"""LMS Program checklist — student surface (2026-08-21 redesign):
GET /lms/programs, GET /lms/programs/{id}, self-check, and submission
paste-back. Redis-free (uses the `client` fixture).

Team-scoped items (Competition domain, 2026-08-24) are covered at the
bottom — same endpoints, `item.scope == "team"` routes the write to the
caller's `Team` in that cohort instead of their own individual row.
"""

import uuid

import pytest
from fastapi import status as http_status
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.lms.course import Course
from app.models.lms.program import LmsProgram, LmsProgramItem, LmsProgramTeamItemProgress
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.spine.contact import Contact
from app.models.user import User
from app.services.lms.program import assign_lms_program
from app.services.teams import create_team


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _author(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Checklist Student Test Author", email=f"cksa-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _student(db) -> User:
    contact = Contact(
        id=uuid.uuid4(), full_name="Checklist Endpoint Student", contact_roles=["student"],
        secondary_phones=[], preferred_language="en", lifecycle_stage="lead",
    )
    db.add(contact)
    await db.flush()
    user = User(
        id=uuid.uuid4(), full_name="Checklist Endpoint Student", email=f"cks-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["student"], status="active", contact_id=contact.id,
    )
    db.add(user)
    await db.flush()
    return user


async def _cohort_with_checklist(db, *, author) -> tuple[Cohort, LmsProgram]:
    program = Program(
        id=uuid.uuid4(), code=f"CKS-{uuid.uuid4().hex[:8]}", name="Checklist Student Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Checklist Student Cohort", status="running")
    db.add(cohort)
    await db.flush()
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Endpoint Test Checklist")
    db.add(lms_program)
    await db.flush()
    return cohort, lms_program


async def _course_item(db, *, lms_program: LmsProgram, author, position: int) -> LmsProgramItem:
    course = Course(id=uuid.uuid4(), title=f"Course {uuid.uuid4().hex[:6]}", created_by=author.id, is_published=True)
    db.add(course)
    await db.flush()
    item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=position,
        item_type="course", title=course.title, course_id=course.id,
    )
    db.add(item)
    await db.flush()
    return item


@pytest.mark.asyncio
async def test_list_is_empty_for_a_student_with_no_assignments(db, client):
    student = await _student(db)
    await db.commit()
    resp = await client.get("/lms/programs", headers=_headers(student))
    assert resp.status_code == 200 and resp.json() == []


@pytest.mark.asyncio
async def test_list_and_detail_report_progress(db, client):
    author = await _author(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    await _course_item(db, lms_program=lms_program, author=author, position=1)
    manual_item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=2,
        item_type="manual", title="Confirm attendance",
    )
    db.add(manual_item)
    student = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    listed = await client.get("/lms/programs", headers=_headers(student))
    assert listed.status_code == 200
    row = listed.json()[0]
    assert row["assignment_id"] == str(assignment.id)
    assert row["items_total"] == 2 and row["items_done"] == 0
    assert row["pct"] == 0

    detail = await client.get(f"/lms/programs/{assignment.id}", headers=_headers(student))
    assert detail.status_code == 200
    body = detail.json()
    assert body["name"] == "Endpoint Test Checklist"
    assert len(body["items"]) == 2
    assert body["items"][0]["item_type"] == "course" and body["items"][0]["status"] == "pending"
    assert body["items"][1]["item_type"] == "manual" and body["items"][1]["status"] == "pending"


@pytest.mark.asyncio
async def test_detail_404s_for_a_different_students_assignment(db, client):
    author = await _author(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    await _course_item(db, lms_program=lms_program, author=author, position=1)
    owner = await _student(db)
    intruder = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=owner.id, cohort_id=cohort.id)
    await db.commit()

    resp = await client.get(f"/lms/programs/{assignment.id}", headers=_headers(intruder))
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_self_check_a_manual_item(db, client):
    author = await _author(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    manual_item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="manual", title="Read the syllabus",
    )
    db.add(manual_item)
    student = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    resp = await client.post(
        f"/lms/programs/{assignment.id}/items/{manual_item.id}/complete", headers=_headers(student),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "done"


@pytest.mark.asyncio
async def test_self_check_a_requires_confirmation_item_goes_to_awaiting(db, client):
    author = await _author(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="manual", title="Attend the ceremony", requires_confirmation=True,
    )
    db.add(item)
    student = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    resp = await client.post(f"/lms/programs/{assignment.id}/items/{item.id}/complete", headers=_headers(student))
    assert resp.status_code == 200
    assert resp.json()["status"] == "awaiting_confirmation"


@pytest.mark.asyncio
async def test_cannot_self_check_an_auto_tracked_course_item(db, client):
    author = await _author(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    item = await _course_item(db, lms_program=lms_program, author=author, position=1)
    student = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    resp = await client.post(f"/lms/programs/{assignment.id}/items/{item.id}/complete", headers=_headers(student))
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_submission_item_needs_a_link_before_it_can_self_check(db, client):
    author = await _author(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="submission", title="Tinkercad build", submission_prompt="Paste your share link",
    )
    db.add(item)
    student = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    too_early = await client.post(f"/lms/programs/{assignment.id}/items/{item.id}/complete", headers=_headers(student))
    assert too_early.status_code == http_status.HTTP_400_BAD_REQUEST

    submitted = await client.post(
        f"/lms/programs/{assignment.id}/items/{item.id}/submit", headers=_headers(student),
        json={"url": "https://tinkercad.com/things/my-build"},
    )
    assert submitted.status_code == 200
    assert submitted.json()["submitted_url"] == "https://tinkercad.com/things/my-build"

    completed = await client.post(f"/lms/programs/{assignment.id}/items/{item.id}/complete", headers=_headers(student))
    assert completed.status_code == 200
    assert completed.json()["status"] == "done"


@pytest.mark.asyncio
async def test_cannot_submit_a_link_to_a_non_submission_item(db, client):
    author = await _author(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="manual", title="Not a submission",
    )
    db.add(item)
    student = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    resp = await client.post(
        f"/lms/programs/{assignment.id}/items/{item.id}/submit", headers=_headers(student),
        json={"url": "https://example.com"},
    )
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST


# ── Team-scoped items (Competition domain, 2026-08-24) ──────────────────────

@pytest.mark.asyncio
async def test_a_team_scoped_item_is_shared_and_any_teammate_can_override(db, client):
    author = await _author(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="submission", title="Mission Poster", submission_prompt="Paste your poster link",
        scope="team",
    )
    db.add(item)
    student_a = await _student(db)
    student_b = await _student(db)
    await db.commit()
    team = await create_team(db, name="Falcon Eye", created_by=student_a.id, cohort_id=cohort.id, member_ids=[student_b.id])
    a_assignment = await assign_lms_program(db, user_id=student_a.id, cohort_id=cohort.id)
    assignment_b = await assign_lms_program(db, user_id=student_b.id, cohort_id=cohort.id)
    await db.commit()

    submitted = await client.post(
        f"/lms/programs/{assignment_b.id}/items/{item.id}/submit", headers=_headers(student_b),
        json={"url": "https://canva.com/design/poster-v1"},
    )
    assert submitted.status_code == 200, submitted.text
    body = submitted.json()
    assert body["scope"] == "team"
    assert body["submitted_url"] == "https://canva.com/design/poster-v1"
    assert body["updated_by_name"] == student_b.full_name

    # Student A never submitted anything themself, but reads the same
    # shared fact — this is the whole point, not an accident.
    detail_a = await client.get(f"/lms/programs/{a_assignment.id}", headers=_headers(student_a))
    assert detail_a.status_code == 200
    a_item = detail_a.json()["items"][0]
    assert a_item["submitted_url"] == "https://canva.com/design/poster-v1"
    assert a_item["updated_by_name"] == student_b.full_name

    # Student A overrides it — same row, not a competing one.
    overridden = await client.post(
        f"/lms/programs/{a_assignment.id}/items/{item.id}/submit", headers=_headers(student_a),
        json={"url": "https://canva.com/design/poster-v2"},
    )
    assert overridden.status_code == 200
    assert overridden.json()["submitted_url"] == "https://canva.com/design/poster-v2"
    assert overridden.json()["updated_by_name"] == student_a.full_name

    # And the team's single progress row is exactly one — no fork per student.
    rows = (await db.execute(
        select(LmsProgramTeamItemProgress).where(LmsProgramTeamItemProgress.item_id == item.id)
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].team_id == team.id


@pytest.mark.asyncio
async def test_a_team_scoped_item_403s_for_a_student_with_no_team_in_that_cohort(db, client):
    author = await _author(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="submission", title="Mission Poster", submission_prompt="Paste your poster link",
        scope="team",
    )
    db.add(item)
    solo_student = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=solo_student.id, cohort_id=cohort.id)
    await db.commit()

    resp = await client.post(
        f"/lms/programs/{assignment.id}/items/{item.id}/submit", headers=_headers(solo_student),
        json={"url": "https://canva.com/design/poster"},
    )
    assert resp.status_code == http_status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_individual_and_team_items_on_the_same_checklist_stay_independent(db, client):
    """A team member's own course/guide progress is unaffected by their
    teammate's edits to the team-scoped rows on the same checklist."""
    author = await _author(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    individual_item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="manual", title="Watch the intro guide",
    )
    team_item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=2,
        item_type="submission", title="Mission Poster", submission_prompt="Paste your poster link",
        scope="team",
    )
    db.add_all([individual_item, team_item])
    student_a = await _student(db)
    student_b = await _student(db)
    await db.commit()
    await create_team(db, name="Zayed Vision", created_by=student_a.id, cohort_id=cohort.id, member_ids=[student_b.id])
    assignment_a = await assign_lms_program(db, user_id=student_a.id, cohort_id=cohort.id)
    assignment_b = await assign_lms_program(db, user_id=student_b.id, cohort_id=cohort.id)
    await db.commit()

    # A completes their own individual item...
    a_done = await client.post(
        f"/lms/programs/{assignment_a.id}/items/{individual_item.id}/complete", headers=_headers(student_a),
    )
    assert a_done.status_code == 200 and a_done.json()["status"] == "done"

    # ...B's own copy of that same item is untouched.
    detail_b = await client.get(f"/lms/programs/{assignment_b.id}", headers=_headers(student_b))
    b_individual = next(i for i in detail_b.json()["items"] if i["id"] == str(individual_item.id))
    assert b_individual["status"] == "pending"

    # But the team item B submits is visible on A's checklist too.
    b_submit = await client.post(
        f"/lms/programs/{assignment_b.id}/items/{team_item.id}/submit", headers=_headers(student_b),
        json={"url": "https://canva.com/design/team-poster"},
    )
    assert b_submit.status_code == 200
    detail_a = await client.get(f"/lms/programs/{assignment_a.id}", headers=_headers(student_a))
    a_team_item = next(i for i in detail_a.json()["items"] if i["id"] == str(team_item.id))
    assert a_team_item["submitted_url"] == "https://canva.com/design/team-poster"

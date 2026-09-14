"""LMS Program checklist — student surface (2026-08-21 redesign):
GET /lms/programs, GET /lms/programs/{id}, self-check, and submission
paste-back. Redis-free (uses the `client` fixture).

Team-scoped items (Competition domain, 2026-08-24) are covered at the
bottom — same endpoints, `item.scope == "team"` routes the write to the
caller's `Team` in that cohort instead of their own individual row.
"""

import uuid
from datetime import date, datetime, time, timedelta, timezone

import pytest
from fastapi import status as http_status
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.lms.course import Course
from app.models.lms.program import LmsProgram, LmsProgramItem, LmsProgramTeamItemProgress
from app.models.missions.design import Design, DesignComponent, DesignComponentLibrary
from app.models.missions.mission import Mission, MissionAttempt, MissionVariant
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.spine.contact import Contact
from app.models.user import User
from app.services.lms.program import assign_lms_program
from app.services.teams import create_team

# ── Roadmap board fixtures (2026-09) — a minimal design mission an attempt
# can be pinned to, and a variant config with every threshold key
# variant_thresholds() reads, same shape test_missions_design_v2_router.py
# uses. ──────────────────────────────────────────────────────────────────────

_VARIANT_CONFIG = {
    "max_storage_kb": 1_048_576.0, "required_storage_margin_kb": 0.0,
    "power_per_solar_cell_w": 1.1, "maximum_budget_aed": 2000.0,
    "assumed_distance_km": 500.0, "transmit_power_dbm": 30.0,
    "good_link_margin_threshold_db": 3.0, "weak_link_margin_threshold_db": 0.0,
    "max_depth_of_discharge_pct": 30.0, "required_downlink_margin_fraction": 0.10,
}


async def _design_mission(db, *, author) -> tuple[Mission, MissionVariant]:
    mission = Mission(
        id=uuid.uuid4(), title="Build Your CubeSat", slug=f"roadmap-design-{uuid.uuid4().hex[:8]}",
        kind="design", authored_by=author.id, status="published", summary="Design one.",
    )
    db.add(mission)
    await db.flush()
    variant = MissionVariant(
        id=uuid.uuid4(), mission_id=mission.id, label="Engineer", position=1, points=200, config=_VARIANT_CONFIG,
    )
    db.add(variant)
    await db.flush()
    return mission, variant


async def _phase_item(db, *, lms_program: LmsProgram, position: int, mission_id, step_key: str) -> LmsProgramItem:
    item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=position,
        item_type="mission_run", title=f"Madar · {step_key}", mission_id=mission_id, mission_step_key=step_key,
    )
    db.add(item)
    await db.flush()
    return item


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
    assert submitted.json()["status"] == "done"


@pytest.mark.asyncio
async def test_multi_link_submission_takes_several_labeled_links(db, client):
    """Ops's per-item toggle (2026-09-14): submission_multi_link=True takes
    `links` instead of a bare `url` — first link still mirrors into
    submitted_url so anything only reading that column sees something real."""
    author = await _author(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="submission", title="Team deliverable", submission_multi_link=True,
    )
    db.add(item)
    student = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    resp = await client.post(
        f"/lms/programs/{assignment.id}/items/{item.id}/submit", headers=_headers(student),
        json={"links": [
            {"label": "Member 1 link", "url": "https://example.com/mem1"},
            {"label": "Member 2 link", "url": "https://example.com/mem2"},
            {"label": None, "url": "https://example.com/team"},
        ]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "done"
    assert body["submission_multi_link"] is True
    assert body["submitted_url"] == "https://example.com/mem1"
    assert [l["url"] for l in body["submitted_links"]] == [
        "https://example.com/mem1", "https://example.com/mem2", "https://example.com/team",
    ]
    assert body["submitted_links"][0]["label"] == "Member 1 link"
    assert body["submitted_links"][2]["label"] is None

    # Round-trips back out of the checklist read too, not just the submit response.
    detail = await client.get(f"/lms/programs/{assignment.id}", headers=_headers(student))
    detail_item = next(i for i in detail.json()["items"] if i["id"] == str(item.id))
    assert len(detail_item["submitted_links"]) == 3


@pytest.mark.asyncio
async def test_multi_link_submission_requires_at_least_one_link(db, client):
    author = await _author(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="submission", title="Team deliverable", submission_multi_link=True,
    )
    db.add(item)
    student = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    empty = await client.post(
        f"/lms/programs/{assignment.id}/items/{item.id}/submit", headers=_headers(student), json={"links": []},
    )
    assert empty.status_code == http_status.HTTP_400_BAD_REQUEST

    no_links_key = await client.post(
        f"/lms/programs/{assignment.id}/items/{item.id}/submit", headers=_headers(student), json={"url": "https://example.com"},
    )
    # A plain `url` on a multi-link item isn't a link list — still refused.
    assert no_links_key.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_single_link_item_ignores_submission_multi_link_off_by_default(db, client):
    """A plain (non-multi) submission item still takes a bare `url`, same
    as before this feature existed — submission_multi_link defaults False."""
    author = await _author(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="submission", title="Solo deliverable",
    )
    db.add(item)
    student = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    resp = await client.post(
        f"/lms/programs/{assignment.id}/items/{item.id}/submit", headers=_headers(student),
        json={"url": "https://example.com/solo"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["submission_multi_link"] is False
    assert body["submitted_url"] == "https://example.com/solo"
    assert body["submitted_links"] is None


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


# ── Submission deadlines ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_submit_allowed_before_deadline(db, client):
    author = await _author(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="submission", title="Final Poster", submission_prompt="Paste your link",
        deadline_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    db.add(item)
    student = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    resp = await client.post(
        f"/lms/programs/{assignment.id}/items/{item.id}/submit", headers=_headers(student),
        json={"url": "https://example.com/poster"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "done"


@pytest.mark.asyncio
async def test_submit_blocked_after_deadline(db, client):
    author = await _author(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="submission", title="Final Poster", submission_prompt="Paste your link",
        deadline_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db.add(item)
    student = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    resp = await client.post(
        f"/lms/programs/{assignment.id}/items/{item.id}/submit", headers=_headers(student),
        json={"url": "https://example.com/poster"},
    )
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_replace_submission_blocked_after_deadline(db, client):
    """Not just the first submit — replacing an already-submitted link is
    blocked too once the deadline has passed."""
    author = await _author(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="submission", title="Final Poster", submission_prompt="Paste your link",
        deadline_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(item)
    student = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    first = await client.post(
        f"/lms/programs/{assignment.id}/items/{item.id}/submit", headers=_headers(student),
        json={"url": "https://example.com/poster-v1"},
    )
    assert first.status_code == 200

    # The deadline passes.
    item.deadline_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db.commit()

    replace = await client.post(
        f"/lms/programs/{assignment.id}/items/{item.id}/submit", headers=_headers(student),
        json={"url": "https://example.com/poster-v2"},
    )
    assert replace.status_code == http_status.HTTP_400_BAD_REQUEST


# ── Session item type ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_session_item_self_check(db, client):
    author = await _author(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="session", title="Kickoff call",
        session_location="Building 4, Room 210", session_meeting_url="https://meet.example.com/kickoff",
    )
    db.add(item)
    student = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    resp = await client.post(f"/lms/programs/{assignment.id}/items/{item.id}/complete", headers=_headers(student))
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "done"


@pytest.mark.asyncio
async def test_session_item_requires_confirmation(db, client):
    author = await _author(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="session", title="Kickoff call", requires_confirmation=True,
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
async def test_get_checklist_returns_session_and_deadline_fields(db, client):
    author = await _author(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    session_item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="session", title="Kickoff call",
        session_date=date(2026, 9, 15), session_starts_at=time(17, 0, 0),
        session_location="Building 4, Room 210", session_meeting_url="https://meet.example.com/kickoff",
    )
    submission_item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=2,
        item_type="submission", title="Final Poster", submission_prompt="Paste your link",
        deadline_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    db.add_all([session_item, submission_item])
    student = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    resp = await client.get(f"/lms/programs/{assignment.id}", headers=_headers(student))
    assert resp.status_code == 200
    items_by_type = {i["item_type"]: i for i in resp.json()["items"]}
    assert items_by_type["session"]["session_date"] == "2026-09-15"
    assert items_by_type["session"]["session_starts_at"] == "17:00:00"
    assert items_by_type["session"]["session_location"] == "Building 4, Room 210"
    assert items_by_type["session"]["session_meeting_url"] == "https://meet.example.com/kickoff"
    assert items_by_type["submission"]["deadline_at"] is not None


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
async def test_team_scoped_submission_blocked_after_deadline(db, client):
    """The single deadline check in submit_program_item covers a
    team-scoped item too — checklist_item_write_target's fan-out happens
    after the guard, so no separate scope branch is needed."""
    author = await _author(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="submission", title="Mission Poster", submission_prompt="Paste your poster link",
        scope="team", deadline_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db.add(item)
    student_a = await _student(db)
    student_b = await _student(db)
    await db.commit()
    await create_team(db, name="Deadline Team", created_by=student_a.id, cohort_id=cohort.id, member_ids=[student_b.id])
    assignment_a = await assign_lms_program(db, user_id=student_a.id, cohort_id=cohort.id)
    await db.commit()

    resp = await client.post(
        f"/lms/programs/{assignment_a.id}/items/{item.id}/submit", headers=_headers(student_a),
        json={"url": "https://canva.com/design/poster"},
    )
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST


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


# ── Roadmap board — gating (2026-09) ────────────────────────────────────────

@pytest.mark.asyncio
async def test_gated_item_locks_until_the_earlier_required_item_is_done(db, client):
    author = await _author(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    first = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="manual", title="Read the guideline",
    )
    second = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=2,
        item_type="manual", title="Do the work", gated=True,
    )
    db.add_all([first, second])
    student = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    before = await client.get(f"/lms/programs/{assignment.id}", headers=_headers(student))
    items_by_id = {i["id"]: i for i in before.json()["items"]}
    assert items_by_id[str(first.id)]["locked"] is False
    assert items_by_id[str(second.id)]["locked"] is True

    locked_complete = await client.post(
        f"/lms/programs/{assignment.id}/items/{second.id}/complete", headers=_headers(student),
    )
    assert locked_complete.status_code == http_status.HTTP_409_CONFLICT

    first_done = await client.post(f"/lms/programs/{assignment.id}/items/{first.id}/complete", headers=_headers(student))
    assert first_done.status_code == 200

    after = await client.get(f"/lms/programs/{assignment.id}", headers=_headers(student))
    after_by_id = {i["id"]: i for i in after.json()["items"]}
    assert after_by_id[str(second.id)]["locked"] is False

    now_complete = await client.post(f"/lms/programs/{assignment.id}/items/{second.id}/complete", headers=_headers(student))
    assert now_complete.status_code == 200


@pytest.mark.asyncio
async def test_optional_item_never_blocks_a_gated_item(db, client):
    author = await _author(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    optional_first = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="manual", title="Optional extra reading", optional=True,
    )
    gated_second = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=2,
        item_type="manual", title="Do the work", gated=True,
    )
    db.add_all([optional_first, gated_second])
    student = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    detail = await client.get(f"/lms/programs/{assignment.id}", headers=_headers(student))
    by_id = {i["id"]: i for i in detail.json()["items"]}
    assert by_id[str(gated_second.id)]["locked"] is False


@pytest.mark.asyncio
async def test_awaiting_confirmation_does_not_unlock_the_next_gated_item(db, client):
    author = await _author(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    first = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="manual", title="Attend the ceremony", requires_confirmation=True,
    )
    second = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=2,
        item_type="manual", title="Do the work", gated=True,
    )
    db.add_all([first, second])
    student = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    first_check = await client.post(f"/lms/programs/{assignment.id}/items/{first.id}/complete", headers=_headers(student))
    assert first_check.status_code == 200 and first_check.json()["status"] == "awaiting_confirmation"

    detail = await client.get(f"/lms/programs/{assignment.id}", headers=_headers(student))
    by_id = {i["id"]: i for i in detail.json()["items"]}
    assert by_id[str(second.id)]["locked"] is True

    locked_submit = await client.post(f"/lms/programs/{assignment.id}/items/{second.id}/complete", headers=_headers(student))
    assert locked_submit.status_code == http_status.HTTP_409_CONFLICT


@pytest.mark.asyncio
async def test_gated_submission_item_409s_while_locked(db, client):
    author = await _author(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    first = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="manual", title="Read the guideline",
    )
    second = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=2,
        item_type="submission", title="Upload your build", submission_prompt="Paste your link", gated=True,
    )
    db.add_all([first, second])
    student = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    resp = await client.post(
        f"/lms/programs/{assignment.id}/items/{second.id}/submit", headers=_headers(student),
        json={"url": "https://example.com/build"},
    )
    assert resp.status_code == http_status.HTTP_409_CONFLICT


# ── Roadmap board — Madar phase items (2026-09) ─────────────────────────────

@pytest.mark.asyncio
async def test_phase_item_setup_needs_self_check_after_the_design_objective_is_saved(db, client):
    """2026-09 — `is_valid` (here, `design_objective is not None`) alone no
    longer flips the tile to done: the student's own "Complete this step"
    click (POST /missions/design/attempts/{id}/steps/setup/confirm) is now
    also required. See services/lms/program.py's `_mission_run_item_done`."""
    author = await _author(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    mission, _variant = await _design_mission(db, author=author)
    item = await _phase_item(db, lms_program=lms_program, position=1, mission_id=mission.id, step_key="setup")
    student = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    detail = await client.get(f"/lms/programs/{assignment.id}", headers=_headers(student))
    row = detail.json()["items"][0]
    assert row["mission_step_key"] == "setup" and row["status"] == "pending"
    attempt_id = uuid.UUID(row["mission_attempt_id"])

    design = Design(id=uuid.uuid4(), attempt_id=attempt_id, design_name="My CubeSat", design_objective="Track weather.")
    db.add(design)
    await db.commit()

    # Ready, but not yet self-checked — still pending.
    still_pending = await client.get(f"/lms/programs/{assignment.id}", headers=_headers(student))
    assert still_pending.json()["items"][0]["status"] == "pending"

    confirm = await client.post(f"/missions/design/attempts/{attempt_id}/steps/setup/confirm", headers=_headers(student))
    assert confirm.status_code == http_status.HTTP_200_OK
    assert confirm.json()["confirmed_steps"] == ["setup"]

    after = await client.get(f"/lms/programs/{assignment.id}", headers=_headers(student))
    assert after.json()["items"][0]["status"] == "done"
    # The whole-mission attempt is still just in_progress — confirming one
    # step (out of several still outstanding here: components/conops/etc.
    # were never touched) isn't enough to auto-finalize the mission. See
    # confirm_design_step's own auto-finalize note — it only fires once
    # every required step is confirmed AND the design is fully valid.
    attempt = await db.get(MissionAttempt, attempt_id)
    assert attempt.status == "in_progress"


@pytest.mark.asyncio
async def test_confirm_design_step_rejects_a_step_that_isnt_ready(db, client):
    author = await _author(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    mission, _variant = await _design_mission(db, author=author)
    await _phase_item(db, lms_program=lms_program, position=1, mission_id=mission.id, step_key="setup")
    student = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    detail = await client.get(f"/lms/programs/{assignment.id}", headers=_headers(student))
    attempt_id = uuid.UUID(detail.json()["items"][0]["mission_attempt_id"])
    # No Design row at all yet — nothing to be ready.
    resp = await client.post(f"/missions/design/attempts/{attempt_id}/steps/setup/confirm", headers=_headers(student))
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_confirm_design_step_rejects_report_and_downlink(db, client):
    """`report`/`downlink` stay purely validity-driven — matching
    DesignMissionPage.tsx's own exclusion of the Report tab from the
    Complete-button flow — so they're not in `CONFIRMABLE_STEP_KEYS`."""
    author = await _author(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    mission, _variant = await _design_mission(db, author=author)
    await _phase_item(db, lms_program=lms_program, position=1, mission_id=mission.id, step_key="report")
    student = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    detail = await client.get(f"/lms/programs/{assignment.id}", headers=_headers(student))
    attempt_id = uuid.UUID(detail.json()["items"][0]["mission_attempt_id"])
    for step_key in ("report", "downlink"):
        resp = await client.post(f"/missions/design/attempts/{attempt_id}/steps/{step_key}/confirm", headers=_headers(student))
        assert resp.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_phase_item_components_needs_self_check_after_dashboard_steps_is_valid(db, client):
    """2026-09 — same self-check requirement as `setup`, for a real
    `DESIGN_STEP_LABELS` key this time (`components`)."""
    author = await _author(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    mission, _variant = await _design_mission(db, author=author)
    item = await _phase_item(db, lms_program=lms_program, position=1, mission_id=mission.id, step_key="components")
    student = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    detail = await client.get(f"/lms/programs/{assignment.id}", headers=_headers(student))
    attempt_id = uuid.UUID(detail.json()["items"][0]["mission_attempt_id"])
    assert detail.json()["items"][0]["status"] == "pending"

    design = Design(id=uuid.uuid4(), attempt_id=attempt_id, design_name="My CubeSat")
    db.add(design)
    await db.flush()
    library = DesignComponentLibrary(id=uuid.uuid4(), component_name="GPS Module", subsystem="ADCS")
    db.add(library)
    await db.flush()
    db.add(DesignComponent(
        id=uuid.uuid4(), design_id=design.id, library_component_id=library.id, quantity=1,
        component_name=library.component_name, subsystem=library.subsystem,
    ))
    await db.commit()

    # Ready (one component added), but not yet self-checked.
    still_pending = await client.get(f"/lms/programs/{assignment.id}", headers=_headers(student))
    assert still_pending.json()["items"][0]["status"] == "pending"

    confirm = await client.post(f"/missions/design/attempts/{attempt_id}/steps/components/confirm", headers=_headers(student))
    assert confirm.status_code == http_status.HTTP_200_OK
    assert confirm.json()["confirmed_steps"] == ["components"]
    # Idempotent — confirming again doesn't duplicate the entry.
    again = await client.post(f"/missions/design/attempts/{attempt_id}/steps/components/confirm", headers=_headers(student))
    assert again.json()["confirmed_steps"] == ["components"]

    after = await client.get(f"/lms/programs/{assignment.id}", headers=_headers(student))
    assert after.json()["items"][0]["status"] == "done"


@pytest.mark.asyncio
async def test_several_phase_items_share_one_mission_attempt_id(db, client):
    """Six Madar phase tiles on one checklist all pin the same
    mission_attempt_id — start_attempt's single-flight resume, not a bug
    (see docs/HANDOFF_LMS.md §11's op note)."""
    author = await _author(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    mission, _variant = await _design_mission(db, author=author)
    await _phase_item(db, lms_program=lms_program, position=1, mission_id=mission.id, step_key="setup")
    await _phase_item(db, lms_program=lms_program, position=2, mission_id=mission.id, step_key="components")
    await _phase_item(db, lms_program=lms_program, position=3, mission_id=mission.id, step_key="conops")
    student = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    detail = await client.get(f"/lms/programs/{assignment.id}", headers=_headers(student))
    attempt_ids = {i["mission_attempt_id"] for i in detail.json()["items"]}
    assert len(attempt_ids) == 1 and None not in attempt_ids


# ── team_setup (2026-09-14 team onboarding) ─────────────────────────────────

@pytest.mark.asyncio
async def test_team_setup_lets_any_teammate_set_and_change_the_name(db, client):
    from app.models.team import Team

    author = await _author(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="team_setup", title="Name your team", scope="team",
    )
    db.add(item)
    student_a = await _student(db)
    student_b = await _student(db)
    await db.commit()
    team = await create_team(
        db, name="T-014", created_by=student_a.id, cohort_id=cohort.id, member_ids=[student_b.id],
        roster_team_id="T-014",
    )
    assignment_a = await assign_lms_program(db, user_id=student_a.id, cohort_id=cohort.id)
    assignment_b = await assign_lms_program(db, user_id=student_b.id, cohort_id=cohort.id)
    await db.commit()

    resp = await client.post(
        f"/lms/programs/{assignment_a.id}/items/{item.id}/team-name",
        headers=_headers(student_a), json={"name": "Falcon Eye"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "done"
    assert body["scope"] == "team"
    assert body["updated_by_name"] == student_a.full_name

    await db.refresh(team)
    assert team.name == "Falcon Eye"

    # The checklist's own top-level team_name reflects it too.
    detail = await client.get(f"/lms/programs/{assignment_b.id}", headers=_headers(student_b))
    assert detail.json()["team_name"] == "Falcon Eye"

    # Student B (a different teammate) changes it again — last write wins,
    # no lock, matches every other team-scoped write's convention.
    resp2 = await client.post(
        f"/lms/programs/{assignment_b.id}/items/{item.id}/team-name",
        headers=_headers(student_b), json={"name": "Silent Comet"},
    )
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["updated_by_name"] == student_b.full_name
    row = (await db.execute(select(Team).where(Team.id == team.id))).scalar_one()
    assert row.name == "Silent Comet"


@pytest.mark.asyncio
async def test_team_setup_rejects_a_case_insensitive_collision(db, client):
    author = await _author(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="team_setup", title="Name your team", scope="team",
    )
    db.add(item)
    student = await _student(db)
    other_owner = await _student(db)
    await db.commit()
    await create_team(db, name="Falcon", created_by=other_owner.id, cohort_id=cohort.id)
    await create_team(db, name="T-014", created_by=student.id, cohort_id=cohort.id, roster_team_id="T-014")
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    resp = await client.post(
        f"/lms/programs/{assignment.id}/items/{item.id}/team-name",
        headers=_headers(student), json={"name": "falcon"},
    )
    assert resp.status_code == 409, resp.text


@pytest.mark.asyncio
async def test_team_setup_blocked_after_deadline(db, client):
    author = await _author(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="team_setup", title="Name your team", scope="team",
        deadline_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db.add(item)
    student = await _student(db)
    await db.commit()
    await create_team(db, name="T-014", created_by=student.id, cohort_id=cohort.id, roster_team_id="T-014")
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    resp = await client.post(
        f"/lms/programs/{assignment.id}/items/{item.id}/team-name",
        headers=_headers(student), json={"name": "Falcon Eye"},
    )
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_team_setup_403s_for_a_student_with_no_team(db, client):
    author = await _author(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="team_setup", title="Name your team", scope="team",
    )
    db.add(item)
    solo_student = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=solo_student.id, cohort_id=cohort.id)
    await db.commit()

    resp = await client.post(
        f"/lms/programs/{assignment.id}/items/{item.id}/team-name",
        headers=_headers(solo_student), json={"name": "Falcon Eye"},
    )
    assert resp.status_code == http_status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_team_setup_rejects_the_wrong_item_type(db, client):
    author = await _author(db)
    cohort, lms_program = await _cohort_with_checklist(db, author=author)
    item = await _course_item(db, lms_program=lms_program, author=author, position=1)
    student = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    resp = await client.post(
        f"/lms/programs/{assignment.id}/items/{item.id}/team-name",
        headers=_headers(student), json={"name": "Falcon Eye"},
    )
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST

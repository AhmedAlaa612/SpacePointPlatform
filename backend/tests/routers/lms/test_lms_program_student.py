"""LMS Program checklist — student surface (2026-08-21 redesign):
GET /lms/programs, GET /lms/programs/{id}, self-check, and submission
paste-back. Redis-free (uses the `client` fixture).
"""

import uuid

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.lms.course import Course
from app.models.lms.program import LmsProgram, LmsProgramItem
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.spine.contact import Contact
from app.models.user import User
from app.services.lms.program import assign_lms_program


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

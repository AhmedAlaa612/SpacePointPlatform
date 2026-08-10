"""P1-5 (LMS Phase 2 Stage 1) — admin enrollment endpoints: roster, grant,
revoke, bulk-grant by cohort or role, per-student view. Redis-free.
"""

import uuid

import pytest
from fastapi import status as http_status
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.lms import Course, Enrollment
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.models.user import User
from app.services.lms import enroll


async def _ops(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Ops Admin", email=f"ops-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _student(db, **kw) -> User:
    user = User(
        id=uuid.uuid4(), full_name=kw.pop("full_name", "Student"),
        email=f"student-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["student"], status="active", **kw,
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _course(db, *, author, **kw) -> Course:
    course = Course(
        id=uuid.uuid4(), title=f"Course {uuid.uuid4().hex[:8]}", created_by=author.id,
        is_published=True, **kw,
    )
    db.add(course)
    await db.flush()
    return course


@pytest.mark.asyncio
async def test_roster_lists_enrollments_with_student_info(db, client):
    ops = await _ops(db)
    course = await _course(db, author=ops)
    student = await _student(db, full_name="Roster Student")
    await enroll(db, user_id=student.id, course_id=course.id, source="self")
    await db.commit()

    resp = await client.get(f"/lms/admin/courses/{course.id}/roster", headers=_headers(ops))
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["user_id"] == str(student.id)
    assert rows[0]["student_name"] == "Roster Student"
    assert rows[0]["status"] == "active"


@pytest.mark.asyncio
async def test_grant_enrolls_a_named_student_and_records_granted_by(db, client):
    ops = await _ops(db)
    course = await _course(db, author=ops)
    student = await _student(db)

    resp = await client.post(
        f"/lms/admin/courses/{course.id}/enrollments", headers=_headers(ops),
        json={"user_id": str(student.id)},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["granted_by"] == str(ops.id)
    assert resp.json()["source"] == "ops"

    row = (await db.execute(
        select(Enrollment).where(Enrollment.user_id == student.id, Enrollment.course_id == course.id)
    )).scalars().first()
    assert row is not None and row.granted_by == ops.id


@pytest.mark.asyncio
async def test_grant_works_on_an_invite_only_course(db, client):
    """access_mode only gates *self*-enrol (P1-4) — an ops grant is always allowed."""
    ops = await _ops(db)
    course = await _course(db, author=ops, access_mode="invite")
    student = await _student(db)

    resp = await client.post(
        f"/lms/admin/courses/{course.id}/enrollments", headers=_headers(ops),
        json={"user_id": str(student.id)},
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_grant_404s_for_unknown_user(db, client):
    ops = await _ops(db)
    course = await _course(db, author=ops)

    resp = await client.post(
        f"/lms/admin/courses/{course.id}/enrollments", headers=_headers(ops),
        json={"user_id": str(uuid.uuid4())},
    )
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_revoke_sets_inactive_never_deletes(db, client):
    ops = await _ops(db)
    course = await _course(db, author=ops)
    student = await _student(db)
    enrollment = await enroll(db, user_id=student.id, course_id=course.id, source="self")
    await db.commit()

    resp = await client.post(f"/lms/admin/enrollments/{enrollment.id}/revoke", headers=_headers(ops))
    assert resp.status_code == 200
    assert resp.json()["status"] == "inactive"

    row = await db.get(Enrollment, enrollment.id)
    assert row is not None  # still exists
    assert row.status == "inactive"


@pytest.mark.asyncio
async def test_student_enrollments_lists_every_course_for_one_user(db, client):
    ops = await _ops(db)
    course_a = await _course(db, author=ops)
    course_b = await _course(db, author=ops)
    student = await _student(db)
    await enroll(db, user_id=student.id, course_id=course_a.id, source="self")
    await enroll(db, user_id=student.id, course_id=course_b.id, source="self")
    await db.commit()

    resp = await client.get(f"/lms/admin/users/{student.id}/enrollments", headers=_headers(ops))
    assert resp.status_code == 200
    course_ids = {row["course_id"] for row in resp.json()}
    assert course_ids == {str(course_a.id), str(course_b.id)}


# ── bulk grant ───────────────────────────────────────────────────────────────

async def _cohort_with_registrations(db, contacts_with_accounts: list[tuple], contacts_without_accounts: int = 0):
    program = Program(
        id=uuid.uuid4(), code=f"BULK-{uuid.uuid4().hex[:8]}", name="Bulk Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(
        id=uuid.uuid4(), program_id=program.id, name="Bulk Cohort",
        status="registration_open", visibility="public",
    )
    db.add(cohort)
    await db.flush()

    for contact, _user in contacts_with_accounts:
        db.add(Registration(
            id=uuid.uuid4(), contact_id=contact.id, cohort_id=cohort.id,
            status="registered", ticket_token=uuid.uuid4().hex, registered_via="desk", payment_status="waived",
        ))
    for _ in range(contacts_without_accounts):
        c = Contact(id=uuid.uuid4(), full_name="No Account", contact_roles=["student"])
        db.add(c)
        await db.flush()
        db.add(Registration(
            id=uuid.uuid4(), contact_id=c.id, cohort_id=cohort.id,
            status="registered", ticket_token=uuid.uuid4().hex, registered_via="desk", payment_status="waived",
        ))
    await db.flush()
    return cohort


@pytest.mark.asyncio
async def test_bulk_grant_by_cohort_enrolls_registered_students_with_accounts(db, client):
    ops = await _ops(db)
    course = await _course(db, author=ops)

    contact_a = Contact(id=uuid.uuid4(), full_name="Bulk A", contact_roles=["student"])
    contact_b = Contact(id=uuid.uuid4(), full_name="Bulk B", contact_roles=["student"])
    db.add_all([contact_a, contact_b])
    await db.flush()
    user_a = await _student(db, full_name="Bulk A", contact_id=contact_a.id)
    user_b = await _student(db, full_name="Bulk B", contact_id=contact_b.id)

    cohort = await _cohort_with_registrations(
        db, [(contact_a, user_a), (contact_b, user_b)], contacts_without_accounts=1,
    )
    await db.commit()

    resp = await client.post(
        f"/lms/admin/courses/{course.id}/enrollments/bulk", headers=_headers(ops),
        json={"cohort_id": str(cohort.id)},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["granted"] == 2
    assert body["already_enrolled"] == 0
    assert body["skipped_no_account"] == 1

    enrolled_ids = set((await db.execute(
        select(Enrollment.user_id).where(Enrollment.course_id == course.id)
    )).scalars().all())
    assert enrolled_ids == {user_a.id, user_b.id}


@pytest.mark.asyncio
async def test_bulk_grant_by_cohort_skips_already_enrolled(db, client):
    ops = await _ops(db)
    course = await _course(db, author=ops)
    contact = Contact(id=uuid.uuid4(), full_name="Already In", contact_roles=["student"])
    db.add(contact)
    await db.flush()
    student = await _student(db, contact_id=contact.id)
    await enroll(db, user_id=student.id, course_id=course.id, source="self")
    cohort = await _cohort_with_registrations(db, [(contact, student)])
    await db.commit()

    resp = await client.post(
        f"/lms/admin/courses/{course.id}/enrollments/bulk", headers=_headers(ops),
        json={"cohort_id": str(cohort.id)},
    )
    assert resp.status_code == 200
    assert resp.json()["granted"] == 0
    assert resp.json()["already_enrolled"] == 1


@pytest.mark.asyncio
async def test_bulk_grant_by_role_enrolls_every_matching_user(db, client):
    """D2: staff can take LMS courses too — bulk-grant by role is that made concrete."""
    ops = await _ops(db)
    course = await _course(db, author=ops)
    instructor_a = User(
        id=uuid.uuid4(), full_name="Instructor A", email=f"instr-a-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["instructor"], status="active",
    )
    instructor_b = User(
        id=uuid.uuid4(), full_name="Instructor B", email=f"instr-b-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["instructor"], status="active",
    )
    db.add_all([instructor_a, instructor_b])
    await db.commit()

    resp = await client.post(
        f"/lms/admin/courses/{course.id}/enrollments/bulk", headers=_headers(ops),
        json={"role": "instructor"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["granted"] == 2

    enrolled_ids = set((await db.execute(
        select(Enrollment.user_id).where(Enrollment.course_id == course.id)
    )).scalars().all())
    assert enrolled_ids == {instructor_a.id, instructor_b.id}


@pytest.mark.asyncio
async def test_bulk_grant_requires_exactly_one_of_cohort_or_role(db, client):
    ops = await _ops(db)
    course = await _course(db, author=ops)

    neither = await client.post(
        f"/lms/admin/courses/{course.id}/enrollments/bulk", headers=_headers(ops), json={},
    )
    assert neither.status_code == http_status.HTTP_422_UNPROCESSABLE_ENTITY

    both = await client.post(
        f"/lms/admin/courses/{course.id}/enrollments/bulk", headers=_headers(ops),
        json={"cohort_id": str(uuid.uuid4()), "role": "instructor"},
    )
    assert both.status_code == http_status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_enrollment_admin_routes_require_content_role(db, client):
    student = await _student(db)
    ops = await _ops(db)
    course = await _course(db, author=ops)

    resp = await client.get(f"/lms/admin/courses/{course.id}/roster", headers=_headers(student))
    assert resp.status_code == http_status.HTTP_403_FORBIDDEN

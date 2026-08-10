"""P4-1/P4-2 (LMS Phase 2 Stage 4, 2026-08-10) — cohort curriculum admin
endpoints and the reconciliation they trigger. Redis-free.
"""

import uuid

import pytest
from fastapi import status as http_status
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.lms import CohortCurriculum, Course, Enrollment, ProgramCurriculum
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.models.user import User


async def _ops(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Ops", email=f"ops-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _program_cohort(db) -> tuple[Program, Cohort]:
    program = Program(
        id=uuid.uuid4(), code=f"AC-{uuid.uuid4().hex[:8]}", name="Admin Curriculum Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Admin Curriculum Cohort", status="running")
    db.add(cohort)
    await db.flush()
    return program, cohort


async def _course(db, *, author) -> Course:
    course = Course(id=uuid.uuid4(), title=f"Course {uuid.uuid4().hex[:8]}", created_by=author.id, is_published=True)
    db.add(course)
    await db.flush()
    return course


async def _registered_student(db, *, cohort) -> User:
    contact = Contact(id=uuid.uuid4(), full_name="Student", contact_roles=["student"])
    db.add(contact)
    await db.flush()
    student = User(
        id=uuid.uuid4(), full_name="Student", email=f"student-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["student"], status="active", contact_id=contact.id,
    )
    db.add(student)
    await db.flush()
    db.add(Registration(
        id=uuid.uuid4(), contact_id=contact.id, cohort_id=cohort.id, status="registered",
        ticket_token=uuid.uuid4().hex, registered_via="desk", payment_status="waived",
    ))
    await db.flush()
    return student


@pytest.mark.asyncio
async def test_cohort_curriculum_add_list_remove(db, client):
    ops = await _ops(db)
    _program, cohort = await _program_cohort(db)
    course_a = await _course(db, author=ops)
    course_b = await _course(db, author=ops)
    await db.commit()

    add_a = await client.post(
        f"/lms/admin/cohorts/{cohort.id}/curriculum", headers=_headers(ops), json={"course_id": str(course_a.id)},
    )
    assert add_a.status_code == 201 and add_a.json()["position"] == 1

    add_b = await client.post(
        f"/lms/admin/cohorts/{cohort.id}/curriculum", headers=_headers(ops), json={"course_id": str(course_b.id)},
    )
    assert add_b.status_code == 201 and add_b.json()["position"] == 2

    dup = await client.post(
        f"/lms/admin/cohorts/{cohort.id}/curriculum", headers=_headers(ops), json={"course_id": str(course_a.id)},
    )
    assert dup.status_code == http_status.HTTP_409_CONFLICT

    listed = await client.get(f"/lms/admin/cohorts/{cohort.id}/curriculum", headers=_headers(ops))
    assert [c["course_id"] for c in listed.json()] == [str(course_a.id), str(course_b.id)]

    removed = await client.delete(
        f"/lms/admin/cohorts/{cohort.id}/curriculum/{course_a.id}", headers=_headers(ops),
    )
    assert removed.status_code == 204
    remaining = (await db.execute(
        select(CohortCurriculum).where(CohortCurriculum.cohort_id == cohort.id)
    )).scalars().all()
    assert [r.course_id for r in remaining] == [course_b.id]


@pytest.mark.asyncio
async def test_adding_a_cohort_curriculum_entry_enrolls_already_registered_students(db, client):
    ops = await _ops(db)
    _program, cohort = await _program_cohort(db)
    course = await _course(db, author=ops)
    student = await _registered_student(db, cohort=cohort)
    await db.commit()

    resp = await client.post(
        f"/lms/admin/cohorts/{cohort.id}/curriculum", headers=_headers(ops), json={"course_id": str(course.id)},
    )
    assert resp.status_code == 201, resp.text

    enrollment = (await db.execute(
        select(Enrollment).where(Enrollment.user_id == student.id, Enrollment.course_id == course.id)
    )).scalars().first()
    assert enrollment is not None


@pytest.mark.asyncio
async def test_adding_a_program_curriculum_entry_reaches_inheriting_cohorts(db, client):
    """P4-2, trigger 1 for the program side — a course added to a program's
    curriculum reaches every cohort that inherits it (no override), not
    just future registrations."""
    ops = await _ops(db)
    program, cohort = await _program_cohort(db)
    course = await _course(db, author=ops)
    student = await _registered_student(db, cohort=cohort)
    await db.commit()

    resp = await client.post(
        f"/lms/admin/programs/{program.id}/curriculum", headers=_headers(ops), json={"course_id": str(course.id)},
    )
    assert resp.status_code == 201, resp.text

    enrollment = (await db.execute(
        select(Enrollment).where(Enrollment.user_id == student.id, Enrollment.course_id == course.id)
    )).scalars().first()
    assert enrollment is not None


@pytest.mark.asyncio
async def test_program_curriculum_change_does_not_reach_a_cohort_with_its_own_override(db, client):
    ops = await _ops(db)
    program, cohort = await _program_cohort(db)
    own_course = await _course(db, author=ops)
    new_program_course = await _course(db, author=ops)
    db.add(CohortCurriculum(id=uuid.uuid4(), cohort_id=cohort.id, course_id=own_course.id, position=1))
    student = await _registered_student(db, cohort=cohort)
    await db.commit()

    resp = await client.post(
        f"/lms/admin/programs/{program.id}/curriculum", headers=_headers(ops),
        json={"course_id": str(new_program_course.id)},
    )
    assert resp.status_code == 201, resp.text

    enrolled_courses = set((await db.execute(
        select(Enrollment.course_id).where(Enrollment.user_id == student.id)
    )).scalars().all())
    assert enrolled_courses == set()  # the cohort's own curriculum is untouched


@pytest.mark.asyncio
async def test_manual_reconcile_endpoint(db, client):
    ops = await _ops(db)
    program, cohort = await _program_cohort(db)
    course = await _course(db, author=ops)
    db.add(ProgramCurriculum(id=uuid.uuid4(), program_id=program.id, course_id=course.id, position=1))
    student = await _registered_student(db, cohort=cohort)
    await db.commit()

    resp = await client.post(f"/lms/admin/cohorts/{cohort.id}/reconcile-enrollments", headers=_headers(ops))
    assert resp.status_code == 200, resp.text
    assert resp.json()["created"] == 1

    again = await client.post(f"/lms/admin/cohorts/{cohort.id}/reconcile-enrollments", headers=_headers(ops))
    assert again.json()["created"] == 0

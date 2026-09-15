"""Invite-code course/path grants (2026-08-21) — `/lms/admin/invite-codes/
{id}/grants`, the signup-time auto-enrol hook, and the learning-path bulk
grant endpoint (`POST /lms/admin/learning-paths/{id}/enrollments/bulk`).
"""

import uuid

import pytest
from fastapi import status as http_status
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.instructors.invitation_code import InvitationCode
from app.models.lms import Course, Enrollment
from app.models.lms.invite_grant import InvitationCodeGrant
from app.models.lms.learning_path import LearningPath, LearningPathStep
from app.models.lms.program import LmsProgram, LmsProgramAssignment, LmsProgramItem
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.models.user import User


async def _ops(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Ops Admin", email=f"ops-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _student(db, *, name="Student", code=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name=name, email=f"{name.lower()}-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="x", roles=["student"], status="active", invitation_code_used=code,
    )
    db.add(user)
    await db.flush()
    return user


async def _student_with_contact(db, *, name="Student", code=None) -> User:
    """A "program" grant needs a real Registration, which needs a
    contact_id — same shape a real student_signup account always has
    (resolve_or_create_contact runs first), unlike the bare _student()
    helper above every other grant test uses."""
    contact = Contact(id=uuid.uuid4(), full_name=name, email=f"{name.lower()}-{uuid.uuid4().hex[:6]}@example.com")
    db.add(contact)
    await db.flush()
    user = User(
        id=uuid.uuid4(), full_name=name, email=f"{name.lower()}-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="x", roles=["student"], status="active", invitation_code_used=code, contact_id=contact.id,
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _course(db, *, author, **kw) -> Course:
    course = Course(
        id=uuid.uuid4(), title=kw.pop("title", f"Course {uuid.uuid4().hex[:8]}"), created_by=author.id,
        is_published=True, **kw,
    )
    db.add(course)
    await db.flush()
    return course


async def _path_with_steps(db, *, author, n=2) -> tuple[LearningPath, list[Course]]:
    path = LearningPath(id=uuid.uuid4(), title=f"Path {uuid.uuid4().hex[:8]}", created_by=author.id, is_published=True)
    db.add(path)
    await db.flush()
    courses = [await _course(db, author=author) for _ in range(n)]
    for i, c in enumerate(courses, start=1):
        db.add(LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=c.id, position=i))
    await db.flush()
    return path, courses


async def _code(db, *, code="BATCH1") -> InvitationCode:
    row = InvitationCode(id=uuid.uuid4(), code=code, kind="student", is_active=True, max_uses=100, used_count=0)
    db.add(row)
    await db.flush()
    return row


async def _cohort_with_program(db, *, author) -> tuple[Cohort, LmsProgram]:
    """A cohort whose program has one course item — enough to prove a
    "program" grant actually calls assign_lms_program (LmsProgramAssignment
    row + the course item's own enrollment), same fixture shape
    test_lms_program_student.py's own _cohort_with_checklist uses."""
    program = Program(
        id=uuid.uuid4(), code=f"IGP-{uuid.uuid4().hex[:8]}", name="Invite Grant Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Invite Grant Cohort", status="running")
    db.add(cohort)
    await db.flush()
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Invite Grant Checklist")
    db.add(lms_program)
    await db.flush()
    course = await _course(db, author=author)
    item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="course", title=course.title, course_id=course.id,
    )
    db.add(item)
    await db.flush()
    return cohort, lms_program


# ── admin grant CRUD ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_creating_a_course_grant_enrols_existing_code_holders_immediately(db, client):
    ops = await _ops(db)
    code = await _code(db)
    author = await _ops(db)
    course = await _course(db, author=author)
    old_holder = await _student(db, name="Old", code=code.code)
    unrelated = await _student(db, name="Unrelated", code="OTHERCODE")
    await db.commit()

    resp = await client.post(
        f"/lms/admin/invite-codes/{code.id}/grants", headers=_headers(ops), json={"course_id": str(course.id)},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["accounts_enrolled"] == 1
    assert body["grant"]["product_type"] == "course"
    assert body["grant"]["course_title"] == course.title

    enrolled = (await db.execute(
        select(Enrollment).where(Enrollment.user_id == old_holder.id, Enrollment.course_id == course.id)
    )).scalars().first()
    assert enrolled is not None
    assert enrolled.status == "active" and enrolled.source == "invite_code"

    untouched = (await db.execute(
        select(Enrollment).where(Enrollment.user_id == unrelated.id, Enrollment.course_id == course.id)
    )).scalars().first()
    assert untouched is None


@pytest.mark.asyncio
async def test_creating_a_path_grant_enrols_every_step_course(db, client):
    ops = await _ops(db)
    code = await _code(db)
    author = await _ops(db)
    path, (c1, c2) = await _path_with_steps(db, author=author)
    holder = await _student(db, code=code.code)
    await db.commit()

    resp = await client.post(
        f"/lms/admin/invite-codes/{code.id}/grants", headers=_headers(ops),
        json={"learning_path_id": str(path.id)},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["grant"]["product_type"] == "learning_path"

    rows = (await db.execute(
        select(Enrollment).where(Enrollment.user_id == holder.id)
    )).scalars().all()
    assert {r.course_id for r in rows} == {c1.id, c2.id}


@pytest.mark.asyncio
async def test_creating_a_program_grant_registers_existing_code_holders_immediately(db, client):
    """2026-09-15 — a "program" grant stores cohort_id (an LmsProgram is
    never assigned standalone, only resolved from a cohort) and is the
    *full* registration experience, not just the checklist: a real
    Registration row (register() -> sync_registration_lms(), same chain a
    human desk-registering someone goes through), which in turn produces
    the LmsProgramAssignment and enrolls every course item."""
    ops = await _ops(db)
    code = await _code(db)
    author = await _ops(db)
    cohort, lms_program = await _cohort_with_program(db, author=author)
    old_holder = await _student_with_contact(db, name="Old", code=code.code)
    unrelated = await _student_with_contact(db, name="Unrelated", code="OTHERCODE")
    await db.commit()

    resp = await client.post(
        f"/lms/admin/invite-codes/{code.id}/grants", headers=_headers(ops), json={"cohort_id": str(cohort.id)},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["accounts_enrolled"] == 1
    assert body["grant"]["product_type"] == "lms_program"
    assert body["grant"]["cohort_name"] == cohort.name
    assert body["grant"]["lms_program_name"] == lms_program.name

    registration = (await db.execute(
        select(Registration).where(Registration.contact_id == old_holder.contact_id, Registration.cohort_id == cohort.id)
    )).scalars().first()
    assert registration is not None
    assert registration.status == "registered"
    assert registration.registered_via == "invite_code"
    assert registration.payment_status == "waived"

    assignment = (await db.execute(
        select(LmsProgramAssignment).where(
            LmsProgramAssignment.user_id == old_holder.id, LmsProgramAssignment.cohort_id == cohort.id,
        )
    )).scalars().first()
    assert assignment is not None
    assert assignment.lms_program_id == lms_program.id
    assert assignment.registration_id == registration.id

    untouched = (await db.execute(
        select(Registration).where(Registration.contact_id == unrelated.contact_id)
    )).scalars().first()
    assert untouched is None
    untouched_assignment = (await db.execute(
        select(LmsProgramAssignment).where(LmsProgramAssignment.user_id == unrelated.id)
    )).scalars().first()
    assert untouched_assignment is None


@pytest.mark.asyncio
async def test_duplicate_grant_is_409(db, client):
    ops = await _ops(db)
    code = await _code(db)
    author = await _ops(db)
    course = await _course(db, author=author)
    await db.commit()

    first = await client.post(
        f"/lms/admin/invite-codes/{code.id}/grants", headers=_headers(ops), json={"course_id": str(course.id)},
    )
    assert first.status_code == 201

    dup = await client.post(
        f"/lms/admin/invite-codes/{code.id}/grants", headers=_headers(ops), json={"course_id": str(course.id)},
    )
    assert dup.status_code == http_status.HTTP_409_CONFLICT


@pytest.mark.asyncio
async def test_duplicate_program_grant_is_409(db, client):
    ops = await _ops(db)
    code = await _code(db)
    author = await _ops(db)
    cohort, _ = await _cohort_with_program(db, author=author)
    await db.commit()

    first = await client.post(
        f"/lms/admin/invite-codes/{code.id}/grants", headers=_headers(ops), json={"cohort_id": str(cohort.id)},
    )
    assert first.status_code == 201, first.text

    dup = await client.post(
        f"/lms/admin/invite-codes/{code.id}/grants", headers=_headers(ops), json={"cohort_id": str(cohort.id)},
    )
    assert dup.status_code == http_status.HTTP_409_CONFLICT


@pytest.mark.asyncio
async def test_grant_requires_exactly_one_of_course_path_or_cohort(db, client):
    ops = await _ops(db)
    code = await _code(db)
    author = await _ops(db)
    course = await _course(db, author=author)
    cohort, _ = await _cohort_with_program(db, author=author)
    await db.commit()

    neither = await client.post(f"/lms/admin/invite-codes/{code.id}/grants", headers=_headers(ops), json={})
    assert neither.status_code == http_status.HTTP_422_UNPROCESSABLE_ENTITY

    all_three = await client.post(
        f"/lms/admin/invite-codes/{code.id}/grants", headers=_headers(ops),
        json={"course_id": str(course.id), "cohort_id": str(cohort.id)},
    )
    assert all_three.status_code == http_status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_list_grants(db, client):
    ops = await _ops(db)
    code = await _code(db)
    author = await _ops(db)
    course = await _course(db, author=author)
    await db.commit()

    await client.post(
        f"/lms/admin/invite-codes/{code.id}/grants", headers=_headers(ops), json={"course_id": str(course.id)},
    )
    listed = await client.get(f"/lms/admin/invite-codes/{code.id}/grants", headers=_headers(ops))
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["course_id"] == str(course.id)


@pytest.mark.asyncio
async def test_deleting_a_grant_does_not_revoke_existing_access(db, client):
    ops = await _ops(db)
    code = await _code(db)
    author = await _ops(db)
    course = await _course(db, author=author)
    holder = await _student(db, code=code.code)
    await db.commit()

    created = await client.post(
        f"/lms/admin/invite-codes/{code.id}/grants", headers=_headers(ops), json={"course_id": str(course.id)},
    )
    grant_id = created.json()["grant"]["id"]

    deleted = await client.delete(
        f"/lms/admin/invite-codes/{code.id}/grants/{grant_id}", headers=_headers(ops),
    )
    assert deleted.status_code == 204

    still_there = (await db.execute(
        select(InvitationCodeGrant).where(InvitationCodeGrant.id == uuid.UUID(grant_id))
    )).scalars().first()
    assert still_there is None

    enrolled = (await db.execute(
        select(Enrollment).where(Enrollment.user_id == holder.id, Enrollment.course_id == course.id)
    )).scalars().first()
    assert enrolled is not None and enrolled.status == "active", "removing the rule never revokes what it already granted"


# ── signup-time auto-enrol ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_new_signup_on_a_granted_code_is_auto_enrolled(db, client):
    ops = await _ops(db)
    code = await _code(db, code="GRANTBATCH")
    author = await _ops(db)
    course = await _course(db, author=author)
    await db.commit()

    await client.post(
        f"/lms/admin/invite-codes/{code.id}/grants", headers=_headers(ops), json={"course_id": str(course.id)},
    )

    resp = await client.post("/auth/signup", json={
        "phone": "+971501234567",
        "invite_code": "grantbatch",
        "full_name": "Fresh Signup", "email": "freshsignup@example.com", "password": "pass-fresh",
    })
    assert resp.status_code == http_status.HTTP_201_CREATED, resp.text

    user = (await db.execute(select(User).where(User.email == "freshsignup@example.com"))).scalars().first()
    enrolled = (await db.execute(
        select(Enrollment).where(Enrollment.user_id == user.id, Enrollment.course_id == course.id)
    )).scalars().first()
    assert enrolled is not None
    assert enrolled.status == "active" and enrolled.source == "invite_code"


@pytest.mark.asyncio
async def test_new_signup_on_a_program_granted_code_is_assigned(db, client):
    ops = await _ops(db)
    code = await _code(db, code="PROGRAMBATCH")
    author = await _ops(db)
    cohort, lms_program = await _cohort_with_program(db, author=author)
    await db.commit()

    await client.post(
        f"/lms/admin/invite-codes/{code.id}/grants", headers=_headers(ops), json={"cohort_id": str(cohort.id)},
    )

    resp = await client.post("/auth/signup", json={
        "phone": "+971501234567",
        "invite_code": "programbatch",
        "full_name": "Program Signup", "email": "programsignup@example.com", "password": "pass-fresh",
    })
    assert resp.status_code == http_status.HTTP_201_CREATED, resp.text

    user = (await db.execute(select(User).where(User.email == "programsignup@example.com"))).scalars().first()
    registration = (await db.execute(
        select(Registration).where(Registration.contact_id == user.contact_id, Registration.cohort_id == cohort.id)
    )).scalars().first()
    assert registration is not None
    assert registration.registered_via == "invite_code"

    assignment = (await db.execute(
        select(LmsProgramAssignment).where(
            LmsProgramAssignment.user_id == user.id, LmsProgramAssignment.cohort_id == cohort.id,
        )
    )).scalars().first()
    assert assignment is not None
    assert assignment.lms_program_id == lms_program.id


# ── learning path bulk grant ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bulk_grant_path_by_role_enrols_every_step(db, client):
    ops = await _ops(db)
    author = await _ops(db)
    path, (c1, c2) = await _path_with_steps(db, author=author)
    facilitator = User(
        id=uuid.uuid4(), full_name="Facil", email=f"facil-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="x", roles=["facilitator"], status="active",
    )
    db.add(facilitator)
    await db.commit()

    resp = await client.post(
        f"/lms/admin/learning-paths/{path.id}/enrollments/bulk", headers=_headers(ops),
        json={"role": "facilitator"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["granted"] == 1

    rows = (await db.execute(
        select(Enrollment).where(Enrollment.user_id == facilitator.id)
    )).scalars().all()
    assert {r.course_id for r in rows} == {c1.id, c2.id}


@pytest.mark.asyncio
async def test_bulk_grant_path_counts_partial_owner_as_already_enrolled(db, client):
    ops = await _ops(db)
    author = await _ops(db)
    path, (c1, c2) = await _path_with_steps(db, author=author)
    facilitator = User(
        id=uuid.uuid4(), full_name="Facil2", email=f"facil2-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="x", roles=["facilitator"], status="active",
    )
    db.add(facilitator)
    await db.flush()
    db.add(Enrollment(id=uuid.uuid4(), user_id=facilitator.id, course_id=c1.id, source="ops", status="active"))
    await db.commit()

    resp = await client.post(
        f"/lms/admin/learning-paths/{path.id}/enrollments/bulk", headers=_headers(ops),
        json={"role": "facilitator"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["granted"] == 1  # not fully owned yet, so still gets the rest granted

    rows = (await db.execute(
        select(Enrollment).where(Enrollment.user_id == facilitator.id)
    )).scalars().all()
    assert {r.course_id for r in rows} == {c1.id, c2.id}


@pytest.mark.asyncio
async def test_bulk_grant_path_with_no_steps_is_400(db, client):
    ops = await _ops(db)
    author = await _ops(db)
    path = LearningPath(id=uuid.uuid4(), title="Empty", created_by=author.id, is_published=True)
    db.add(path)
    await db.commit()

    resp = await client.post(
        f"/lms/admin/learning-paths/{path.id}/enrollments/bulk", headers=_headers(ops),
        json={"role": "facilitator"},
    )
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST

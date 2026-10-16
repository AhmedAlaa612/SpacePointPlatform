"""Tests for multi-invite code redemption and post-signup ledger (2026-10).

Covers:
1. Signup without code, then post-signup redemption of program/cohort code.
2. Existing student redeeming a second program code (both cohorts active and searchable).
3. Idempotent redemption of the same code twice (no duplicate records or used_count increments).
4. Redeeming an observer code converts student to observer (roles, card_id prefix, checklist mode).
5. Retroactive invite code grants apply to users who redeemed via UserInvitationCode even if
   their scalar users.invitation_code_used was overwritten by a newer code.
"""

import uuid
import pytest
from fastapi import status as http_status
from sqlalchemy import select, func

from app.core.security import create_access_token
from app.models.instructors.invitation_code import InvitationCode
from app.models.lms import Course, Enrollment
from app.models.lms.invite_grant import InvitationCodeGrant, UserInvitationCode
from app.models.lms.program import LmsProgram, LmsProgramAssignment, LmsProgramItem
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.models.user import User
from app.services.documents.card_id import format_card_id
from app.services.lms.program import assign_lms_program


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _ops(db) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name="Ops Admin",
        email=f"ops-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        roles=["operations"],
        status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _student_with_contact(db, *, name="Student", code=None, roles=None, card_number=None) -> User:
    contact = Contact(
        id=uuid.uuid4(),
        full_name=name,
        email=f"{name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}@example.com",
        contact_roles=["student"],
    )
    db.add(contact)
    await db.flush()
    user = User(
        id=uuid.uuid4(),
        full_name=name,
        email=contact.email,
        password_hash="x",
        roles=roles or ["student"],
        status="active",
        invitation_code_used=code,
        contact_id=contact.id,
        card_number=card_number,
    )
    db.add(user)
    await db.flush()
    return user


async def _code(db, *, code="BATCH1", kind="student", is_active=True, max_uses=100) -> InvitationCode:
    row = InvitationCode(
        id=uuid.uuid4(),
        code=code,
        kind=kind,
        is_active=is_active,
        max_uses=max_uses,
        used_count=0,
    )
    db.add(row)
    await db.flush()
    return row


async def _course(db, *, author) -> Course:
    course = Course(
        id=uuid.uuid4(),
        title=f"Course {uuid.uuid4().hex[:8]}",
        created_by=author.id,
        is_published=True,
    )
    db.add(course)
    await db.flush()
    return course


async def _cohort_with_program(db, *, author, name="Cohort") -> tuple[Cohort, LmsProgram, Course]:
    program = Program(
        id=uuid.uuid4(),
        code=f"PRG-{uuid.uuid4().hex[:8]}",
        name=f"Program for {name}",
        program_type="workshop",
        pricing_model="free",
        active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(
        id=uuid.uuid4(),
        program_id=program.id,
        name=name,
        status="running",
    )
    db.add(cohort)
    await db.flush()
    lms_program = LmsProgram(
        id=uuid.uuid4(),
        program_id=program.id,
        name=f"Checklist for {name}",
    )
    db.add(lms_program)
    await db.flush()
    course = await _course(db, author=author)
    item = LmsProgramItem(
        id=uuid.uuid4(),
        owner_type="program",
        owner_id=lms_program.id,
        position=1,
        item_type="course",
        title=course.title,
        course_id=course.id,
    )
    db.add(item)
    await db.flush()
    return cohort, lms_program, course


# ─────────────────────────────────────────────────────────────────────────────
# 1. Signup without code, then post-signup redemption of program code
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_signup_without_code_then_redeem_program_code(db, client):
    ops = await _ops(db)
    student = await _student_with_contact(db, name="SoloStudent", code=None)
    code = await _code(db, code="COHORT_A")
    cohort, lms_program, _ = await _cohort_with_program(db, author=ops, name="Cohort A")
    grant = InvitationCodeGrant(
        id=uuid.uuid4(),
        invitation_code_id=code.id,
        cohort_id=cohort.id,
        product_type="lms_program",
    )
    db.add(grant)
    await db.commit()

    resp = await client.post(
        "/lms/redeem-invite",
        headers=_headers(student),
        json={"code": "COHORT_A"},
    )
    assert resp.status_code == http_status.HTTP_200_OK, resp.text
    data = resp.json()
    assert data["code"] == "COHORT_A"
    assert data["already_redeemed"] is False
    assert data["redirect_to"].startswith("/learn/checklists/")

    # UserInvitationCode record created
    uic = (
        await db.execute(
            select(UserInvitationCode).where(
                UserInvitationCode.user_id == student.id,
                UserInvitationCode.invitation_code_id == code.id,
            )
        )
    ).scalars().first()
    assert uic is not None
    assert uic.code == "COHORT_A"

    # used_count incremented
    await db.refresh(code)
    assert code.used_count == 1

    # Registration created
    reg = (
        await db.execute(
            select(Registration).where(
                Registration.contact_id == student.contact_id,
                Registration.cohort_id == cohort.id,
            )
        )
    ).scalars().first()
    assert reg is not None

    # LmsProgramAssignment created
    assignment = (
        await db.execute(
            select(LmsProgramAssignment).where(
                LmsProgramAssignment.user_id == student.id,
                LmsProgramAssignment.cohort_id == cohort.id,
            )
        )
    ).scalars().first()
    assert assignment is not None
    assert data["redirect_to"] == f"/learn/checklists/{assignment.id}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Existing student redeems second program code
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_existing_student_redeems_second_program_code(db, client):
    ops = await _ops(db)
    code1 = await _code(db, code="BATCH1")
    cohort1, _, _ = await _cohort_with_program(db, author=ops, name="Cohort 1")
    db.add(
        InvitationCodeGrant(
            id=uuid.uuid4(),
            invitation_code_id=code1.id,
            cohort_id=cohort1.id,
            product_type="lms_program",
        )
    )

    code2 = await _code(db, code="BATCH2")
    cohort2, _, _ = await _cohort_with_program(db, author=ops, name="Cohort 2")
    db.add(
        InvitationCodeGrant(
            id=uuid.uuid4(),
            invitation_code_id=code2.id,
            cohort_id=cohort2.id,
            product_type="lms_program",
        )
    )

    student = await _student_with_contact(db, name="MultiStudent", code=None)
    await db.commit()

    # Redeem first code
    r1 = await client.post("/lms/redeem-invite", headers=_headers(student), json={"code": "BATCH1"})
    assert r1.status_code == http_status.HTTP_200_OK, r1.text

    # Redeem second code
    r2 = await client.post("/lms/redeem-invite", headers=_headers(student), json={"code": "BATCH2"})
    assert r2.status_code == http_status.HTTP_200_OK, r2.text

    # Verify student has active assignments in BOTH cohorts
    assignments = (
        await db.execute(
            select(LmsProgramAssignment).where(
                LmsProgramAssignment.user_id == student.id,
            )
        )
    ).scalars().all()
    assigned_cohort_ids = {a.cohort_id for a in assignments}
    assert cohort1.id in assigned_cohort_ids
    assert cohort2.id in assigned_cohort_ids

    # Verify search by invite_code=BATCH1 finds this student
    search1 = await client.get("/lms/admin/students?invite_code=BATCH1", headers=_headers(ops))
    assert search1.status_code == http_status.HTTP_200_OK, search1.text
    students_batch1 = [s["id"] for s in search1.json()]
    assert str(student.id) in students_batch1

    # Verify search by invite_code=BATCH2 finds this student
    search2 = await client.get("/lms/admin/students?invite_code=BATCH2", headers=_headers(ops))
    assert search2.status_code == http_status.HTTP_200_OK, search2.text
    students_batch2 = [s["id"] for s in search2.json()]
    assert str(student.id) in students_batch2

    # Verify GET /auth/me returns invitation_codes_used with both codes
    me_resp = await client.get("/auth/me", headers=_headers(student))
    assert me_resp.status_code == http_status.HTTP_200_OK, me_resp.text
    me_codes = [c["code"] for c in me_resp.json().get("invitation_codes_used", [])]
    assert "BATCH1" in me_codes
    assert "BATCH2" in me_codes


# ─────────────────────────────────────────────────────────────────────────────
# 3. Redeeming same code twice is idempotent
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_redeeming_same_code_twice_is_idempotent(db, client):
    code = await _code(db, code="IDEMPOTENT_CODE")
    student = await _student_with_contact(db, name="IdempotentStudent")
    await db.commit()

    # First redemption
    r1 = await client.post("/lms/redeem-invite", headers=_headers(student), json={"code": "IDEMPOTENT_CODE"})
    assert r1.status_code == http_status.HTTP_200_OK, r1.text
    assert r1.json()["already_redeemed"] is False

    # Second redemption
    r2 = await client.post("/lms/redeem-invite", headers=_headers(student), json={"code": "IDEMPOTENT_CODE"})
    assert r2.status_code == http_status.HTTP_200_OK, r2.text
    assert r2.json()["already_redeemed"] is True

    # used_count is still 1
    await db.refresh(code)
    assert code.used_count == 1

    # Only 1 UserInvitationCode row
    count = (
        await db.execute(
            select(func.count(UserInvitationCode.id)).where(
                UserInvitationCode.user_id == student.id,
                UserInvitationCode.invitation_code_id == code.id,
            )
        )
    ).scalar()
    assert count == 1


# ─────────────────────────────────────────────────────────────────────────────
# 4. Redeeming observer code converts student to observer
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_redeeming_observer_code_converts_student_to_observer(db, client):
    ops = await _ops(db)
    student = await _student_with_contact(db, name="FutureObserver", card_number=1050)
    cohort, lms_program, _ = await _cohort_with_program(db, author=ops, name="Observer Cohort")

    # Initially assigned in participant mode
    await assign_lms_program(
        db,
        user_id=student.id,
        cohort_id=cohort.id,
        mode="participant",
    )
    obs_code = await _code(db, code="OBSERVER_BATCH", kind="observer")
    await db.commit()

    # Verify initial card format is student
    assert format_card_id(student.card_number, student.roles).startswith("SP-ST-")

    # Redeem observer code
    resp = await client.post(
        "/lms/redeem-invite",
        headers=_headers(student),
        json={"code": "OBSERVER_BATCH"},
    )
    assert resp.status_code == http_status.HTTP_200_OK, resp.text
    data = resp.json()
    assert data["kind"] == "observer"
    assert "observer" in data["roles"]
    assert "student" not in data["roles"]

    # Student roles converted in DB
    await db.refresh(student)
    assert student.roles == ["observer"]

    # Card ID format converted to SP-OB-####-UAE
    assert format_card_id(student.card_number, student.roles).startswith("SP-OB-")

    # Existing LmsProgramAssignment converted to observer mode
    assignment = (
        await db.execute(
            select(LmsProgramAssignment).where(
                LmsProgramAssignment.user_id == student.id,
                LmsProgramAssignment.cohort_id == cohort.id,
            )
        )
    ).scalars().first()
    assert assignment is not None
    assert assignment.mode == "observer"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Retroactive grant applies to all multi-code holders
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_retroactive_grant_applies_to_all_multi_code_holders(db, client):
    ops = await _ops(db)
    author = await _ops(db)
    code1 = await _code(db, code="BATCH1")
    code2 = await _code(db, code="BATCH2")
    student = await _student_with_contact(db, name="RetroStudent")
    await db.commit()

    # Student redeems BATCH1 first, then BATCH2 second
    r1 = await client.post("/lms/redeem-invite", headers=_headers(student), json={"code": "BATCH1"})
    assert r1.status_code == http_status.HTTP_200_OK, r1.text

    r2 = await client.post("/lms/redeem-invite", headers=_headers(student), json={"code": "BATCH2"})
    assert r2.status_code == http_status.HTTP_200_OK, r2.text

    await db.refresh(student)
    # Scalar column was updated with latest code
    assert student.invitation_code_used == "BATCH2"

    # Now ops attaches a new course grant to BATCH1 (the FIRST code student redeemed)
    course = await _course(db, author=author)
    await db.commit()

    grant_resp = await client.post(
        f"/lms/admin/invite-codes/{code1.id}/grants",
        headers=_headers(ops),
        json={"course_id": str(course.id)},
    )
    assert grant_resp.status_code == http_status.HTTP_201_CREATED, grant_resp.text
    grant_data = grant_resp.json()
    assert grant_data["accounts_enrolled"] >= 1

    # Student is enrolled in the new course via retroactive grant
    enrollment = (
        await db.execute(
            select(Enrollment).where(
                Enrollment.user_id == student.id,
                Enrollment.course_id == course.id,
            )
        )
    ).scalars().first()
    assert enrollment is not None
    assert enrollment.status == "active"
    assert enrollment.source == "invite_code"

"""P7-7 (LMS Phase 2 Stage 7, 2026-08-11) — server-side step gating per
cohort, the S1 fix (Madar enforced page_access only in the browser; the
budget API endpoints had no dependency on it at all). Redis-free.
"""

import uuid

import pytest
from fastapi import HTTPException

from app.models.missions.design import DesignStepGate
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.models.user import User
from app.services.missions.design.gating import assert_step_unlocked, is_step_unlocked, resolve_student_cohort
from app.services.missions.verifiers.design import ensure_design


async def _user(db, *, roles=None, contact_id=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Gating User", email=f"gate-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=roles or ["student"], status="active", contact_id=contact_id,
    )
    db.add(user)
    await db.flush()
    return user


async def _cohort(db) -> Cohort:
    program = Program(
        id=uuid.uuid4(), code=f"GP-{uuid.uuid4().hex[:8]}", name="Gating Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Gating Cohort", status="running")
    db.add(cohort)
    await db.flush()
    return cohort


@pytest.mark.asyncio
async def test_ungated_steps_are_always_unlocked(db):
    cohort = await _cohort(db)
    assert await is_step_unlocked(db, cohort_id=cohort.id, step_key="components") is True
    assert await is_step_unlocked(db, cohort_id=cohort.id, step_key="conops") is True


@pytest.mark.asyncio
async def test_gated_step_defaults_to_locked_when_no_row_exists(db):
    cohort = await _cohort(db)
    assert await is_step_unlocked(db, cohort_id=cohort.id, step_key="data_budget") is False


@pytest.mark.asyncio
async def test_gated_step_unlocked_once_a_row_says_so(db):
    cohort = await _cohort(db)
    db.add(DesignStepGate(cohort_id=cohort.id, step_key="data_budget", is_unlocked=True))
    await db.flush()
    assert await is_step_unlocked(db, cohort_id=cohort.id, step_key="data_budget") is True


@pytest.mark.asyncio
async def test_no_cohort_means_never_gated_standalone_attempt(db):
    assert await is_step_unlocked(db, cohort_id=None, step_key="data_budget") is True


@pytest.mark.asyncio
async def test_assert_step_unlocked_raises_403_when_locked(db):
    cohort = await _cohort(db)
    with pytest.raises(HTTPException) as exc:
        await assert_step_unlocked(
            db, design=type("D", (), {"cohort_id": cohort.id})(), step_key="power_budget",
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_resolve_student_cohort_uses_the_most_recent_active_registration(db):
    contact = Contact(id=uuid.uuid4(), full_name="Gating Student", contact_roles=["student"])
    db.add(contact)
    await db.flush()
    student = await _user(db, contact_id=contact.id)
    cohort = await _cohort(db)
    db.add(Registration(
        id=uuid.uuid4(), contact_id=contact.id, cohort_id=cohort.id, status="registered",
        ticket_token=uuid.uuid4().hex, registered_via="desk", payment_status="waived",
    ))
    await db.flush()

    resolved = await resolve_student_cohort(db, user_id=student.id)
    assert resolved == cohort.id


@pytest.mark.asyncio
async def test_resolve_student_cohort_is_none_without_a_registration(db):
    student = await _user(db)
    assert await resolve_student_cohort(db, user_id=student.id) is None

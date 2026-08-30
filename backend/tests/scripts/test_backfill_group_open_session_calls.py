"""2026-08-30: pre-existing single-session open calls get folded into a
standing CohortCall, the same way a fresh open_call already does."""

import uuid
from datetime import date

import pytest
from sqlalchemy import select

from app.models.sessions.cohort import Cohort
from app.models.sessions.cohort_call import CohortCall
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionCallTarget
from app.models.sessions.session_call import SessionCall
from app.models.user import User
from scripts.backfill_group_open_session_calls import backfill_group_open_session_calls


async def _make_cohort_with_session(db, **session_overrides) -> tuple[Cohort, Session]:
    program = Program(
        id=uuid.uuid4(), code=f"BACKFILL-{uuid.uuid4().hex[:8]}", name="P",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="C", status="planned", visibility="public")
    db.add(cohort)
    await db.flush()
    defaults = dict(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 8, 10))
    defaults.update(session_overrides)
    session = Session(**defaults)
    db.add(session)
    await db.flush()
    return cohort, session


async def _make_user(db, roles: list[str]) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Test User", email=f"{uuid.uuid4().hex}@example.com",
        password_hash="x", roles=roles,
    )
    db.add(user)
    await db.flush()
    return user


async def _make_ungrouped_open_call(db, session_id, target_user_ids: list[uuid.UUID] | None = None) -> SessionCall:
    """A session call as it would have looked before this change — never
    goes through staffing.open_call, so cohort_call_id stays NULL."""
    call = SessionCall(id=uuid.uuid4(), session_id=session_id, status="open")
    db.add(call)
    await db.flush()
    for user_id in target_user_ids or []:
        db.add(SessionCallTarget(id=uuid.uuid4(), call_id=call.id, session_id=session_id, user_id=user_id))
    await db.flush()
    return call


@pytest.mark.asyncio
async def test_backfill_groups_an_ungrouped_open_call(db):
    _, session = await _make_cohort_with_session(db)
    call = await _make_ungrouped_open_call(db, session.id)

    grouped = await backfill_group_open_session_calls(db)

    assert grouped == 1
    await db.refresh(call)
    assert call.cohort_call_id is not None
    cohort_call = await db.get(CohortCall, call.cohort_call_id)
    assert cohort_call.status == "open"


@pytest.mark.asyncio
async def test_backfill_merges_two_public_ungrouped_calls_in_the_same_cohort(db):
    cohort, s1 = await _make_cohort_with_session(db, meeting_date=date(2026, 8, 10))
    s2 = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 8, 17))
    db.add(s2)
    await db.flush()
    call1 = await _make_ungrouped_open_call(db, s1.id)
    call2 = await _make_ungrouped_open_call(db, s2.id)

    grouped = await backfill_group_open_session_calls(db)

    assert grouped == 2
    await db.refresh(call1)
    await db.refresh(call2)
    assert call1.cohort_call_id == call2.cohort_call_id


@pytest.mark.asyncio
async def test_backfill_keeps_a_targeted_call_separate_from_a_public_one(db):
    cohort, s1 = await _make_cohort_with_session(db, meeting_date=date(2026, 8, 10))
    s2 = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 8, 17))
    db.add(s2)
    await db.flush()
    targeted_instructor = await _make_user(db, ["instructor"])
    call1 = await _make_ungrouped_open_call(db, s1.id)  # public
    call2 = await _make_ungrouped_open_call(db, s2.id, target_user_ids=[targeted_instructor.id])

    await backfill_group_open_session_calls(db)

    await db.refresh(call1)
    await db.refresh(call2)
    assert call1.cohort_call_id != call2.cohort_call_id


@pytest.mark.asyncio
async def test_backfill_is_idempotent(db):
    _, session = await _make_cohort_with_session(db)
    call = await _make_ungrouped_open_call(db, session.id)

    first = await backfill_group_open_session_calls(db)
    original_cohort_call_id = call.cohort_call_id
    second = await backfill_group_open_session_calls(db)

    assert first == 1
    assert second == 0
    assert call.cohort_call_id == original_cohort_call_id


@pytest.mark.asyncio
async def test_backfill_ignores_closed_calls(db):
    _, session = await _make_cohort_with_session(db)
    call = SessionCall(id=uuid.uuid4(), session_id=session.id, status="closed")
    db.add(call)
    await db.flush()

    grouped = await backfill_group_open_session_calls(db)

    assert grouped == 0
    await db.refresh(call)
    assert call.cohort_call_id is None

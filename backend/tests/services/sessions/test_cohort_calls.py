"""Tests for the cohort-level standing call grouping (2026-08-01 follow-up to
W4 S4-1's per-session marketplace, see services/sessions/staffing.py's
`open_cohort_call`/`list_cohort_calls`/`close_cohort_call`).

Covers the four mandatory cases from the phase plan:
  (a) opening over a chosen session-id subset only touches those sessions,
      reporting (not raising on) any that aren't currently unstaffed;
  (b) closing for a subset leaves the rest open and the CohortCall itself
      still "open";
  (c) closing the last remaining open session flips CohortCall to "closed";
  (d) a session's own fully independent call (opened directly, no
      cohort_call_id) is unaffected by a cohort call closing alongside it.
"""

import uuid
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.sessions.cohort import Cohort
from app.models.sessions.cohort_call import CohortCall
from app.models.sessions.program import Program
from app.models.sessions.session import Session
from app.models.sessions.session_call import SessionCall
from app.models.user import User
from app.services.sessions import staffing


async def _make_cohort(db, **overrides) -> Cohort:
    program = Program(
        id=uuid.uuid4(), code=f"CCALL-{uuid.uuid4().hex[:8]}", name="Cohort Call Test Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    defaults = dict(id=uuid.uuid4(), program_id=program.id, name="Cohort Call Test Cohort", status="planned", visibility="public")
    defaults.update(overrides)
    cohort = Cohort(**defaults)
    db.add(cohort)
    await db.flush()
    return cohort


async def _make_session(db, cohort_id, **overrides) -> Session:
    defaults = dict(id=uuid.uuid4(), cohort_id=cohort_id, meeting_date=date(2026, 8, 10))
    defaults.update(overrides)
    session = Session(**defaults)
    db.add(session)
    await db.flush()
    return session


async def _make_user(db, roles: list[str] = ("instructor",), **overrides) -> User:
    defaults = dict(
        id=uuid.uuid4(), full_name="Test User", email=f"{uuid.uuid4().hex}@example.com",
        password_hash="x", roles=list(roles),
    )
    defaults.update(overrides)
    user = User(**defaults)
    db.add(user)
    await db.flush()
    return user


# ── (a) opening over a chosen subset ────────────────────────────────────────

@pytest.mark.asyncio
async def test_open_cohort_call_only_opens_the_given_subset(db):
    cohort = await _make_cohort(db)
    s1 = await _make_session(db, cohort.id, meeting_date=date(2026, 8, 10))
    s2 = await _make_session(db, cohort.id, meeting_date=date(2026, 8, 17))
    s3_untouched = await _make_session(db, cohort.id, meeting_date=date(2026, 8, 24))

    call, succeeded, failed = await staffing.open_cohort_call(
        db, cohort.id, session_ids=[s1.id, s2.id],
    )

    assert set(succeeded) == {s1.id, s2.id}
    assert failed == []
    await db.refresh(s1)
    await db.refresh(s2)
    await db.refresh(s3_untouched)
    assert s1.staffing_status == "open_call"
    assert s2.staffing_status == "open_call"
    assert s3_untouched.staffing_status == "unstaffed"  # not in the subset — untouched

    # The two opened sessions' calls are grouped under the new CohortCall.
    grouped = (await db.execute(
        select(SessionCall).where(SessionCall.cohort_call_id == call.id)
    )).scalars().all()
    assert {sc.session_id for sc in grouped} == {s1.id, s2.id}
    assert call.status == "open"


@pytest.mark.asyncio
async def test_open_cohort_call_reports_already_staffed_session_as_failed(db):
    """A session in the requested subset that isn't currently unstaffed
    (open_call's own 409) is reported back, not allowed to blow up the rest
    of the batch — same tolerate-and-report contract as bulk_open_call."""
    cohort = await _make_cohort(db)
    ok = await _make_session(db, cohort.id, meeting_date=date(2026, 8, 10))
    already_staffed = await _make_session(db, cohort.id, meeting_date=date(2026, 8, 17), staffing_status="staffed")

    call, succeeded, failed = await staffing.open_cohort_call(
        db, cohort.id, session_ids=[ok.id, already_staffed.id],
    )

    assert succeeded == [ok.id]
    assert len(failed) == 1
    assert failed[0]["session_id"] == already_staffed.id
    await db.refresh(already_staffed)
    assert already_staffed.staffing_status == "staffed"  # untouched by the failure


@pytest.mark.asyncio
async def test_open_cohort_call_reports_session_not_in_cohort(db):
    cohort_a = await _make_cohort(db, name="A")
    cohort_b = await _make_cohort(db, name="B")
    in_a = await _make_session(db, cohort_a.id)
    in_b = await _make_session(db, cohort_b.id)

    call, succeeded, failed = await staffing.open_cohort_call(
        db, cohort_a.id, session_ids=[in_a.id, in_b.id],
    )

    assert succeeded == [in_a.id]
    assert len(failed) == 1
    assert failed[0]["session_id"] == in_b.id


@pytest.mark.asyncio
async def test_open_cohort_call_defaults_to_every_unstaffed_session(db):
    """session_ids omitted falls back to open_call_for_cohort's existing
    default — every currently-unstaffed session in the cohort."""
    cohort = await _make_cohort(db)
    unstaffed = await _make_session(db, cohort.id, meeting_date=date(2026, 8, 10))
    staffed = await _make_session(db, cohort.id, meeting_date=date(2026, 8, 17), staffing_status="staffed")

    call, succeeded, failed = await staffing.open_cohort_call(db, cohort.id)

    assert succeeded == [unstaffed.id]
    assert failed == []


@pytest.mark.asyncio
async def test_open_cohort_call_404s_on_missing_cohort(db):
    with pytest.raises(HTTPException) as exc:
        await staffing.open_cohort_call(db, uuid.uuid4())
    assert exc.value.status_code == 404


# ── (b) / (c) closing a subset vs. closing the last one ─────────────────────

@pytest.mark.asyncio
async def test_close_cohort_call_for_a_subset_leaves_the_rest_open(db):
    cohort = await _make_cohort(db)
    s1 = await _make_session(db, cohort.id, meeting_date=date(2026, 8, 10))
    s2 = await _make_session(db, cohort.id, meeting_date=date(2026, 8, 17))
    call, succeeded, failed = await staffing.open_cohort_call(db, cohort.id, session_ids=[s1.id, s2.id])
    assert failed == []

    await staffing.close_cohort_call(db, cohort.id, call.id, session_ids=[s1.id])

    await db.refresh(s1)
    await db.refresh(s2)
    assert s1.staffing_status == "unstaffed"  # its only call just closed
    assert s2.staffing_status == "open_call"  # untouched

    await db.refresh(call)
    assert call.status == "open"  # s2's call is still open under it
    assert call.closed_at is None


@pytest.mark.asyncio
async def test_close_cohort_call_closing_the_last_open_session_flips_it_closed(db):
    cohort = await _make_cohort(db)
    s1 = await _make_session(db, cohort.id, meeting_date=date(2026, 8, 10))
    s2 = await _make_session(db, cohort.id, meeting_date=date(2026, 8, 17))
    call, succeeded, failed = await staffing.open_cohort_call(db, cohort.id, session_ids=[s1.id, s2.id])
    assert failed == []

    await staffing.close_cohort_call(db, cohort.id, call.id, session_ids=[s1.id])
    await staffing.close_cohort_call(db, cohort.id, call.id, session_ids=[s2.id])

    await db.refresh(call)
    assert call.status == "closed"
    assert call.closed_at is not None


@pytest.mark.asyncio
async def test_close_cohort_call_with_no_session_ids_closes_everything(db):
    cohort = await _make_cohort(db)
    s1 = await _make_session(db, cohort.id, meeting_date=date(2026, 8, 10))
    s2 = await _make_session(db, cohort.id, meeting_date=date(2026, 8, 17))
    call, _, failed = await staffing.open_cohort_call(db, cohort.id, session_ids=[s1.id, s2.id])
    assert failed == []

    await staffing.close_cohort_call(db, cohort.id, call.id)

    await db.refresh(s1)
    await db.refresh(s2)
    assert s1.staffing_status == "unstaffed"
    assert s2.staffing_status == "unstaffed"
    await db.refresh(call)
    assert call.status == "closed"


@pytest.mark.asyncio
async def test_close_cohort_call_404s_on_wrong_cohort(db):
    cohort_a = await _make_cohort(db, name="A")
    cohort_b = await _make_cohort(db, name="B")
    s = await _make_session(db, cohort_a.id)
    call, _, _ = await staffing.open_cohort_call(db, cohort_a.id, session_ids=[s.id])

    with pytest.raises(HTTPException) as exc:
        await staffing.close_cohort_call(db, cohort_b.id, call.id)
    assert exc.value.status_code == 404


# ── (d) an independent session-level call is unaffected ─────────────────────

@pytest.mark.asyncio
async def test_independent_session_call_survives_cohort_call_close(db):
    """A session can run its own completely independent call (opened
    directly via open_call, no cohort_call_id) alongside a cohort call —
    closing the cohort call must not touch it."""
    cohort = await _make_cohort(db)
    shared_session = await _make_session(db, cohort.id, meeting_date=date(2026, 8, 10))

    cohort_call, succeeded, failed = await staffing.open_cohort_call(
        db, cohort.id, session_ids=[shared_session.id],
    )
    assert failed == []
    assert succeeded == [shared_session.id]

    # The session is already open_call (from the cohort call), so a second,
    # independent call is opened via set_call... actually open_call refuses
    # once staffed, but open_call_status is open_call already which is fine
    # to add another concurrent call to (2026-08-01 multi-call support).
    independent_call = await staffing._create_call(
        db, session_id=shared_session.id, target_user_ids=None, actor_user_id=None, label="Independent",
    )
    assert independent_call.cohort_call_id is None

    await staffing.close_cohort_call(db, cohort.id, cohort_call.id)

    await db.refresh(independent_call)
    assert independent_call.status == "open"  # untouched by the cohort call closing

    # The session itself stays open_call because the independent call is
    # still open, even though the cohort-grouped call was just closed.
    await db.refresh(shared_session)
    assert shared_session.staffing_status == "open_call"


# ── list_cohort_calls ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_cohort_calls_shapes_targets_and_sessions(db):
    cohort = await _make_cohort(db)
    s1 = await _make_session(db, cohort.id, meeting_date=date(2026, 8, 10))
    target_user = await _make_user(db)

    call, succeeded, failed = await staffing.open_cohort_call(
        db, cohort.id, session_ids=[s1.id], target_user_ids=[target_user.id],
    )
    assert failed == []

    rows = await staffing.list_cohort_calls(db, cohort.id)
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == call.id
    assert row["status"] == "open"
    assert row["target_user_ids"] == [target_user.id]
    assert len(row["sessions"]) == 1
    assert row["sessions"][0]["session_id"] == s1.id
    assert row["sessions"][0]["status"] == "open"
    assert row["sessions"][0]["staffing_status"] == "open_call"


@pytest.mark.asyncio
async def test_list_cohort_calls_empty_for_cohort_with_none(db):
    cohort = await _make_cohort(db)
    assert await staffing.list_cohort_calls(db, cohort.id) == []

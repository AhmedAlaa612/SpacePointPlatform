"""Mandatory tests for V2 W4 S4-1 (see MASTER_EXECUTION_PLAN_V2.md):
transition matrix (allowed + rejected per role); interest without open_call
rejected; select from a non-interested user allowed (ops override) but
flagged in the response. Session-scoped throughout, not cohort-scoped — see
the plan's W4 discoveries entry for why.
"""

import uuid
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.sessions.cohort import Cohort
from app.models.sessions.instructor_interest import InstructorInterest
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor
from app.models.spine.touchpoint import Touchpoint
from app.models.user import User
from app.services.sessions import staffing


async def _make_cohort_with_session(db, **session_overrides) -> tuple[Cohort, Session]:
    program = Program(
        id=uuid.uuid4(), code=f"STAFF-{uuid.uuid4().hex[:8]}", name="Staffing Test Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Staffing Test Cohort", status="planned", visibility="public")
    db.add(cohort)
    await db.flush()
    defaults = dict(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 8, 10))
    defaults.update(session_overrides)
    session = Session(**defaults)
    db.add(session)
    await db.flush()
    return cohort, session


async def _make_user(db, roles: list[str], **overrides) -> User:
    defaults = dict(
        id=uuid.uuid4(), full_name="Test User", email=f"{uuid.uuid4().hex}@example.com",
        password_hash="x", roles=roles,
    )
    defaults.update(overrides)
    user = User(**defaults)
    db.add(user)
    await db.flush()
    return user


# ── open_call / reopen transition matrix ────────────────────────────────────

@pytest.mark.asyncio
async def test_open_call_from_unstaffed_succeeds(db):
    _, session = await _make_cohort_with_session(db)
    result = await staffing.open_call(db, session.id)
    assert result.staffing_status == "open_call"


@pytest.mark.asyncio
async def test_open_call_from_open_call_rejected(db):
    _, session = await _make_cohort_with_session(db, staffing_status="open_call")
    with pytest.raises(HTTPException) as exc:
        await staffing.open_call(db, session.id)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_open_call_from_staffed_rejected(db):
    _, session = await _make_cohort_with_session(db, staffing_status="staffed")
    with pytest.raises(HTTPException) as exc:
        await staffing.open_call(db, session.id)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_reopen_from_staffed_succeeds(db):
    _, session = await _make_cohort_with_session(db, staffing_status="staffed")
    result = await staffing.reopen(db, session.id)
    assert result.staffing_status == "open_call"


@pytest.mark.asyncio
async def test_reopen_from_unstaffed_rejected(db):
    _, session = await _make_cohort_with_session(db)
    with pytest.raises(HTTPException) as exc:
        await staffing.reopen(db, session.id)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_reopen_keeps_existing_assignments(db):
    _, session = await _make_cohort_with_session(db, staffing_status="staffed")
    instructor = await _make_user(db, ["instructor"])
    db.add(SessionInstructor(id=uuid.uuid4(), session_id=session.id, user_id=instructor.id, role="lead"))
    await db.flush()

    await staffing.reopen(db, session.id)

    assignment = (await db.execute(
        select(SessionInstructor).where(SessionInstructor.session_id == session.id)
    )).scalars().first()
    assert assignment is not None  # not removed by reopening


@pytest.mark.asyncio
async def test_open_call_for_cohort_only_opens_unstaffed_sessions(db):
    cohort, s1 = await _make_cohort_with_session(db, meeting_date=date(2026, 8, 10))
    s2 = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 8, 17), staffing_status="staffed")
    db.add(s2)
    await db.flush()

    opened = await staffing.open_call_for_cohort(db, cohort.id)

    assert len(opened) == 1
    assert opened[0].id == s1.id
    await db.refresh(s2)
    assert s2.staffing_status == "staffed"  # untouched


# ── register_interest / withdraw_interest ───────────────────────────────────

@pytest.mark.asyncio
async def test_register_interest_requires_open_call(db):
    _, session = await _make_cohort_with_session(db)  # unstaffed
    instructor = await _make_user(db, ["instructor"])
    with pytest.raises(HTTPException) as exc:
        await staffing.register_interest(db, session.id, instructor)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_register_interest_rejects_non_instructor_role(db):
    _, session = await _make_cohort_with_session(db, staffing_status="open_call")
    intern = await _make_user(db, ["intern"])
    with pytest.raises(HTTPException) as exc:
        await staffing.register_interest(db, session.id, intern)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_register_interest_allows_instructor_and_facilitator(db):
    _, session = await _make_cohort_with_session(db, staffing_status="open_call")
    instructor = await _make_user(db, ["instructor"])
    facilitator = await _make_user(db, ["facilitator"])

    await staffing.register_interest(db, session.id, instructor, note="I'd love this one")
    await staffing.register_interest(db, session.id, facilitator)

    interests = await staffing.list_interest(db, session.id)
    assert len(interests) == 2


@pytest.mark.asyncio
async def test_register_interest_twice_updates_note_not_duplicates(db):
    _, session = await _make_cohort_with_session(db, staffing_status="open_call")
    instructor = await _make_user(db, ["instructor"])

    await staffing.register_interest(db, session.id, instructor, note="first note")
    await staffing.register_interest(db, session.id, instructor, note="updated note")

    interests = await staffing.list_interest(db, session.id)
    assert len(interests) == 1
    assert interests[0][0].note == "updated note"


@pytest.mark.asyncio
async def test_withdraw_interest_removes_it(db):
    _, session = await _make_cohort_with_session(db, staffing_status="open_call")
    instructor = await _make_user(db, ["instructor"])
    await staffing.register_interest(db, session.id, instructor)

    await staffing.withdraw_interest(db, session.id, instructor)

    assert await staffing.list_interest(db, session.id) == []


# ── select_instructors ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_select_instructors_writes_assignment_and_flips_to_staffed(db):
    _, session = await _make_cohort_with_session(db, staffing_status="open_call")
    instructor = await _make_user(db, ["instructor"])
    await staffing.register_interest(db, session.id, instructor)

    assignments, without_interest = await staffing.select_instructors(db, session.id, [instructor.id], "lead")

    assert len(assignments) == 1
    assert without_interest == []
    await db.refresh(session)
    assert session.staffing_status == "staffed"


@pytest.mark.asyncio
async def test_select_instructors_supports_multiple_with_select_all(db):
    _, session = await _make_cohort_with_session(db, staffing_status="open_call")
    a = await _make_user(db, ["instructor"])
    b = await _make_user(db, ["instructor"])
    await staffing.register_interest(db, session.id, a)
    await staffing.register_interest(db, session.id, b)

    assignments, without_interest = await staffing.select_instructors(db, session.id, [a.id, b.id], "co")

    assert len(assignments) == 2
    assert without_interest == []


@pytest.mark.asyncio
async def test_select_instructor_without_interest_allowed_but_flagged(db):
    """Mandatory case from the spec: ops can select someone who never
    registered interest — allowed, not rejected, but the caller finds out."""
    _, session = await _make_cohort_with_session(db, staffing_status="open_call")
    never_interested = await _make_user(db, ["instructor"])

    assignments, without_interest = await staffing.select_instructors(db, session.id, [never_interested.id], "lead")

    assert len(assignments) == 1
    assert without_interest == [never_interested.id]


@pytest.mark.asyncio
async def test_select_instructors_requires_at_least_one(db):
    _, session = await _make_cohort_with_session(db, staffing_status="open_call")
    with pytest.raises(HTTPException) as exc:
        await staffing.select_instructors(db, session.id, [], "lead")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_select_instructors_writes_touchpoint_when_contact_linked(db):
    from app.models.spine.contact import Contact

    contact = Contact(id=uuid.uuid4(), full_name="Linked Instructor", contact_roles=["instructor"])
    db.add(contact)
    await db.flush()
    _, session = await _make_cohort_with_session(db, staffing_status="open_call")
    instructor = await _make_user(db, ["instructor"], contact_id=contact.id)

    await staffing.select_instructors(db, session.id, [instructor.id], "lead")

    touchpoint = (await db.execute(
        select(Touchpoint).where(Touchpoint.contact_id == contact.id, Touchpoint.touchpoint_type == "staffing")
    )).scalars().first()
    assert touchpoint is not None
    assert str(session.id) in touchpoint.raw_platform_id


@pytest.mark.asyncio
async def test_select_instructors_no_touchpoint_when_user_not_linked_to_a_contact(db):
    """Must not crash just because a user hasn't been backfilled to a
    contact yet — best-effort, not a hard requirement."""
    _, session = await _make_cohort_with_session(db, staffing_status="open_call")
    instructor = await _make_user(db, ["instructor"])  # contact_id left None
    assert instructor.contact_id is None

    assignments, _ = await staffing.select_instructors(db, session.id, [instructor.id], "lead")
    assert len(assignments) == 1  # didn't raise


@pytest.mark.asyncio
async def test_remove_instructor_deletes_assignment(db):
    _, session = await _make_cohort_with_session(db, staffing_status="staffed")
    instructor = await _make_user(db, ["instructor"])
    db.add(SessionInstructor(id=uuid.uuid4(), session_id=session.id, user_id=instructor.id, role="lead"))
    await db.flush()

    await staffing.remove_instructor(db, session.id, instructor.id)

    remaining = (await db.execute(
        select(SessionInstructor).where(SessionInstructor.session_id == session.id)
    )).scalars().first()
    assert remaining is None


# ── list_available_sessions / list_my_sessions (S4-3) ───────────────────────

@pytest.mark.asyncio
async def test_list_available_sessions_only_shows_open_call(db):
    _, open_session = await _make_cohort_with_session(db, staffing_status="open_call")
    _, unstaffed_session = await _make_cohort_with_session(db)
    _, staffed_session = await _make_cohort_with_session(db, staffing_status="staffed")
    instructor = await _make_user(db, ["instructor"])

    rows = await staffing.list_available_sessions(db, instructor)

    ids = {s.id for s, _, _, _, _ in rows}
    assert open_session.id in ids
    assert unstaffed_session.id not in ids
    assert staffed_session.id not in ids


@pytest.mark.asyncio
async def test_list_available_sessions_reports_interest_count_and_my_interest(db):
    _, session = await _make_cohort_with_session(db, staffing_status="open_call")
    me = await _make_user(db, ["instructor"])
    someone_else = await _make_user(db, ["instructor"])
    await staffing.register_interest(db, session.id, me, note="pick me")
    await staffing.register_interest(db, session.id, someone_else)

    rows = await staffing.list_available_sessions(db, me)

    assert len(rows) == 1
    _, _, _, count, my_interest = rows[0]
    assert count == 2
    assert my_interest is not None
    assert my_interest.note == "pick me"


@pytest.mark.asyncio
async def test_list_available_sessions_empty_when_nothing_open(db):
    assert await staffing.list_available_sessions(db, await _make_user(db, ["instructor"])) == []


@pytest.mark.asyncio
async def test_list_my_sessions_only_shows_assigned(db):
    _, assigned_session = await _make_cohort_with_session(db, staffing_status="staffed")
    _, other_session = await _make_cohort_with_session(db, staffing_status="staffed")
    instructor = await _make_user(db, ["instructor"])
    db.add(SessionInstructor(id=uuid.uuid4(), session_id=assigned_session.id, user_id=instructor.id, role="co"))
    await db.flush()

    rows = await staffing.list_my_sessions(db, instructor)

    assert len(rows) == 1
    s, _, _, role = rows[0]
    assert s.id == assigned_session.id
    assert role == "co"
    assert other_session.id not in {r[0].id for r in rows}

"""Cohort-level kit defaults (Phase 3 follow-up to the session kit loop,
I2-1/I2-2).

A session with no kit activity of its own inherits its cohort's default kit
list. The first time this specific session's kits are touched — ops
assigns/removes one, or an instructor receives/returns one — the cohort's
current default is copied ("materialized") into real `SessionKit` rows for
that one session, and `kits_overridden` flips to True for good. The flag,
not the row count, is what makes a session deliberately emptied out stay
independent instead of silently re-inheriting on the next read.
"""

import uuid
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.inventory import Kit, KitTemplate, Location, Warehouse
from app.models.inventory.session_kit import SessionKit
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.session import Session
from app.models.user import User
from app.services.inventory import (
    assign_kits,
    assigned_kits,
    cohort_kit_ids,
    cohort_kits,
    materialize_session_kits,
    mark_kits_received,
    remove_cohort_kit,
    resolve_session_kits,
    set_cohort_kits,
    unassign_kit,
)


async def _user(db, *roles: str) -> User:
    u = User(
        id=uuid.uuid4(), full_name="Person", email=f"u-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) or ["operations"], status="active",
    )
    db.add(u)
    await db.flush()
    return u


async def _cohort(db) -> Cohort:
    program = Program(
        id=uuid.uuid4(), code=f"P-{uuid.uuid4().hex[:8]}", name="Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Cohort", status="running")
    db.add(cohort)
    await db.flush()
    return cohort


async def _session(db, cohort: Cohort) -> Session:
    session = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date.today())
    db.add(session)
    await db.flush()
    return session


async def _kit(db) -> Kit:
    loc = Location(id=uuid.uuid4(), name="Dubai", country="AE")
    tpl = KitTemplate(id=uuid.uuid4(), name="SatKit", code=f"T{uuid.uuid4().hex[:5]}")
    db.add_all([loc, tpl])
    await db.flush()
    wh = Warehouse(id=uuid.uuid4(), location_id=loc.id, name="Dubai Main")
    db.add(wh)
    await db.flush()
    kit = Kit(
        id=uuid.uuid4(), template_id=tpl.id, label=f"SP-K-{uuid.uuid4().hex[:6]}",
        public_token=uuid.uuid4().hex * 2, current_location_id=loc.id,
        current_warehouse_id=wh.id,
    )
    db.add(kit)
    await db.flush()
    return kit


# ── setting/reading the cohort default itself ───────────────────────────────

@pytest.mark.asyncio
async def test_setting_the_default_twice_is_idempotent(db):
    """Same multi-select-resubmit contract as `assign_kits`."""
    ops = await _user(db)
    cohort = await _cohort(db)
    kit = await _kit(db)

    await set_cohort_kits(db, cohort_id=cohort.id, kit_ids=[kit.id], actor_user_id=ops.id)
    await set_cohort_kits(db, cohort_id=cohort.id, kit_ids=[kit.id], actor_user_id=ops.id)

    assert [k.id for k in await cohort_kits(db, cohort.id)] == [kit.id]


@pytest.mark.asyncio
async def test_removing_a_kit_not_in_the_default_is_a_404(db):
    cohort = await _cohort(db)
    kit = await _kit(db)
    with pytest.raises(HTTPException) as exc:
        await remove_cohort_kit(db, cohort_id=cohort.id, kit_id=kit.id)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_setting_defaults_on_a_missing_cohort_is_a_404(db):
    ops = await _user(db)
    kit = await _kit(db)
    with pytest.raises(HTTPException) as exc:
        await set_cohort_kits(db, cohort_id=uuid.uuid4(), kit_ids=[kit.id], actor_user_id=ops.id)
    assert exc.value.status_code == 404


# ── inheritance: a fresh session reads the cohort default ──────────────────

@pytest.mark.asyncio
async def test_a_fresh_session_inherits_the_cohort_default(db):
    ops = await _user(db)
    cohort = await _cohort(db)
    kit = await _kit(db)
    await set_cohort_kits(db, cohort_id=cohort.id, kit_ids=[kit.id], actor_user_id=ops.id)
    session = await _session(db, cohort)

    kits, level = await resolve_session_kits(db, session)
    assert level == "cohort"
    assert [k.id for k in kits] == [kit.id]
    assert session.kits_overridden is False


@pytest.mark.asyncio
async def test_a_cohort_with_no_default_resolves_to_none(db):
    cohort = await _cohort(db)
    session = await _session(db, cohort)

    kits, level = await resolve_session_kits(db, session)
    assert kits == []
    assert level == "none"


# ── materialization: the first write on the session copies the default in ──

@pytest.mark.asyncio
async def test_assigning_a_kit_materializes_the_cohort_default_first(db):
    """Assigning one additional kit to the session must not wipe out the
    cohort's inherited kits — they get copied in as real rows first, and the
    newly assigned kit joins them."""
    ops = await _user(db)
    cohort = await _cohort(db)
    default_kit = await _kit(db)
    extra_kit = await _kit(db)
    await set_cohort_kits(db, cohort_id=cohort.id, kit_ids=[default_kit.id], actor_user_id=ops.id)
    session = await _session(db, cohort)

    await assign_kits(db, session_id=session.id, kit_ids=[extra_kit.id], actor_user_id=ops.id)

    await db.refresh(session)
    assert session.kits_overridden is True
    own = {k.id for k in await assigned_kits(db, session.id)}
    assert own == {default_kit.id, extra_kit.id}

    kits, level = await resolve_session_kits(db, session)
    assert level == "session"
    assert {k.id for k in kits} == {default_kit.id, extra_kit.id}


@pytest.mark.asyncio
async def test_unassigning_an_inherited_kit_materializes_then_removes_it(db):
    """The whole point of materialize-on-write: a kit that only exists
    because the cohort defaults to it can still be taken off just this one
    session."""
    ops = await _user(db)
    cohort = await _cohort(db)
    kit = await _kit(db)
    await set_cohort_kits(db, cohort_id=cohort.id, kit_ids=[kit.id], actor_user_id=ops.id)
    session = await _session(db, cohort)

    await unassign_kit(db, session_id=session.id, kit_id=kit.id, actor_user_id=ops.id)

    await db.refresh(session)
    assert session.kits_overridden is True
    kits, level = await resolve_session_kits(db, session)
    assert level == "session"
    assert kits == []


@pytest.mark.asyncio
async def test_a_session_emptied_to_zero_stays_at_session_level(db):
    """The row-count trap this whole flag exists to avoid: zero materialized
    kits must not be indistinguishable from "never touched"."""
    ops = await _user(db)
    cohort = await _cohort(db)
    kit = await _kit(db)
    await set_cohort_kits(db, cohort_id=cohort.id, kit_ids=[kit.id], actor_user_id=ops.id)
    session = await _session(db, cohort)

    await unassign_kit(db, session_id=session.id, kit_id=kit.id, actor_user_id=ops.id)
    await db.refresh(session)

    # Read it again, as a fresh caller would — must not silently revert to
    # inheriting the cohort default just because there are zero rows.
    kits, level = await resolve_session_kits(db, session)
    assert kits == []
    assert level == "session"


@pytest.mark.asyncio
async def test_receiving_an_inherited_kit_materializes_it_first(db):
    """`mark_kits_received` previously 404'd on a kit with no `SessionKit`
    row — exactly the case an inherited, not-yet-materialized kit is in."""
    ops = await _user(db)
    instructor = await _user(db, "instructor")
    cohort = await _cohort(db)
    kit = await _kit(db)
    await set_cohort_kits(db, cohort_id=cohort.id, kit_ids=[kit.id], actor_user_id=ops.id)
    session = await _session(db, cohort)

    rows = await mark_kits_received(
        db, session_id=session.id, kit_ids=[kit.id], actor_user_id=instructor.id
    )
    assert len(rows) == 1
    assert rows[0].received_at is not None

    await db.refresh(session)
    assert session.kits_overridden is True


@pytest.mark.asyncio
async def test_changing_the_cohort_default_after_materialization_is_isolated(db):
    """Once a session has materialized, it is fully independent of the
    cohort default — even a later change to that default must not leak in."""
    ops = await _user(db)
    cohort = await _cohort(db)
    original_kit = await _kit(db)
    new_kit = await _kit(db)
    await set_cohort_kits(db, cohort_id=cohort.id, kit_ids=[original_kit.id], actor_user_id=ops.id)
    session = await _session(db, cohort)

    # First touch — materializes the original default.
    await assign_kits(db, session_id=session.id, kit_ids=[], actor_user_id=ops.id)
    await db.refresh(session)
    assert session.kits_overridden is True
    assert {k.id for k in await assigned_kits(db, session.id)} == {original_kit.id}

    # The cohort default changes afterward — the already-materialized
    # session must not see it.
    await set_cohort_kits(db, cohort_id=cohort.id, kit_ids=[new_kit.id], actor_user_id=ops.id)
    kits, level = await resolve_session_kits(db, session)
    assert level == "session"
    assert {k.id for k in kits} == {original_kit.id}


@pytest.mark.asyncio
async def test_materializing_twice_is_a_no_op(db):
    """`materialize_session_kits` must not re-copy or duplicate once the
    flag is already set."""
    ops = await _user(db)
    cohort = await _cohort(db)
    kit = await _kit(db)
    await set_cohort_kits(db, cohort_id=cohort.id, kit_ids=[kit.id], actor_user_id=ops.id)
    session = await _session(db, cohort)

    await materialize_session_kits(db, session=session, actor_user_id=ops.id)
    await materialize_session_kits(db, session=session, actor_user_id=ops.id)

    rows = (await db.execute(
        select(SessionKit).where(SessionKit.session_id == session.id)
    )).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_a_cohort_with_no_defaults_materializes_to_zero_rows_but_still_flips(db):
    """Today's universal case: no `CohortKit` rows anywhere. Materializing
    must still flip the flag (recording that a write happened) without
    creating anything."""
    ops = await _user(db)
    cohort = await _cohort(db)
    session = await _session(db, cohort)

    await materialize_session_kits(db, session=session, actor_user_id=ops.id)

    assert session.kits_overridden is True
    rows = (await db.execute(
        select(SessionKit).where(SessionKit.session_id == session.id)
    )).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_kit_sessions_includes_cohort_default_sessions(db):
    """`kit_sessions` must return sessions where the kit is inherited from the cohort default,
    not just explicit SessionKit rows."""
    from app.services.inventory.checks import kit_sessions
    ops = await _user(db)
    cohort = await _cohort(db)
    kit = await _kit(db)
    await set_cohort_kits(db, cohort_id=cohort.id, kit_ids=[kit.id], actor_user_id=ops.id)
    session = await _session(db, cohort)

    sessions = await kit_sessions(db, kit.id)
    assert len(sessions) == 1
    assert sessions[0]["session_id"] == session.id


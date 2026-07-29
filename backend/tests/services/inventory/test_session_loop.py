"""The session loop (I2-1/I2-2): assigning kits, counting them, and the gate
on finishing a session.

The gate is the one place inventory reaches into live production code
(`services/sessions/delivery.py::mark_done`), so the "a session with no kits
is completely unaffected" case matters as much as the gating one — most
sessions have no kits, and they must behave exactly as they did before.
"""

import uuid
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.inventory import Item, Kit, KitItem, KitCheck, KitTemplate, KitTemplateItem, Location
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor
from app.models.user import User
from app.services.inventory import (
    assign_kits,
    assigned_kits,
    expected_counts,
    outstanding_post_checks,
    record_check,
    unassign_kit,
)
from app.services.sessions.delivery import mark_done, start_session


# ── factories ───────────────────────────────────────────────────────────────

async def _user(db, *roles: str) -> User:
    u = User(
        id=uuid.uuid4(), full_name="Person", email=f"u-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) or ["operations"], status="active",
    )
    db.add(u)
    await db.flush()
    return u


async def _session(db) -> Session:
    program = Program(
        id=uuid.uuid4(), code=f"P-{uuid.uuid4().hex[:8]}", name="Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Cohort", status="running")
    db.add(cohort)
    await db.flush()
    session = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date.today())
    db.add(session)
    await db.flush()
    return session


async def _kit(db, *, required: dict | None = None, held: dict | None = None) -> Kit:
    loc = Location(id=uuid.uuid4(), name="Dubai", country="AE")
    tpl = KitTemplate(id=uuid.uuid4(), name="SatKit", code=f"T{uuid.uuid4().hex[:5]}")
    db.add_all([loc, tpl])
    await db.flush()
    for item, qty in (required or {}).items():
        db.add(KitTemplateItem(id=uuid.uuid4(), template_id=tpl.id, item_id=item.id, required_qty=qty))
    kit = Kit(
        id=uuid.uuid4(), template_id=tpl.id, label=f"SP-K-{uuid.uuid4().hex[:6]}",
        public_token=uuid.uuid4().hex * 2, current_location_id=loc.id,
    )
    db.add(kit)
    await db.flush()
    for item, qty in (held or {}).items():
        db.add(KitItem(id=uuid.uuid4(), kit_id=kit.id, item_id=item.id, qty=qty))
    await db.flush()
    return kit


async def _item(db, name=None, **kw) -> Item:
    item = Item(id=uuid.uuid4(), name=name or f"Item {uuid.uuid4().hex[:6]}", **kw)
    db.add(item)
    await db.flush()
    return item


# ── assignment ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_assigning_the_same_kit_twice_is_a_no_op(db):
    """The UI is a multi-select that resubmits the whole set, so this has to
    be idempotent rather than a 409."""
    ops = await _user(db)
    session = await _session(db)
    kit = await _kit(db)

    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=ops.id)
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=ops.id)

    assert [k.id for k in await assigned_kits(db, session.id)] == [kit.id]


@pytest.mark.asyncio
async def test_unassigning_a_kit_that_was_not_assigned_is_a_404(db):
    session = await _session(db)
    kit = await _kit(db)
    with pytest.raises(HTTPException) as exc:
        await unassign_kit(db, session_id=session.id, kit_id=kit.id)
    assert exc.value.status_code == 404


# ── the count form ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_form_is_prefilled_and_excludes_consumables(db):
    """One tap for the common case. And twenty screws counted after every
    workshop is how a shortage list becomes unreadable."""
    board = await _item(db, name="ADCS Board")
    screw = await _item(db, name="M3 Screw", is_consumable=True)
    kit = await _kit(db, required={board: 1, screw: 20}, held={board: 1, screw: 14})

    lines = await expected_counts(db, kit)
    assert [line["item_name"] for line in lines] == ["ADCS Board"]
    assert lines[0]["expected"] == 1, "prefilled with what we believe is in the box"
    assert lines[0]["required"] == 1


# ── recording a count ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_count_becomes_the_kits_contents(db):
    """Someone who just looked inside the box outranks the database."""
    instructor = await _user(db, "instructor")
    board = await _item(db, name="ADCS Board")
    kit = await _kit(db, required={board: 2}, held={board: 2})

    await record_check(db, kit=kit, phase="post", checked_by=instructor.id, counts={board.id: 1})

    row = (await db.execute(
        select(KitItem).where(KitItem.kit_id == kit.id, KitItem.item_id == board.id)
    )).scalars().first()
    assert row.qty == 1


@pytest.mark.asyncio
async def test_missing_is_snapshotted_not_recomputed(db):
    """A template's parts list changes; what was missing on the day does not.
    Recomputing an old check against today's BOM would rewrite history."""
    instructor = await _user(db, "instructor")
    board = await _item(db, name="ADCS Board")
    kit = await _kit(db, required={board: 3})

    check = await record_check(db, kit=kit, phase="post", checked_by=instructor.id, counts={board.id: 1})
    assert check.missing == {str(board.id): 2}

    # The BOM is later relaxed — the historical check must not change.
    line = (await db.execute(
        select(KitTemplateItem).where(KitTemplateItem.template_id == kit.template_id)
    )).scalars().first()
    line.required_qty = 1
    await db.flush()
    await db.refresh(check)
    assert check.missing == {str(board.id): 2}


@pytest.mark.asyncio
async def test_a_skipped_check_is_recorded_not_absent(db):
    """"Chose to start without counting" must be distinguishable from "hasn't
    got to it yet", or a later shortage has no baseline."""
    instructor = await _user(db, "instructor")
    kit = await _kit(db)

    check = await record_check(db, kit=kit, phase="pre", checked_by=instructor.id, skipped=True)
    assert check.skipped is True
    assert check.counts == {} and check.missing == {}


@pytest.mark.asyncio
async def test_an_empty_check_that_is_not_skipped_is_rejected(db):
    instructor = await _user(db, "instructor")
    kit = await _kit(db)
    with pytest.raises(HTTPException) as exc:
        await record_check(db, kit=kit, phase="post", checked_by=instructor.id, counts={})
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_a_negative_count_is_rejected(db):
    instructor = await _user(db, "instructor")
    board = await _item(db)
    kit = await _kit(db, required={board: 1})
    with pytest.raises(HTTPException) as exc:
        await record_check(db, kit=kit, phase="post", checked_by=instructor.id, counts={board.id: -1})
    assert exc.value.status_code == 400


# ── the gate on finishing a session ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_session_with_no_kits_finishes_exactly_as_before(db):
    """Most sessions have no kits. The gate must be invisible to them —
    this is the regression that matters most, since mark_done is live code."""
    ops = await _user(db)
    session = await _session(db)
    await start_session(db, session.id, ops)

    done = await mark_done(db, session.id, ops)
    assert done.completed_at is not None


@pytest.mark.asyncio
async def test_a_session_with_an_uncounted_kit_cannot_be_finished(db):
    ops = await _user(db)
    session = await _session(db)
    kit = await _kit(db)
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=ops.id)

    with pytest.raises(HTTPException) as exc:
        await mark_done(db, session.id, ops)
    assert exc.value.status_code == 409
    assert kit.label in exc.value.detail, "name the kit, don't just say something is missing"
    await db.refresh(session)
    assert session.completed_at is None


@pytest.mark.asyncio
async def test_counting_the_kit_unlocks_finishing(db):
    ops = await _user(db)
    session = await _session(db)
    board = await _item(db)
    kit = await _kit(db, required={board: 1}, held={board: 1})
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=ops.id)

    assert [k.id for k in await outstanding_post_checks(db, session.id)] == [kit.id]

    await record_check(
        db, kit=kit, phase="post", checked_by=ops.id, counts={board.id: 1}, session_id=session.id
    )
    assert await outstanding_post_checks(db, session.id) == []

    done = await mark_done(db, session.id, ops)
    assert done.completed_at is not None


@pytest.mark.asyncio
async def test_a_pre_check_does_not_satisfy_the_gate(db):
    """Counting on the way in says nothing about what came back."""
    ops = await _user(db)
    session = await _session(db)
    board = await _item(db)
    kit = await _kit(db, required={board: 1}, held={board: 1})
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=ops.id)

    await record_check(
        db, kit=kit, phase="pre", checked_by=ops.id, counts={board.id: 1}, session_id=session.id
    )
    with pytest.raises(HTTPException) as exc:
        await mark_done(db, session.id, ops)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_a_skipped_post_check_still_counts_as_counted(db):
    """The gate exists to make people look, not to trap them. If a kit is
    genuinely unavailable to count, saying so closes the session — and leaves
    a record that nobody looked."""
    ops = await _user(db)
    session = await _session(db)
    kit = await _kit(db)
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=ops.id)

    await record_check(db, kit=kit, phase="post", checked_by=ops.id, skipped=True, session_id=session.id)

    done = await mark_done(db, session.id, ops)
    assert done.completed_at is not None
    check = (await db.execute(select(KitCheck).where(KitCheck.kit_id == kit.id))).scalars().first()
    assert check.skipped is True


@pytest.mark.asyncio
async def test_finishing_stays_idempotent(db):
    ops = await _user(db)
    session = await _session(db)
    first = await mark_done(db, session.id, ops)
    stamp = first.completed_at
    second = await mark_done(db, session.id, ops)
    assert second.completed_at == stamp


@pytest.mark.asyncio
async def test_an_unassigned_instructor_still_gets_404_not_409(db):
    """The gate must not leak the existence of a session an instructor has
    nothing to do with — the don't-leak-existence rule outranks it."""
    outsider = await _user(db, "instructor")
    ops = await _user(db)
    session = await _session(db)
    kit = await _kit(db)
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=ops.id)

    with pytest.raises(HTTPException) as exc:
        await mark_done(db, session.id, outsider)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_the_assigned_instructor_sees_the_gate(db):
    ops = await _user(db)
    instructor = await _user(db, "instructor")
    session = await _session(db)
    db.add(SessionInstructor(id=uuid.uuid4(), session_id=session.id, user_id=instructor.id, role="lead"))
    kit = await _kit(db)
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=ops.id)
    await db.flush()

    with pytest.raises(HTTPException) as exc:
        await mark_done(db, session.id, instructor)
    assert exc.value.status_code == 409

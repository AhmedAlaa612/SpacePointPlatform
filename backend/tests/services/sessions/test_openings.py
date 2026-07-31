"""Duration, delivery roles, openings and add-ons (I5-2 … I5-4, §G-addons)."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.sessions.cohort import Cohort
from app.models.sessions.delivery_role import DeliveryRole
from app.models.sessions.instructor_interest import InstructorInterest
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor
from app.models.user import User
from app.services.sessions import openings as svc


async def _user(db, *roles: str) -> User:
    u = User(
        id=uuid.uuid4(), full_name=f"P{uuid.uuid4().hex[:4]}",
        email=f"u-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) or ["instructor"], status="active",
    )
    db.add(u)
    await db.flush()
    return u


async def _chain(db, *, program_hours=None, cohort_hours=None, session_hours=None):
    program = Program(
        id=uuid.uuid4(), code=f"P-{uuid.uuid4().hex[:8]}", name="P",
        program_type="workshop", pricing_model="free", active=True,
        duration_hours=program_hours,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(
        id=uuid.uuid4(), program_id=program.id, name="C", status="running",
        duration_hours=cohort_hours,
    )
    db.add(cohort)
    await db.flush()
    session = Session(
        id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date.today(),
        duration_hours=session_hours,
    )
    db.add(session)
    await db.flush()
    return program, cohort, session


async def _role(db, name, order) -> DeliveryRole:
    role = DeliveryRole(id=uuid.uuid4(), name=f"{name} {uuid.uuid4().hex[:4]}", sort_order=order)
    db.add(role)
    await db.flush()
    return role


# ── I5-2: duration hierarchy ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_duration_falls_back_program_then_cohort_then_session(db):
    """The chain the operator specified, and the same shape `price` uses."""
    _p, _c, session = await _chain(db, program_hours=3)
    assert await svc.resolve_duration(db, session) == Decimal("3")

    _p, _c, session = await _chain(db, program_hours=3, cohort_hours=4)
    assert await svc.resolve_duration(db, session) == Decimal("4")

    _p, _c, session = await _chain(db, program_hours=3, cohort_hours=4, session_hours=Decimal("2.5"))
    assert await svc.resolve_duration(db, session) == Decimal("2.5")


@pytest.mark.asyncio
async def test_duration_is_none_when_nobody_set_it(db):
    """Honest rather than zero: the payment line stays blank instead of
    printing a guessed number on something someone signs."""
    _p, _c, session = await _chain(db)
    assert await svc.resolve_duration(db, session) is None


# ── I5-3: roles are data ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_lead_is_the_lowest_sort_order_not_a_name(db):
    """Everything that used to match `role == "lead"` reads seniority now, so
    renaming or inserting a role above doesn't break who is in charge."""
    # 0 beats the seeded "Lead Facilitator" at 1 — the point being that
    # inserting a role *above* the existing top one moves seniority, which a
    # name match on "lead" could never do.
    junior = await _role(db, "Assistant", 90)
    senior = await _role(db, "Chief", 0)

    assert await svc.lead_role_id(db) == senior.id
    assert senior.id != junior.id


@pytest.mark.asyncio
async def test_session_lead_is_the_most_senior_person_assigned(db):
    lead_role = await _role(db, "Lead", 1)
    assist_role = await _role(db, "Assistant", 5)
    _p, _c, session = await _chain(db)
    boss, helper = await _user(db), await _user(db)
    # Deliberately added junior-first, so ordering can't pass by accident.
    db.add(SessionInstructor(
        id=uuid.uuid4(), session_id=session.id, user_id=helper.id, role_id=assist_role.id))
    db.add(SessionInstructor(
        id=uuid.uuid4(), session_id=session.id, user_id=boss.id, role_id=lead_role.id))
    await db.flush()

    assert await svc.session_lead_user_id(db, session.id) == boss.id


@pytest.mark.asyncio
async def test_a_duplicate_role_name_is_refused(db):
    await svc.create_role(db, name="Marshal")
    with pytest.raises(HTTPException) as exc:
        await svc.create_role(db, name="marshal")
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_the_last_active_role_cannot_be_deactivated(db):
    """Deactivating everything would make assignment impossible with no
    obvious way back."""
    roles = await svc.list_roles(db)
    for role in roles[1:]:
        await svc.update_role(db, role=role, is_active=False)
    with pytest.raises(HTTPException) as exc:
        await svc.update_role(db, role=roles[0], is_active=False)
    assert exc.value.status_code == 409


# ── I5-4: openings ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_slots_remaining_and_waitlist_are_derived_not_stored(db):
    ops = await _user(db, "operations")
    lead_role = await _role(db, "Lead", 1)
    _p, _c, session = await _chain(db)

    await svc.set_openings(
        db, session_id=session.id, actor_user_id=ops.id,
        lines=[{"role_id": lead_role.id, "slots": 2, "amount_aed": Decimal("2000"), "notes": None}],
    )
    [row] = await svc.openings_for_session(db, session.id)
    assert (row["slots"], row["filled"], row["remaining"]) == (2, 0, 2)
    assert row["amount_aed"] == Decimal("2000.00")

    someone = await _user(db)
    db.add(SessionInstructor(
        id=uuid.uuid4(), session_id=session.id, user_id=someone.id, role_id=lead_role.id))
    await db.flush()

    [row] = await svc.openings_for_session(db, session.id)
    assert (row["filled"], row["remaining"]) == (1, 1)


@pytest.mark.asyncio
async def test_a_session_is_half_staffed_when_one_role_is_still_open(db):
    """The consequence the plan flagged: staffing stops being all-or-nothing."""
    ops = await _user(db, "operations")
    lead_role = await _role(db, "Lead", 1)
    assist_role = await _role(db, "Assistant", 2)
    _p, _c, session = await _chain(db)

    await svc.set_openings(
        db, session_id=session.id, actor_user_id=ops.id,
        lines=[
            {"role_id": lead_role.id, "slots": 1},
            {"role_id": assist_role.id, "slots": 2},
        ],
    )
    boss = await _user(db)
    db.add(SessionInstructor(
        id=uuid.uuid4(), session_id=session.id, user_id=boss.id, role_id=lead_role.id))
    await db.flush()

    assert await svc.fully_staffed(db, session.id) is False


@pytest.mark.asyncio
async def test_a_session_with_no_openings_behaves_exactly_as_before(db):
    """Everything created before I5-4 has no openings, and must keep meaning
    "staffed once somebody is assigned"."""
    _p, _c, session = await _chain(db)
    role = await _role(db, "Lead", 1)
    assert await svc.fully_staffed(db, session.id) is False

    someone = await _user(db)
    db.add(SessionInstructor(
        id=uuid.uuid4(), session_id=session.id, user_id=someone.id, role_id=role.id))
    await db.flush()
    assert await svc.fully_staffed(db, session.id) is True


@pytest.mark.asyncio
async def test_removing_an_opening_someone_holds_is_refused(db):
    ops = await _user(db, "operations")
    role = await _role(db, "Lead", 1)
    _p, _c, session = await _chain(db)
    await svc.set_openings(
        db, session_id=session.id, actor_user_id=ops.id,
        lines=[{"role_id": role.id, "slots": 1}],
    )
    someone = await _user(db)
    db.add(SessionInstructor(
        id=uuid.uuid4(), session_id=session.id, user_id=someone.id, role_id=role.id))
    await db.flush()

    with pytest.raises(HTTPException) as exc:
        await svc.set_openings(db, session_id=session.id, actor_user_id=ops.id, lines=[])
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_slots_cannot_drop_below_the_number_already_assigned(db):
    ops = await _user(db, "operations")
    role = await _role(db, "Lead", 1)
    _p, _c, session = await _chain(db)
    await svc.set_openings(
        db, session_id=session.id, actor_user_id=ops.id,
        lines=[{"role_id": role.id, "slots": 2}],
    )
    for _ in range(2):
        u = await _user(db)
        db.add(SessionInstructor(
            id=uuid.uuid4(), session_id=session.id, user_id=u.id, role_id=role.id))
    await db.flush()

    with pytest.raises(HTTPException) as exc:
        await svc.set_openings(
            db, session_id=session.id, actor_user_id=ops.id,
            lines=[{"role_id": role.id, "slots": 1}],
        )
    assert exc.value.status_code == 409


# ── §G-addons ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ops_addons_arrive_agreed_and_instructor_ones_arrive_proposed(db):
    """This mapping *is* the approval mechanism — one column doing the work of
    an approval feature."""
    ops = await _user(db, "operations")
    instructor = await _user(db)
    _p, _c, session = await _chain(db)

    offered = await svc.add_addon(
        db, session_id=session.id, description="Poster printing", amount_aed=200,
        source="offer", actor_user_id=ops.id,
    )
    assert offered.status == "agreed" and offered.decided_at is not None

    asked = await svc.add_addon(
        db, session_id=session.id, description="Taxi", amount_aed=80,
        source="survey", actor_user_id=instructor.id, user_id=instructor.id,
    )
    assert asked.status == "proposed" and asked.decided_at is None


@pytest.mark.asyncio
async def test_all_five_sources_are_accepted(db):
    """The operator's five moments, one table."""
    ops = await _user(db, "operations")
    _p, _c, session = await _chain(db)
    for source in ("offer", "interest", "invite", "survey", "payment"):
        addon = await svc.add_addon(
            db, session_id=session.id, description=f"via {source}", amount_aed=10,
            source=source, actor_user_id=ops.id,
        )
        assert addon.source == source


@pytest.mark.asyncio
async def test_deciding_a_request_records_who_and_when(db):
    ops = await _user(db, "operations")
    instructor = await _user(db)
    _p, _c, session = await _chain(db)
    addon = await svc.add_addon(
        db, session_id=session.id, description="Extra hour", amount_aed=100,
        source="interest", actor_user_id=instructor.id, user_id=instructor.id,
    )

    await svc.decide_addon(db, addon=addon, status="agreed", actor_user_id=ops.id)
    assert addon.status == "agreed"
    assert addon.decided_by == ops.id and addon.decided_at is not None


@pytest.mark.asyncio
async def test_a_role_addon_reaches_whoever_holds_that_role(db):
    """`user_id` NULL means it belongs to the role — how the per-opening idea
    survives without an `opening_id`."""
    ops = await _user(db, "operations")
    role = await _role(db, "Lead", 1)
    _p, _c, session = await _chain(db)
    holder, stranger = await _user(db), await _user(db)
    db.add(SessionInstructor(
        id=uuid.uuid4(), session_id=session.id, user_id=holder.id, role_id=role.id))
    await db.flush()

    await svc.add_addon(
        db, session_id=session.id, description="Printing", amount_aed=200,
        source="offer", actor_user_id=ops.id, role_id=role.id,
    )

    assert len(await svc.addons_for_session(db, session.id, user_id=holder.id)) == 1
    assert await svc.addons_for_session(db, session.id, user_id=stranger.id) == []


@pytest.mark.asyncio
async def test_an_unknown_source_is_refused(db):
    ops = await _user(db, "operations")
    _p, _c, session = await _chain(db)
    with pytest.raises(HTTPException) as exc:
        await svc.add_addon(
            db, session_id=session.id, description="x", amount_aed=1,
            source="telepathy", actor_user_id=ops.id,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_updating_an_addon_changes_only_what_was_sent(db):
    ops = await _user(db, "operations")
    _p, _c, session = await _chain(db)
    addon = await svc.add_addon(
        db, session_id=session.id, description="Poster printing", amount_aed=200,
        source="offer", actor_user_id=ops.id,
    )

    await svc.update_addon(db, addon=addon, amount_aed=250)
    assert addon.description == "Poster printing"
    assert addon.amount_aed == Decimal("250")

    await svc.update_addon(db, addon=addon, description="Banner printing")
    assert addon.description == "Banner printing"
    assert addon.amount_aed == Decimal("250")


@pytest.mark.asyncio
async def test_deleting_an_addon_removes_it_from_the_session(db):
    ops = await _user(db, "operations")
    _p, _c, session = await _chain(db)
    addon = await svc.add_addon(
        db, session_id=session.id, description="Taxi", amount_aed=80,
        source="offer", actor_user_id=ops.id,
    )
    await svc.delete_addon(db, addon=addon)
    assert await svc.addons_for_session(db, session.id) == []


# ── B2: open calls per role ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_closed_roles_are_invisible_with_open_only_but_not_to_ops(db):
    ops = await _user(db, "operations")
    lead = await _role(db, "Lead", 1)
    assistant = await _role(db, "Assistant", 2)
    _p, _c, session = await _chain(db)
    await svc.set_openings(
        db, session_id=session.id, actor_user_id=ops.id,
        lines=[{"role_id": lead.id, "slots": 1}, {"role_id": assistant.id, "slots": 2}],
    )

    await svc.set_openings_open(db, session_id=session.id, role_ids=[lead.id])

    all_rows = await svc.openings_for_session(db, session.id)
    assert {r["role_id"]: r["is_open"] for r in all_rows} == {lead.id: True, assistant.id: False}

    open_rows = await svc.openings_for_session(db, session.id, open_only=True)
    assert [r["role_id"] for r in open_rows] == [lead.id]


@pytest.mark.asyncio
async def test_set_openings_open_with_none_opens_every_role(db):
    """The default the plain 'Open Call (All Instructors)' button relies on."""
    ops = await _user(db, "operations")
    lead = await _role(db, "Lead", 1)
    assistant = await _role(db, "Assistant", 2)
    _p, _c, session = await _chain(db)
    await svc.set_openings(
        db, session_id=session.id, actor_user_id=ops.id,
        lines=[{"role_id": lead.id, "slots": 1}, {"role_id": assistant.id, "slots": 1}],
    )
    await svc.set_openings_open(db, session_id=session.id, role_ids=[lead.id])

    await svc.set_openings_open(db, session_id=session.id, role_ids=None)
    rows = await svc.openings_for_session(db, session.id)
    assert all(r["is_open"] for r in rows)

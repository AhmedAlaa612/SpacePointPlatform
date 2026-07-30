"""Inventory reminders (I2-5).

Tests the two internals directly — `send_inventory_reminders` itself opens its
own engine (a worker job has no request to borrow a session from), so the ARQ
entry point is verified by running a real worker, not here.

Redis-free: nothing in these functions touches the queue. SMTP is
unconfigured in dev, so `try_send_email` degrades gracefully and returns
False; the in-app notification is what these assert on, which is the point —
email alone was never an acceptable channel here.
"""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from app.models.inventory import Item, Kit, KitTemplate, Location, StockLevel
from app.models.notification import Notification
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor
from app.models.user import User
from app.services.inventory import assign_kits, issue_merch, record_check
from app.workers.tasks.inventory import (

    OVERDUE_TYPE,
    UNCOUNTED_TYPE,
    _remind_overdue,
    _remind_uncounted,
)

async def _role_id(db, name: str = "Lead Facilitator"):
    """I5-3: roles are rows now. The three are seeded by migration
    `c2a7b49e0022`, so tests look them up rather than inventing their own."""
    from sqlalchemy import select

    from app.models.sessions.delivery_role import DeliveryRole

    return await db.scalar(select(DeliveryRole.id).where(DeliveryRole.name == name))



async def _user(db, *roles: str) -> User:
    u = User(
        id=uuid.uuid4(), full_name=f"P{uuid.uuid4().hex[:4]}",
        email=f"u-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) or ["operations"], status="active",
    )
    db.add(u)
    await db.flush()
    return u


async def _session_with_kit(db, lead: User, *, meeting_date: date) -> tuple[Session, Kit]:
    program = Program(
        id=uuid.uuid4(), code=f"P-{uuid.uuid4().hex[:8]}", name="P",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="C", status="running")
    db.add(cohort)
    await db.flush()
    session = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=meeting_date)
    db.add(session)
    await db.flush()
    db.add(SessionInstructor(id=uuid.uuid4(), session_id=session.id, user_id=lead.id, role_id=await _role_id(db)))

    loc = Location(id=uuid.uuid4(), name="Dubai", country="AE")
    tpl = KitTemplate(id=uuid.uuid4(), name="SatKit", code=f"T{uuid.uuid4().hex[:5]}")
    db.add_all([loc, tpl])
    await db.flush()
    kit = Kit(
        id=uuid.uuid4(), template_id=tpl.id, label=f"SP-K-{uuid.uuid4().hex[:6]}",
        public_token=uuid.uuid4().hex * 2, current_location_id=loc.id,
    )
    db.add(kit)
    await db.flush()
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=lead.id)
    return session, kit


async def _notifications(db, user_id, notif_type) -> int:
    return await db.scalar(
        select(func.count()).select_from(Notification).where(
            Notification.user_id == user_id, Notification.type == notif_type
        )
    )


# ── uncounted kits ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_yesterdays_uncounted_session_nudges_its_instructor(db):
    lead = await _user(db, "instructor")
    session, kit = await _session_with_kit(db, lead, meeting_date=date.today() - timedelta(days=1))

    assert await _remind_uncounted(db) == 1
    assert await _notifications(db, lead.id, UNCOUNTED_TYPE) == 1

    notif = (await db.execute(
        select(Notification).where(Notification.user_id == lead.id)
    )).scalars().first()
    assert kit.label in notif.body, "name the kit, don't make them go looking"


@pytest.mark.asyncio
async def test_a_session_today_is_left_alone(db):
    """A day's grace on purpose. Somebody who packs up at 6pm and counts the
    boxes next morning has done nothing wrong, and a reminder that fires while
    they're still in the room is how people learn to ignore them."""
    lead = await _user(db, "instructor")
    await _session_with_kit(db, lead, meeting_date=date.today())

    assert await _remind_uncounted(db) == 0
    assert await _notifications(db, lead.id, UNCOUNTED_TYPE) == 0


@pytest.mark.asyncio
async def test_a_counted_session_is_not_nudged(db):
    lead = await _user(db, "instructor")
    session, kit = await _session_with_kit(db, lead, meeting_date=date.today() - timedelta(days=3))
    await record_check(
        db, kit=kit, phase="post", checked_by=lead.id, skipped=True, session_id=session.id
    )

    assert await _remind_uncounted(db) == 0


@pytest.mark.asyncio
async def test_nobody_is_nudged_twice_about_the_same_session(db):
    """One nudge per thing. The notification is the record — a separate
    "reminded_at" column would be a second source of truth about one fact."""
    lead = await _user(db, "instructor")
    await _session_with_kit(db, lead, meeting_date=date.today() - timedelta(days=2))

    assert await _remind_uncounted(db) == 1
    assert await _remind_uncounted(db) == 0
    assert await _notifications(db, lead.id, UNCOUNTED_TYPE) == 1


@pytest.mark.asyncio
async def test_a_session_with_no_kits_is_never_nudged(db):
    lead = await _user(db, "instructor")
    program = Program(
        id=uuid.uuid4(), code=f"P-{uuid.uuid4().hex[:8]}", name="P",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="C", status="running")
    db.add(cohort)
    await db.flush()
    session = Session(
        id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date.today() - timedelta(days=5)
    )
    db.add(session)
    await db.flush()
    db.add(SessionInstructor(id=uuid.uuid4(), session_id=session.id, user_id=lead.id, role_id=await _role_id(db)))
    await db.flush()

    assert await _remind_uncounted(db) == 0


# ── overdue things ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_an_overdue_vest_nudges_whoever_has_it(db):
    ops = await _user(db)
    person = await _user(db, "instructor")
    loc = Location(id=uuid.uuid4(), name="Dubai", country="AE")
    vest = Item(id=uuid.uuid4(), name="Vest (L)", category="merch", returnable_default=True)
    db.add_all([loc, vest])
    await db.flush()
    db.add(StockLevel(id=uuid.uuid4(), item_id=vest.id, location_id=loc.id, qty=5))
    await db.flush()

    await issue_merch(
        db, actor_user_id=ops.id, item_id=vest.id, to_user_id=person.id,
        from_location_id=loc.id, due_back_on=date.today() - timedelta(days=2),
    )

    assert await _remind_overdue(db) == 1
    assert await _notifications(db, person.id, OVERDUE_TYPE) == 1


@pytest.mark.asyncio
async def test_nothing_without_a_deadline_is_ever_nudged(db):
    """A kit that lives with an instructor indefinitely must never generate a
    reminder, or the channel becomes noise."""
    ops = await _user(db)
    person = await _user(db, "instructor")
    loc = Location(id=uuid.uuid4(), name="Dubai", country="AE")
    shirt = Item(id=uuid.uuid4(), name="T-Shirt (L)", category="merch", returnable_default=False)
    db.add_all([loc, shirt])
    await db.flush()
    db.add(StockLevel(id=uuid.uuid4(), item_id=shirt.id, location_id=loc.id, qty=5))
    await db.flush()

    await issue_merch(
        db, actor_user_id=ops.id, item_id=shirt.id, to_user_id=person.id, from_location_id=loc.id
    )

    assert await _remind_overdue(db) == 0


@pytest.mark.asyncio
async def test_overdue_reminders_are_also_sent_only_once(db):
    ops = await _user(db)
    person = await _user(db, "instructor")
    loc = Location(id=uuid.uuid4(), name="Dubai", country="AE")
    vest = Item(id=uuid.uuid4(), name="Vest (M)", category="merch", returnable_default=True)
    db.add_all([loc, vest])
    await db.flush()
    db.add(StockLevel(id=uuid.uuid4(), item_id=vest.id, location_id=loc.id, qty=5))
    await db.flush()
    await issue_merch(
        db, actor_user_id=ops.id, item_id=vest.id, to_user_id=person.id,
        from_location_id=loc.id, due_back_on=date.today() - timedelta(days=1),
    )

    assert await _remind_overdue(db) == 1
    assert await _remind_overdue(db) == 0

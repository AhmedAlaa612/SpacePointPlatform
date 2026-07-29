"""Inventory reminders (I2-5).

Two nudges, both cron jobs rather than anything triggered by a request:

* a session finished a day ago and its kits were never counted
* something is past its return date and hasn't come back

**Both send an in-app notification and an email.** Email alone is not a
channel here: there is no delivery tracking anywhere in this system and SMTP
cannot report bounces (`HANDOFF_V2_LIVE.md` §5.8), so an email that silently
fails looks exactly like a reminder that was ignored.

Reminders are sent **once per thing**, tracked by the notification already
existing rather than by a flag on the row. A second table to remember whether
we nagged is a second thing to keep honest, and the notification *is* the
record.
"""

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.inventory.kit import Kit
from app.models.inventory.movement import Movement
from app.models.inventory.session_kit import SessionKit
from app.models.notification import Notification
from app.models.sessions.session import Session, SessionInstructor
from app.models.user import User
from app.services.email import try_send_email
from app.services.inventory.checks import outstanding_post_checks
from app.services.inventory.movements import overdue
from app.services.notification import create_notification

logger = logging.getLogger(__name__)

UNCOUNTED_TYPE = "inventory_uncounted_kits"
OVERDUE_TYPE = "inventory_overdue"


async def _already_nudged(db: AsyncSession, user_id, notif_type: str, key: str) -> bool:
    """One nudge per thing. The notification is the record — a separate
    "reminded_at" column would be a second source of truth about the same
    fact."""
    return await db.scalar(
        select(Notification.id).where(
            Notification.user_id == user_id,
            Notification.type == notif_type,
            Notification.body.contains(key),
        )
    ) is not None


async def _remind_uncounted(db: AsyncSession) -> int:
    """Sessions that finished yesterday whose kits were never counted.

    A day's grace on purpose: an instructor who packs up at 6pm and counts the
    boxes the next morning has done nothing wrong, and a reminder that fires
    while they are still in the room is how people learn to ignore them.
    """
    cutoff = date.today() - timedelta(days=1)
    session_ids = (await db.execute(
        select(Session.id)
        .join(SessionKit, SessionKit.session_id == Session.id)
        .where(Session.meeting_date <= cutoff, Session.completed_at.is_(None))
        .distinct()
    )).scalars().all()

    sent = 0
    for session_id in session_ids:
        uncounted = await outstanding_post_checks(db, session_id)
        if not uncounted:
            continue

        labels = ", ".join(k.label for k in uncounted)
        instructors = (await db.execute(
            select(User)
            .join(SessionInstructor, SessionInstructor.user_id == User.id)
            .where(SessionInstructor.session_id == session_id)
        )).scalars().all()

        for user in instructors:
            if await _already_nudged(db, user.id, UNCOUNTED_TYPE, str(session_id)):
                continue
            body = (
                f"Your session still needs its kits counted before it can be marked done: "
                f"{labels}. (session {session_id})"
            )
            await create_notification(
                db, user_id=user.id, title="Kits still to count",
                body=body, type=UNCOUNTED_TYPE,
            )
            await try_send_email(
                to=user.email,
                subject="Kits still to count",
                body=(
                    f"Hi {user.full_name},\n\n"
                    f"Your session hasn't been closed out yet — these kits still need "
                    f"counting: {labels}.\n\n"
                    f"You can do it from the session page in the portal.\n"
                ),
            )
            sent += 1
    return sent


async def _remind_overdue(db: AsyncSession) -> int:
    sent = 0
    for movement in await overdue(db):
        if movement.to_user_id is None:
            continue
        user = await db.get(User, movement.to_user_id)
        if user is None:
            continue

        what = "a kit"
        if movement.kit_id:
            kit = await db.get(Kit, movement.kit_id)
            what = kit.label if kit else "a kit"
        elif movement.qty:
            what = f"{movement.qty} item(s)"

        if await _already_nudged(db, user.id, OVERDUE_TYPE, str(movement.id)):
            continue

        await create_notification(
            db, user_id=user.id, title="Something is due back",
            body=f"{what} was due back on {movement.due_back_on}. (movement {movement.id})",
            type=OVERDUE_TYPE,
        )
        await try_send_email(
            to=user.email,
            subject="Something is due back",
            body=(
                f"Hi {user.full_name},\n\n"
                f"{what} was due back on {movement.due_back_on} and we haven't recorded it "
                f"returning. If you've already handed it over, let operations know so we can "
                f"fix the record.\n"
            ),
        )
        sent += 1
    return sent


async def send_inventory_reminders(ctx: dict) -> dict:
    """ARQ cron entry point. Opens its own session — a worker job has no
    request to borrow one from."""
    engine = create_async_engine(settings.DATABASE_URL)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessionmaker() as db:
            uncounted = await _remind_uncounted(db)
            due = await _remind_overdue(db)
            await db.commit()
    finally:
        await engine.dispose()

    logger.info("inventory reminders: %s uncounted, %s overdue", uncounted, due)
    return {"uncounted": uncounted, "overdue": due, "at": datetime.now(timezone.utc).isoformat()}

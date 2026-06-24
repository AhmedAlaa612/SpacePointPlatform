from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from uuid import UUID
from app.models.notification import Notification


async def create_notification(db: AsyncSession, user_id: UUID, title: str, body: str = None) -> None:
    notif = Notification(user_id=user_id, title=title, body=body)
    db.add(notif)


async def get_notifications(db: AsyncSession, user_id: UUID):
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(50)
    )
    return result.scalars().all()


async def mark_read(db: AsyncSession, notification_id: UUID, user_id: UUID):
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id
        )
    )
    notif = result.scalars().first()
    if notif:
        notif.is_read = True
        await db.commit()
        await db.refresh(notif)
    return notif


async def mark_all_read(db: AsyncSession, user_id: UUID) -> None:
    result = await db.execute(
        select(Notification).where(
            Notification.user_id == user_id,
            Notification.is_read == False  # noqa: E712
        )
    )
    for n in result.scalars().all():
        n.is_read = True
    await db.commit()

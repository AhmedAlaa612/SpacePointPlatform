"""Shared access to the portal_settings key-value table (admin signature,
signatory name/title, application video config, …)."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.instructors.payment import PortalSetting


async def get_portal_setting(db: AsyncSession, key: str, default: str = "") -> str:
    row = (await db.execute(select(PortalSetting).where(PortalSetting.key == key))).scalars().first()
    return row.value if row and row.value else default


async def set_portal_setting(db: AsyncSession, key: str, value: str) -> PortalSetting:
    """Upsert. Callers commit — this only flushes, so a setting change can
    ride the same transaction as whatever prompted it."""
    import uuid

    row = (await db.execute(select(PortalSetting).where(PortalSetting.key == key))).scalars().first()
    if row is None:
        row = PortalSetting(id=uuid.uuid4(), key=key, value=value)
        db.add(row)
    else:
        row.value = value
    await db.flush()
    return row

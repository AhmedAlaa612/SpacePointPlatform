"""Shared access to the portal_settings key-value table (admin signature,
signatory name/title, application video config, …)."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.instructors.payment import PortalSetting


async def get_portal_setting(db: AsyncSession, key: str, default: str = "") -> str:
    row = (await db.execute(select(PortalSetting).where(PortalSetting.key == key))).scalars().first()
    return row.value if row and row.value else default

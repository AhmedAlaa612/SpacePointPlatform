"""Seed reference data. Run after `alembic upgrade head`:

    python seed.py

Phase 0 seeds only the admin account (from ADMIN_EMAIL / ADMIN_PASSWORD).
Later phases extend this with invitation codes, checklist modules, titles/badges,
and reward settings.
"""

import asyncio

from sqlalchemy import select

from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import AsyncSessionLocal
from app.models.enums import UserRole
from app.models.user import User


async def seed_admin() -> None:
    async with AsyncSessionLocal() as db:
        existing = (
            await db.execute(select(User).where(User.email == settings.ADMIN_EMAIL))
        ).scalars().first()
        if existing:
            print(f"✓ Admin already exists: {settings.ADMIN_EMAIL}")
            return

        admin = User(
            full_name="SpacePoint Admin",
            email=settings.ADMIN_EMAIL,
            password_hash=get_password_hash(settings.ADMIN_PASSWORD),
            roles=[UserRole.admin],
            status="active",
        )
        db.add(admin)
        await db.commit()
        print(f"✓ Created admin: {settings.ADMIN_EMAIL}")


async def main() -> None:
    await seed_admin()


if __name__ == "__main__":
    asyncio.run(main())

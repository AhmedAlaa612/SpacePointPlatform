"""Seed (or update) SatKit Space Systems Book V2 in the LMS database & R2/local storage.

Usage:
    cd backend
    python -m scripts.seed_satkit_book [--source "C:\\Users\\ahmed\\Downloads\\SatKit Space Systems Book - V2"]
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.lms.book import LmsBook
from app.models.user import User
from app.services.lms.books import unpack_and_upload_book_zip
from scripts.package_satkit_book import package_book


async def seed_satkit(source_dir: Path, zip_path: Path) -> None:
    summary = package_book(source_dir, zip_path)
    zip_bytes = zip_path.read_bytes()

    async with AsyncSessionLocal() as db:
        admin_user = (
            await db.execute(select(User).where(User.email == settings.ADMIN_EMAIL))
        ).scalars().first()
        if admin_user is None:
            admin_user = (await db.execute(select(User).limit(1))).scalars().first()
        if admin_user is None:
            raise RuntimeError("No users found in DB; create an admin user first before seeding books.")

        book = (
            await db.execute(select(LmsBook).where(LmsBook.slug == "satkit-space-systems"))
        ).scalars().first()

        now = datetime.now(timezone.utc)
        if book is None:
            book = LmsBook(
                id=uuid.uuid4(),
                slug="satkit-space-systems",
                title="Space Systems with SatKit",
                title_ar="أنظمة الفضاء مع SatKit",
                subtitle=None,
                description=(
                    "A bilingual interactive space systems textbook pairing physics units with hands-on "
                    "SatKit CubeSat mission labs, 3D hardware figures, live simulations, and engineering notebooks."
                ),
                author_name="SpacePoint Engineering",
                languages=["en", "ar"],
                access_mode="open",
                is_published=True,
                created_by=admin_user.id,
                created_at=now,
                updated_at=now,
            )
            db.add(book)
            await db.flush()

        res = await unpack_and_upload_book_zip(db, book=book, zip_bytes=zip_bytes)
        book.subtitle = None
        book.is_published = True
        await db.commit()
        print("Seeded SatKit book:", {**summary, **res, "book_id": str(book.id)})


def main() -> None:
    parser = argparse.ArgumentParser(description="Package and seed SatKit Space Systems Book V2.")
    parser.add_argument(
        "--source",
        default=r"C:\Users\ahmed\Downloads\SatKit Space Systems Book - V2",
        help="Path to the unpacked SatKit book folder",
    )
    parser.add_argument(
        "--zip",
        default=str(Path(__file__).resolve().parents[1] / "storage" / "seed_bundles" / "satkit-space-systems-v2.zip"),
        help="Intermediate zip output path",
    )
    args = parser.parse_args()
    asyncio.run(seed_satkit(Path(args.source), Path(args.zip)))


if __name__ == "__main__":
    main()

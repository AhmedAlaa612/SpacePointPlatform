"""Backfill users.email (plus contacts.email / applications.email) to strip().lower().

`users.email` has a case-sensitive UNIQUE index, and normalization was only
ever applied on some write paths (student signup) — not admin-created
accounts, instructor applications, judging imports, or bulk scripts.
Result: an account stored as "John@X.com" or " judge@x.com " could never
log in, since login compares against the normalized input. That mismatch
is fixed in app/routers/auth.py and app/services/user.py (plus a
User.email model validator as safety net); this script fixes the data
already sitting in the tables.

CONFLICTS
    If two rows already differ only by case (e.g. "a@x.com" and "A@x.com"),
    lowercasing both would collide on the unique index. This script never
    writes into that situation blindly — it reports any such collision group
    and skips every row in it, so a human can decide which account is the
    real one (merge, or rename the stray).

USAGE
    python -m scripts.backfill_lowercase_emails [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.spine.contact import Contact
from app.models.user import User


async def backfill_lowercase_emails(db: AsyncSession) -> tuple[int, list[str]]:
    """Normalize users.email + contacts.email + applications.email.

    Returns (rows_updated, collision_groups) where collision_groups covers
    users.email collisions only (the UNIQUE-constrained table) — contacts
    and applications have no such constraint so they normalize unconditionally.
    """
    users = (await db.execute(select(User).where(User.email.is_not(None)))).scalars().all()

    by_lower: dict[str, list[User]] = defaultdict(list)
    for user in users:
        by_lower[(user.email or "").strip().lower()].append(user)

    updated = 0
    collisions: list[str] = []
    for lower, rows in by_lower.items():
        if len(rows) > 1:
            ids = ", ".join(str(r.id) for r in rows)
            collisions.append(f"{lower}: {len(rows)} accounts ({ids})")
            continue
        user = rows[0]
        if user.email != lower:
            user.email = lower
            updated += 1

    # Contacts feed users.email via get_or_create_student_account — a dirty
    # contact re-dirties the next account. Applications feed users.email via
    # approve/onboard. Normalize both unconditionally (no UNIQUE to collide).
    contacts = (await db.execute(select(Contact).where(Contact.email.is_not(None)))).scalars().all()
    for c in contacts:
        norm = (c.email or "").strip().lower() or None
        if c.email != norm:
            c.email = norm
            updated += 1

    apps = (await db.execute(select(Application).where(Application.email.is_not(None)))).scalars().all()
    for app in apps:
        norm = (app.email or "").strip().lower()
        if app.email != norm:
            app.email = norm
            updated += 1

    await db.flush()
    return updated, collisions


async def run(dry_run: bool = False) -> None:
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        updated, collisions = await backfill_lowercase_emails(db)
        if dry_run:
            await db.rollback()
            print(f"[backfill_lowercase_emails] DRY RUN — would lowercase {updated} email(s); "
                  f"no changes written.")
        else:
            await db.commit()
            print(f"[backfill_lowercase_emails] lowercased {updated} email(s).")

        if collisions:
            print(f"[backfill_lowercase_emails] SKIPPED {len(collisions)} collision group(s) "
                  f"— resolve manually:")
            for line in collisions:
                print(f"  {line}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run))

"""One-time platform-wide SP-0000 renumbering (operator ask, 2026-08-17).

Every account gets an ID number now, not just accounts someone happened to
generate a physical/digital card for — "if they create an account they
should get an id". New ordering:

    1  -> the boss              (--boss-email)
    2  -> the COO                (--coo-email)
    3, 4  -> reserved, left unassigned on purpose
    5+ -> everyone else, oldest account first (users.created_at ascending)

Run this AFTER scripts/bulk_import_instructors.py (not before) — the newly
imported instructors need to already exist so they're included in the
"everyone else" pool and sort near the end by their (recent) created_at.

────────────────────────────────────────────────────────────────────────────
USAGE
────────────────────────────────────────────────────────────────────────────
    cd backend
    .venv\\Scripts\\python.exe scripts\\reset_card_numbers.py \\
        --boss-email boss@example.com --coo-email coo@example.com --dry-run

Same DATABASE_URL-from-.env convention as bulk_import_instructors.py — no
separate --db flag, so it's always obvious which database a run touched.

--dry-run : prints the full old-ID -> new-ID mapping table and makes no
            database changes at all (not even inside a rolled-back
            transaction — this script's dry-run is pure computation from a
            read-only query, since the reassignment logic needs no writes
            to simulate). Always run this first.

────────────────────────────────────────────────────────────────────────────
WHY THE NULL-FIRST STEP
────────────────────────────────────────────────────────────────────────────
`users.card_number` has a unique partial index (idx_users_card_number,
sql/0011_person_id_cards.sql). Reassigning in place would collide constantly
— e.g. whoever is about to become #1 might currently hold #47, and #47 is
also somebody else's target number. Nulling every card_number first (single
UPDATE, no unique conflict possible against NULL) then reassigning avoids
that entirely.

Any EXISTING `id_cards` row (a role's already-rendered card) has its own
`card_id` string updated to match — otherwise the numbers on file would
disagree with the number the person's card actually renders next time
someone views it. `card_seq_person` is bumped past the highest assigned
number afterward so the next lazy allocation (ensure_card_number, now
called at every account-creation site — see services/documents/id_card.py)
never collides with a number this script just handed out.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import select, text

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.id_card import IdCard
from app.models.user import User


def _card_id(number: int) -> str:
    return f"SP-{number:04d}-UAE"


async def run(args) -> None:
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        boss = (await db.execute(
            select(User).where(User.email.ilike(args.boss_email))
        )).scalars().first()
        coo = (await db.execute(
            select(User).where(User.email.ilike(args.coo_email))
        )).scalars().first()
        if boss is None:
            raise SystemExit(f"No user found with email {args.boss_email!r}")
        if coo is None:
            raise SystemExit(f"No user found with email {args.coo_email!r}")
        if boss.id == coo.id:
            raise SystemExit("--boss-email and --coo-email resolve to the same account")

        others = (await db.execute(
            select(User)
            .where(User.id.notin_([boss.id, coo.id]))
            .order_by(User.created_at.asc(), User.id.asc())
        )).scalars().all()

        assignment: list[tuple[User, int]] = [(boss, 1), (coo, 2)]
        assignment += [(u, 5 + i) for i, u in enumerate(others)]
        max_number = max(n for _, n in assignment)

        print("\n" + "=" * 92)
        print(f"CARD NUMBER RESET {'(DRY RUN — no changes made)' if args.dry_run else '(LIVE RUN)'}")
        print("=" * 92)
        print(f"{'new':>5}  {'old':>5}  {'name':<32} email")
        print("-" * 92)
        for u, new_number in assignment:
            old = u.card_number if u.card_number is not None else "-"
            print(f"{new_number:>5}  {str(old):>5}  {u.full_name[:32]:<32} {u.email}")
        print("-" * 92)
        print(f"Total accounts: {len(assignment)} (3 and 4 reserved, unassigned)")
        print("=" * 92 + "\n")

        if args.dry_run:
            return

        # Null every card_number first — see module docstring for why.
        await db.execute(text("UPDATE users SET card_number = NULL"))
        await db.flush()
        # Without this, any user whose NEW number happens to equal the OLD
        # in-memory value they were loaded with (boss/coo are the likely
        # case — their slot is often already close to what it was) gets
        # silently left NULL: SQLAlchemy's dirty-tracking compares against
        # the object's last-known Python value, never against what the raw
        # SQL above just did to the actual row, so `u.card_number = 5`
        # looks like a no-op when the object already said 5 in memory even
        # though the DB row is now NULL. expire_all() forces every
        # attribute to be reloaded (as NULL, post-update) before the
        # assignment below, so every reassignment is seen as a real change.
        # Caught by testing this script against the dev DB before it ever
        # touched production — see the session's dry-run report.
        db.expire_all()

        for u, new_number in assignment:
            u.card_number = new_number
        await db.flush()

        # Any already-rendered card's stored card_id string needs to match
        # the new number too, or it'll disagree with what renders next time.
        user_ids = [u.id for u, _ in assignment]
        number_by_user = {u.id: n for u, n in assignment}
        existing_cards = (await db.execute(
            select(IdCard).where(IdCard.user_id.in_(user_ids))
        )).scalars().all()
        for card in existing_cards:
            card.card_id = _card_id(number_by_user[card.user_id])

        await db.execute(text("CREATE SEQUENCE IF NOT EXISTS card_seq_person START 1 INCREMENT 1"))
        await db.execute(text("SELECT setval('card_seq_person', :n)"), {"n": max_number})

        await db.commit()
        print(f"Committed. {len(existing_cards)} existing id_cards row(s) had their card_id string updated to match.")


def main() -> None:
    p = argparse.ArgumentParser(description="One-time platform-wide SP-0000 renumbering")
    p.add_argument("--boss-email", required=True)
    p.add_argument("--coo-email", required=True)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()

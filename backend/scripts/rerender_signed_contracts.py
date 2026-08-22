"""Re-render already-signed instructor contracts with the fixed layout.

The signature block's Facilitator column was misaligned in the DOCX
template pipeline (the "Date:" label sat a full inch left of its column,
and the date itself was tab-snapped away from the label). Both were fixed
in services/documents/contract.py on 2026-08-09, and the block was rebuilt
as a table on 2026-08-22 so a long name can no longer break it at all.
Unsigned drafts need no backfill — `_ensure_contract`
(routers/instructors/instructor.py) already re-renders those from scratch on
every profile load — but signed PDFs are written once at signing time and
never touched again, so they keep the old broken layout forever unless
something rewrites them. That's this script.

Everything needed to reproduce a signed contract byte-for-byte (modulo the
layout fix itself) is persisted on InstructorProfile: `contract_signature_data`
holds the signature image, `contract_signed_at` the date that was printed.

DECISIONS (operator, 2026-08-09)
  * Living area is re-resolved live via the router's own `_resolve_living_area`
    rather than being recovered from the old PDF. No instructor has changed
    city, so live resolution reproduces what was originally printed. If that
    ever stops being true, this script would silently reprint a DIFFERENT
    city than the one signed against — re-check the assumption before reusing
    it for a later backfill.
  * The date is re-derived as `instructor_since` — the day the role was
    granted — via format_contract_date, matching both the signing endpoint
    and the unsigned draft (2026-08-22: all three used to disagree; signing
    printed the signing date, zero-padded, and this script reproduced that).
    A re-render therefore CORRECTS the date on contracts signed before that
    change rather than reproducing it; falls back to the signing date for a
    row with no instructor_since.
  * The signed PDF is REPLACED IN PLACE at its existing `signed_contract_path`,
    with no archival copy of the original. The as-signed artifact is not
    recoverable afterwards. This was an explicit call made when exactly one
    signed contract existed and it was visibly broken; for a larger or
    legally-scrutinised set, archive first instead.

Only the stored PDF changes. `contract_signed_at`, `contract_signature_data`
and `signed_contract_path` are all left exactly as they are — this is not a
re-signing, and it must never look like one.

USAGE
    python -m scripts.rerender_signed_contracts [--dry-run] [--email EMAIL]

    --email scopes the run to that one instructor instead of every signed
    contract — for fixing a single reported-broken contract without
    overwriting everyone else's already-signed PDF too (operator ask,
    2026-08-22: exactly this case — one instructor's long name broke their
    layout, the fix shouldn't touch anyone whose contract already looked
    fine).

IDEMPOTENCY
    Safe to re-run: each run regenerates from the same persisted inputs and
    overwrites the same path, so a second run produces the same bytes as the
    first (the printed date comes from instructor_since, never today).
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instructors.instructor_profile import InstructorProfile
from app.models.user import User
from app.routers.instructors.instructor import _resolve_living_area
from app.services import storage
from app.services.documents.contract import format_contract_date, generate_contract_pdf


async def rerender_signed_contracts(
    db: AsyncSession, *, dry_run: bool = False, email: str | None = None,
) -> tuple[int, int]:
    """Re-render signed contracts in place. Returns (rerendered, skipped).

    `email` scopes this to one instructor's contract instead of every signed
    one — see USAGE in the module docstring.

    Flushes but never commits/rolls back — that's the caller's job, matching
    scripts/backfill_user_contacts.py.
    """
    query = (
        select(InstructorProfile, User)
        .join(User, User.id == InstructorProfile.user_id)
        .where(InstructorProfile.contract_signed_at.is_not(None))
    )
    if email is not None:
        query = query.where(User.email == email)
    rows = (await db.execute(query)).all()

    rerendered = skipped = 0
    for profile, user in rows:
        # A signed profile missing either of these can't be reproduced: the
        # signature image is unrecoverable, and without a path there's nothing
        # to overwrite. Skip loudly rather than writing a contract with a
        # blank signature over a real one.
        if not profile.signed_contract_path or not profile.contract_signature_data:
            print(f"  SKIP {user.full_name} ({user.id}): "
                  f"path={profile.signed_contract_path!r} "
                  f"signature={'present' if profile.contract_signature_data else 'MISSING'}")
            skipped += 1
            continue

        living_area = await _resolve_living_area(db, user)
        contract_date = format_contract_date(
            profile.instructor_since or profile.contract_signed_at.date()
        )

        pdf_bytes = await asyncio.to_thread(
            generate_contract_pdf,
            user.full_name,
            living_area,
            contract_date=contract_date,
            instructor_signature_b64=profile.contract_signature_data,
        )

        if dry_run:
            print(f"  WOULD REPLACE {user.full_name} -> {profile.signed_contract_path} "
                  f"({len(pdf_bytes)} bytes, city={living_area!r}, date={contract_date!r})")
        else:
            url = await storage.upload_file(
                "contracts", profile.signed_contract_path, pdf_bytes, "application/pdf"
            )
            # Path is unchanged; refresh the legacy *_url column only because
            # it's still the fallback in _profile_out when path is unset.
            profile.signed_contract_url = url
            print(f"  REPLACED {user.full_name} -> {profile.signed_contract_path} "
                  f"({len(pdf_bytes)} bytes, city={living_area!r}, date={contract_date!r})")
        rerendered += 1

    await db.flush()
    return rerendered, skipped


async def run(dry_run: bool = False, email: str | None = None) -> tuple[int, int]:
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        rerendered, skipped = await rerender_signed_contracts(db, dry_run=dry_run, email=email)
        if email is not None and rerendered == 0 and skipped == 0:
            # Distinguish "found them, nothing to do" from "typo'd the email
            # and silently matched nobody" — the latter must not print the
            # same all-clear as a real no-op run.
            print(f"[rerender_signed_contracts] no signed contract found for {email!r} — "
                  f"check the email is correct and that they've actually signed.")
            return rerendered, skipped
        if dry_run:
            await db.rollback()
            print(f"[rerender_signed_contracts] DRY RUN — would re-render {rerendered} "
                  f"signed contract(s), skipped {skipped}; nothing written.")
        else:
            await db.commit()
            print(f"[rerender_signed_contracts] re-rendered {rerendered} "
                  f"signed contract(s), skipped {skipped}.")
    return rerendered, skipped


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true",
                   help="Report what would be replaced; write nothing to storage or the DB.")
    p.add_argument("--email", default=None,
                   help="Only re-render this one instructor's signed contract, by login email.")
    return p.parse_args(argv)


def main() -> None:
    args = parse_args()
    asyncio.run(run(dry_run=args.dry_run, email=args.email))


if __name__ == "__main__":
    main()

"""Backfill LMS access stranded by the "email already on a different
account" gap (2026-09-15), and report (never auto-fix) the fallout of the
roster re-upload bug fixed the same day in
services/competitions/registration_import.py.

Root cause: `get_or_create_student_account` (services/lms/ops_integration.py)
returns (None, False) — and `sync_registration_lms` therefore skips
`assign_lms_program` entirely — whenever a registration's contact has no
linked User AND some *other* account already owns that email. The
competition roster importer's own `fallback_email` path already covers the
*team*-membership half of this gap (it looks up that existing user by email
and still adds them to the team via `_register_and_assign_team`), but never
retroactively calls `assign_lms_program` — so the student ends up
Registered=yes, Team=yes, LMS checklist access=NO. Confirmed against
production logs (~2026-09) via the recurring "get_or_create_student_account:
email %s is already on a different account, skipping" warning.

This script closes the LMS-access half directly: for every non-cancelled
Registration whose contact resolves to a User (either its own linked one,
or — the gap case — the pre-existing account that already holds that
email) but has no LmsProgramAssignment yet for that (user, cohort), it
calls `assign_lms_program` the same way `sync_registration_lms` would have.
It never creates a new User and never sends any email (`assign_lms_program`
itself sends none) — this only closes the checklist-access gap on an
account that already exists.

It also *reports* (read-only, never writes, unless --cancel-duplicates is
given — see below) two related anomalies:
  - "registered but not on any team", in cohorts that have teams at all —
    should be near zero, since the importer's fallback path above already
    handles team join even when the LMS-access call above got skipped; a
    non-zero count here is a different bug, not this gap.
  - duplicate-registration groups: more than one Registration in the same
    cohort for contacts sharing a normalized email — pre-existing
    duplicates from before registration_import.py's own email-dedup fix
    (observed in production, 2026-09-15: the same roster sheet imported
    three times ~25-30 minutes apart, each run minting fresh Contact rows
    instead of matching the ones from the run before — timestamps too far
    apart to be a race, an ops/UI issue instead).

--cancel-duplicates (opt-in, off by default even without --dry-run): for
each duplicate group, marks every Registration except the earliest
`status="cancelled"`, keeping the row for audit history rather than
deleting it. Safe with respect to LMS access and team membership — both
are keyed off User, not Registration, so nothing about either changes.

USAGE
    python -m scripts.backfill_registration_access [--dry-run] [--cohort-id UUID] [--cancel-duplicates]

IDEMPOTENCY
    Only ever writes an LmsProgramAssignment for a (user, cohort) pair that
    doesn't have one yet — a pair fixed by an earlier run (or by the live
    app) is never revisited, same UNIQUE(user_id, cohort_id) idempotency
    `assign_lms_program` itself already guarantees. --cancel-duplicates is
    likewise idempotent: a group with only one non-cancelled Registration
    left (from an earlier run of this flag) is no longer a "duplicate
    group" at all, so a second run leaves it alone. Safe to run more than
    once, and safe to run while the app is live.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lms.program import LmsProgramAssignment
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.models.team import Team, TeamMember
from app.models.user import User
from app.services.lms.program import assign_lms_program

logger = logging.getLogger("scripts.backfill_registration_access")


@dataclass
class AccessReport:
    assigned: list[tuple[uuid.UUID, uuid.UUID, str]] = field(default_factory=list)
    already_ok: int = 0
    no_user: list[uuid.UUID] = field(default_factory=list)
    no_program: int = 0
    errors: list[tuple[uuid.UUID, str]] = field(default_factory=list)


async def _resolve_user(db: AsyncSession, contact: Contact) -> User | None:
    """Same resolution order `get_or_create_student_account` itself follows,
    minus the "create a brand new one" branch — a registration old enough
    to need backfilling already went through that function once; no
    account existing at all here means the contact has no email, not that
    creation is still pending."""
    linked = (await db.execute(
        select(User).where(User.contact_id == contact.id).order_by(User.created_at)
    )).scalars().first()
    if linked is not None:
        return linked
    if not contact.email:
        return None
    return (await db.execute(
        select(User).where(User.email == contact.email).order_by(User.created_at)
    )).scalars().first()


async def backfill_lms_access(db: AsyncSession, *, cohort_id: uuid.UUID | None = None) -> AccessReport:
    query = select(Registration).where(Registration.status != "cancelled")
    if cohort_id is not None:
        query = query.where(Registration.cohort_id == cohort_id)
    registrations = (await db.execute(query)).scalars().all()

    report = AccessReport()
    for reg in registrations:
        contact = await db.get(Contact, reg.contact_id)
        if contact is None:
            continue
        user = await _resolve_user(db, contact)
        if user is None:
            report.no_user.append(reg.id)
            continue

        existing = await db.scalar(
            select(LmsProgramAssignment).where(
                LmsProgramAssignment.user_id == user.id, LmsProgramAssignment.cohort_id == reg.cohort_id,
            )
        )
        if existing is not None:
            report.already_ok += 1
            continue

        try:
            assignment = await assign_lms_program(
                db, user_id=user.id, cohort_id=reg.cohort_id, registration_id=reg.id,
            )
        except Exception as exc:  # pragma: no cover - defensive, mirrors sync_registration_lms's own discipline
            logger.exception("assign_lms_program failed for registration %s", reg.id)
            report.errors.append((reg.id, str(exc)))
            continue

        if assignment is not None:
            report.assigned.append((reg.id, user.id, user.email))
        else:
            report.no_program += 1

    return report


async def report_team_gaps(
    db: AsyncSession, *, cohort_id: uuid.UUID | None = None,
) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """Read-only. Registered students in a cohort that has teams at all, who
    aren't a member of any team in it. See module docstring for why this
    should already be near zero."""
    cohorts_with_teams = set((await db.execute(
        select(Team.cohort_id).where(Team.cohort_id.is_not(None)).distinct()
    )).scalars().all())
    if cohort_id is not None:
        cohorts_with_teams &= {cohort_id}

    gaps: list[tuple[uuid.UUID, uuid.UUID]] = []
    for cid in cohorts_with_teams:
        regs = (await db.execute(
            select(Registration).where(Registration.cohort_id == cid, Registration.status != "cancelled")
        )).scalars().all()
        member_user_ids = set((await db.execute(
            select(TeamMember.user_id).join(Team, Team.id == TeamMember.team_id).where(Team.cohort_id == cid)
        )).scalars().all())
        for reg in regs:
            contact = await db.get(Contact, reg.contact_id)
            if contact is None:
                continue
            user = await _resolve_user(db, contact)
            if user is not None and user.id not in member_user_ids:
                gaps.append((reg.id, user.id))
    return gaps


async def _group_duplicate_registrations(
    db: AsyncSession, *, cohort_id: uuid.UUID | None = None,
) -> dict[tuple[uuid.UUID, str], list[Registration]]:
    """(cohort_id, normalized email) -> its Registrations, oldest first.
    Shared by the read-only report and the opt-in cancellation below, so
    both agree on exactly what counts as a duplicate group."""
    query = select(Registration).where(Registration.status != "cancelled")
    if cohort_id is not None:
        query = query.where(Registration.cohort_id == cohort_id)
    registrations = (await db.execute(query)).scalars().all()

    by_key: dict[tuple[uuid.UUID, str], list[Registration]] = defaultdict(list)
    for reg in registrations:
        contact = await db.get(Contact, reg.contact_id)
        if contact is None or not contact.email:
            continue
        key = (reg.cohort_id, contact.email.strip().lower())
        by_key[key].append(reg)

    for regs in by_key.values():
        regs.sort(key=lambda r: r.created_at)
    return {key: regs for key, regs in by_key.items() if len(regs) > 1}


async def report_duplicate_registrations(
    db: AsyncSession, *, cohort_id: uuid.UUID | None = None,
) -> list[dict]:
    """Read-only. More than one Registration in the same cohort for contacts
    sharing a normalized email. Reported, never touched — see module
    docstring for why picking one to keep is a human call."""
    groups = await _group_duplicate_registrations(db, cohort_id=cohort_id)
    return [
        {
            "cohort_id": cid,
            "email": email,
            "registration_ids": sorted(r.id for r in regs),
            "created_at": [r.created_at for r in regs],
        }
        for (cid, email), regs in groups.items()
    ]


async def cancel_duplicate_registrations(
    db: AsyncSession, *, cohort_id: uuid.UUID | None = None,
) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """Opt-in cleanup (never run implicitly by `backfill_lms_access` or the
    read-only report above): for every duplicate group, keeps the
    earliest-created Registration and marks every later one in the group
    `status="cancelled"`. Rows are kept, not deleted, for audit history.
    Safe with respect to LMS access and team membership — both are keyed
    off `User`, not `Registration` (`LmsProgramAssignment` is
    UNIQUE(user_id, cohort_id), `TeamMember`'s PK is (team_id, user_id)),
    so cancelling the extra Registration rows for the same physical
    student never touches either. Returns (kept_id, cancelled_id) pairs."""
    groups = await _group_duplicate_registrations(db, cohort_id=cohort_id)
    cancelled: list[tuple[uuid.UUID, uuid.UUID]] = []
    for regs in groups.values():
        kept, *extras = regs
        for reg in extras:
            reg.status = "cancelled"
            cancelled.append((kept.id, reg.id))
    return cancelled


async def run(
    dry_run: bool = False, cohort_id: uuid.UUID | None = None, cancel_duplicates: bool = False,
) -> None:
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        access_report = await backfill_lms_access(db, cohort_id=cohort_id)
        team_gaps = await report_team_gaps(db, cohort_id=cohort_id)
        dupes = await report_duplicate_registrations(db, cohort_id=cohort_id)
        cancelled = await cancel_duplicate_registrations(db, cohort_id=cohort_id) if cancel_duplicates else []

        if dry_run:
            await db.rollback()
        else:
            await db.commit()

    label = "DRY RUN — would grant" if dry_run else "granted"
    print(f"[backfill_registration_access] {label} LMS program access to "
          f"{len(access_report.assigned)} registration(s):")
    for reg_id, user_id, email in access_report.assigned:
        print(f"    registration={reg_id} user={user_id} email={email}")
    print(f"[backfill_registration_access] already had access: {access_report.already_ok}")
    print(f"[backfill_registration_access] no resolvable user account (no email on contact): "
          f"{len(access_report.no_user)} {access_report.no_user}")
    print(f"[backfill_registration_access] cohort has no LMS program/checklist (expected no-op): "
          f"{access_report.no_program}")
    if access_report.errors:
        print(f"[backfill_registration_access] ERRORS while assigning: {access_report.errors}")

    print()
    print(f"[backfill_registration_access] registered-but-not-on-any-team anomalies: {len(team_gaps)}")
    for reg_id, user_id in team_gaps:
        print(f"    registration={reg_id} user={user_id}")

    print()
    print(f"[backfill_registration_access] duplicate-registration groups (same cohort, same email): {len(dupes)}")
    for dupe in dupes:
        print(f"    cohort={dupe['cohort_id']} email={dupe['email']} "
              f"registrations={dupe['registration_ids']} created_at={dupe['created_at']}")

    if cancel_duplicates:
        label = "DRY RUN — would cancel" if dry_run else "cancelled"
        print()
        print(f"[backfill_registration_access] {label} {len(cancelled)} duplicate registration(s) "
              f"(kept the earliest per group):")
        for kept_id, cancelled_id in cancelled:
            print(f"    kept={kept_id} cancelled={cancelled_id}")
    elif dupes:
        print()
        print("[backfill_registration_access] pass --cancel-duplicates to cancel every duplicate "
              "except the earliest per group (kept registration is never touched).")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true", help="Report what would happen; write nothing.")
    p.add_argument("--cohort-id", type=uuid.UUID, default=None, help="Limit to one cohort.")
    p.add_argument(
        "--cancel-duplicates", action="store_true",
        help="Also cancel every duplicate registration except the earliest per (cohort, email) group. "
             "Off by default even without --dry-run.",
    )
    return p.parse_args(argv)


def main() -> None:
    args = parse_args()
    asyncio.run(run(dry_run=args.dry_run, cohort_id=args.cohort_id, cancel_duplicates=args.cancel_duplicates))


if __name__ == "__main__":
    main()

"""Backfill users.contact_id — V2 R2-6.

Every staff user (instructor, ambassador, teacher, intern, admin, etc.) is
also a spine contact, same as public registrants — so they show up in
Contacts/merge-review flows and can be linked from touchpoints. This script
creates the missing contact rows for any user that doesn't have one yet, and
also re-syncs contact_roles for users already linked, since a user's actual
roles can change (e.g. gaining "instructor" later) well after their contact
was first created — see the 2026-07-24 fix below.

Deliberately does NOT go through services.spine.identity.resolve_or_create_contact:
that function's evaluate()-based matching exists to reconcile a NEW submission
against contacts that might already exist from an EARLIER submission with the
same phone/email. There's no equivalent history to reconcile against here —
a user without contact_id has, by definition, never been backfilled before,
so a plain create is correct; matching by name is still never done, per
MASTER_EXECUTION_PLAN.md §2.5.

USAGE
    python -m scripts.backfill_user_contacts [--dry-run]

IDEMPOTENCY
    Creating a contact only ever happens for users WHERE contact_id IS NULL —
    a user linked in a prior run is never linked to a SECOND contact. Role
    re-sync is additive-only (union, never removes an existing role) and is a
    no-op once a contact's roles already cover what the user's roles map to
    (see tests/scripts/test_backfill_user_contacts.py).
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.spine.contact import Contact
from app.models.user import User
from app.services.spine.identity import contact_roles_for_user as _contact_roles_for
from app.services.spine.identity import ensure_user_contact

# Re-exported from services/spine/identity.py (canonical location as of
# 2026-07-24) purely so this module's existing name keeps working for
# tests/imports written against it (`from scripts.backfill_user_contacts
# import _contact_roles_for`) — don't add new logic here, add it there.


async def backfill_user_contacts(db: AsyncSession) -> int:
    """Link every user without a contact_id to a freshly-created contact, and
    re-sync contact_roles for users already linked (additive/union only —
    never removes a role the contact already has, whether that came from an
    earlier sync or a human editing the contact directly in the Contacts UI).

    Pure service function: flushes but never commits/rolls back — that's the
    caller's job (run() below for a real CLI invocation, the `db` test
    fixture's automatic rollback in tests). Returns the number of users
    NEWLY linked (not the number of role re-syncs) so existing callers/tests
    that check "did this create a new contact" keep working unchanged.
    """
    linked = 0

    unlinked = (await db.execute(select(User).where(User.contact_id.is_(None)))).scalars().all()
    for user in unlinked:
        await ensure_user_contact(db, user, source="backfill_initial")
        linked += 1

    # Already-linked users: additive-only re-sync, no role-history event (see
    # services/spine/role_history.py's module docstring / the plan's
    # 2026-07-24 discoveries entry — there's no reliable date to attach to a
    # role change the script is only now noticing, possibly long after it
    # actually happened; the live services/user.py hook is what records
    # these going forward).
    already_linked = (await db.execute(select(User).where(User.contact_id.is_not(None)))).scalars().all()
    for user in already_linked:
        contact = await db.get(Contact, user.contact_id)
        if contact is None:
            continue
        needed = set(_contact_roles_for(user)) - set(contact.contact_roles or [])
        if needed:
            contact.contact_roles = sorted(set(contact.contact_roles or []) | needed)

    await db.flush()
    return linked


async def run(dry_run: bool = False) -> int:
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        linked = await backfill_user_contacts(db)
        if dry_run:
            await db.rollback()
            print(f"[backfill_user_contacts] DRY RUN — would link {linked} new user(s) "
                  f"(plus role re-sync for already-linked users); no changes written.")
        else:
            await db.commit()
            print(f"[backfill_user_contacts] linked {linked} new user(s); "
                  f"re-synced contact_roles for already-linked users where needed.")
    return linked


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true", help="Report what would happen; write nothing.")
    return p.parse_args(argv)


def main() -> None:
    args = parse_args()
    asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()

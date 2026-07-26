"""Role-history recording (operator request, 2026-07-24) — "in this date they
were lead, in that date they became student, then intern, then instructor."

One function, `record_role_diff`, used by every place that mutates either
`contacts.contact_roles` or `users.roles`: compute what was added/removed
between a before/after snapshot and append one row per role per side. This
file has no opinion on *which* vocabulary a caller passes (raw `users.roles`
strings like "applicant"/"instructor", or `contacts.contact_roles` values like
"student"/"parent_guardian") — that choice is the caller's, so a single
staff account's promotion (applicant -> instructor) reads with the real role
names, not the collapsed contact_roles bucket.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.spine.contact_role_event import ContactRoleEvent


async def record_role_diff(
    db: AsyncSession,
    contact_id: UUID,
    before: list[str] | None,
    after: list[str] | None,
    *,
    source: str,
    changed_by_user_id: UUID | None = None,
    occurred_at: datetime | None = None,
) -> None:
    """Diff two role snapshots and append one ContactRoleEvent per role that
    appeared or disappeared. No-op if before == after. Flushes but never
    commits — part of the caller's transaction."""
    before_set = set(before or [])
    after_set = set(after or [])
    added = after_set - before_set
    removed = before_set - after_set
    if not added and not removed:
        return

    when = occurred_at or datetime.now(timezone.utc)
    for role in sorted(added):
        db.add(ContactRoleEvent(
            contact_id=contact_id, role=role, action="added",
            source=source, changed_by_user_id=changed_by_user_id, occurred_at=when,
        ))
    for role in sorted(removed):
        db.add(ContactRoleEvent(
            contact_id=contact_id, role=role, action="removed",
            source=source, changed_by_user_id=changed_by_user_id, occurred_at=when,
        ))
    await db.flush()

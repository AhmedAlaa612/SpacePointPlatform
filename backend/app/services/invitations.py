"""Invite-code validation — checks the admin-managed `invitation_codes`
table first, falls back to an ambassador's own `users.invite_code` referral.

Extracted 2026-08-08 from `routers/auth.py::instructor_apply` (where this
logic originated) and `validate_invite` (which had its own copy) so LMS
student signup can reuse the exact same rule rather than a third copy.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instructors.invitation_code import InvitationCode
from app.models.user import User


async def resolve_invite_code(
    db: AsyncSession, code: str | None, *, kind: str | None = None
) -> tuple[InvitationCode | None, User | None]:
    """Blank code -> (None, None), nothing to do. Otherwise: an admin-issued
    `InvitationCode` match wins first (expiry/usage-limit enforced here —
    caller still owns incrementing `used_count` once the signup actually
    commits); else an active ambassador's own `invite_code` is treated as a
    referral. Raises 400 if a non-blank code matches neither.

    `kind` (2026-08-13) scopes the admin-code lookup to one pool —
    'instructor' or 'student'. A code of the wrong kind is not a match, and
    falls through to the ambassador branch like any unknown code, so it ends
    up as a plain "Invalid or inactive invite code" rather than leaking that
    the code exists for a different signup flow. Passing None keeps the
    old any-kind behaviour for callers that genuinely don't care.

    Ambassador referral codes are deliberately kind-agnostic: an ambassador's
    personal code is a referral, not a batch, and the operator's call
    (2026-08-13) is that it still admits a student.
    """
    if not code:
        return None, None

    normalized = code.strip().upper()

    stmt = select(InvitationCode).where(
        InvitationCode.code == normalized, InvitationCode.is_active.is_(True),
    )
    if kind is not None:
        stmt = stmt.where(InvitationCode.kind == kind)
    invitation = (await db.execute(stmt)).scalars().first()
    if invitation:
        if invitation.expires_at and invitation.expires_at < datetime.now(timezone.utc):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invitation code has expired")
        if invitation.used_count >= invitation.max_uses:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invitation code has reached its usage limit")
        return invitation, None

    ambassador = (await db.execute(
        select(User).where(
            User.invite_code == normalized,
            User.roles.any("ambassador"),
            User.status == "active",
        )
    )).scalars().first()
    if not ambassador:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid or inactive invite code")

    return None, ambassador

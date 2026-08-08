"""resolve_invite_code() (2026-08-08) — extracted from instructor_apply's
inline validation so LMS student signup can reuse the same rule. Covers the
admin-code path (valid/expired/exhausted), the ambassador-referral fallback,
an unknown code, and the blank-code no-op.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.models.instructors.invitation_code import InvitationCode
from app.models.user import User
from app.services.invitations import resolve_invite_code


async def _ambassador(db, *, invite_code: str, status: str = "active") -> User:
    amb = User(
        id=uuid.uuid4(), full_name="Amb", email=f"amb-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["ambassador"], status=status, invite_code=invite_code,
    )
    db.add(amb)
    await db.flush()
    return amb


@pytest.mark.asyncio
async def test_blank_code_is_a_noop(db):
    assert await resolve_invite_code(db, None) == (None, None)
    assert await resolve_invite_code(db, "") == (None, None)


@pytest.mark.asyncio
async def test_valid_admin_code_returned_uppercased_and_stripped(db):
    code = InvitationCode(id=uuid.uuid4(), code="LAUNCH2026", is_active=True, max_uses=5, used_count=0)
    db.add(code)
    await db.commit()

    invitation, ambassador = await resolve_invite_code(db, "  launch2026  ")
    assert ambassador is None
    assert invitation is not None and invitation.id == code.id


@pytest.mark.asyncio
async def test_expired_admin_code_is_400(db):
    code = InvitationCode(
        id=uuid.uuid4(), code="EXPIRED1", is_active=True,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db.add(code)
    await db.commit()

    with pytest.raises(HTTPException) as exc:
        await resolve_invite_code(db, "EXPIRED1")
    assert exc.value.status_code == 400
    assert "expired" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_exhausted_admin_code_is_400(db):
    code = InvitationCode(id=uuid.uuid4(), code="MAXEDOUT", is_active=True, max_uses=3, used_count=3)
    db.add(code)
    await db.commit()

    with pytest.raises(HTTPException) as exc:
        await resolve_invite_code(db, "MAXEDOUT")
    assert exc.value.status_code == 400
    assert "usage limit" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_ambassador_referral_code_matches_case_insensitively(db):
    amb = await _ambassador(db, invite_code="AMBASSADOR1")
    await db.commit()

    invitation, ambassador = await resolve_invite_code(db, "ambassador1")
    assert invitation is None
    assert ambassador is not None and ambassador.id == amb.id


@pytest.mark.asyncio
async def test_inactive_ambassador_code_is_400(db):
    await _ambassador(db, invite_code="INACTIVE1", status="inactive")
    await db.commit()

    with pytest.raises(HTTPException) as exc:
        await resolve_invite_code(db, "INACTIVE1")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_unknown_code_is_400(db):
    with pytest.raises(HTTPException) as exc:
        await resolve_invite_code(db, "NOSUCHCODE")
    assert exc.value.status_code == 400
    assert "invalid" in exc.value.detail.lower()

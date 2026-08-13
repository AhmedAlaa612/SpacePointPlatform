import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.db.base import Base
from sqlalchemy.dialects.postgresql import UUID


class InvitationCode(Base):
    """Admin-managed invitation codes (distinct from an ambassador's
    users.invite_code referral field — both are checked on /apply/instructor).

    `kind` splits the pool (2026-08-13): 'instructor' codes let someone apply
    as an instructor, 'student' codes let someone sign up to the LMS. One
    pool served both until student signup became a required gate, at which
    point a code issued for a school batch would also have unlocked
    instructor applications. `resolve_invite_code` takes the expected kind
    and will not match across it.

    `label` is the batch's human name ("Fall 2026 Batch"), carried over from
    Madar where `invitation_codes` doubled as cohort identity — it's what the
    students-management filter shows instead of a raw code.
    """

    __tablename__ = "invitation_codes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(100), unique=True, nullable=False, index=True)
    # instructor|student
    kind = Column(String(16), nullable=False, default="instructor", server_default="instructor", index=True)
    label = Column(String(120), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    max_uses = Column(Integer, nullable=False, default=20)
    used_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

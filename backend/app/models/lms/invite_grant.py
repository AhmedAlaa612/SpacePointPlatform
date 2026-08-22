"""Invite-code course/path grants (2026-08-21) — a school/cohort batch code
(`InvitationCode`, kind='student') can carry a standing list of courses or
learning-path bundles that everyone who used it gets for free, no Stripe
checkout involved. The code IS the batch (same `users.invitation_code_used`
string-match idiom the invite-codes admin screen already uses) — this is
deliberately not a new generic groups/audiences table (§3 of `BulkGrantIn`'s
own docstring rules that out); it only exists because InvitationCode already
serves as the batch primitive in this codebase.

Applies to both new signups (`routers/auth.py::student_signup`, right where
`invitation.used_count` is bumped) and retroactively to everyone who already
used the code (`services/lms/invite_grants.py::grant_invite_code_access`,
called the moment ops attaches the grant). Removing a grant only stops it
applying going forward — it does not revoke enrollments already made,
mirroring how deleting a `LearningPath` never touches its students' access.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class InvitationCodeGrant(Base):
    """`product_type` is "course" | "learning_path" — same flat-string
    discriminator idiom as `Purchase.product_type`, not a DB-enforced
    polymorphic FK. Duplicate grants (same code + same course/path) are
    rejected at the service layer with a 409, not a DB constraint — same
    posture as `LmsProgramItem`'s conflict checks."""

    __tablename__ = "invitation_code_grants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invitation_code_id = Column(
        UUID(as_uuid=True), ForeignKey("invitation_codes.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    product_type = Column(String(16), nullable=False)  # "course" | "learning_path"
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=True)
    learning_path_id = Column(
        UUID(as_uuid=True), ForeignKey("learning_paths.id", ondelete="CASCADE"), nullable=True
    )
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

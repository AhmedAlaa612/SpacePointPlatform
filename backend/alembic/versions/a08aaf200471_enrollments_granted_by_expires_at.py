"""enrollments.granted_by + enrollments.expires_at (P1-3, LMS Phase 2 Stage 1, 2026-08-10).

Both nullable, both no-ops for every existing row (NULL = "nobody granted
this" / "perpetual"). The access-check predicate that actually reads
expires_at lands in the same commit as this migration (routers/lms/student.py
::_assert_enrolled) — per the audit (LMS_DESIGN_AUDIT.md §9.3(c)), a column
that exists without the gate reading it is expiry that *looks* implemented
and silently isn't.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a08aaf200471"
down_revision = "85cc0825c220"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "enrollments",
        sa.Column("granted_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column("enrollments", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("enrollments", "expires_at")
    op.drop_column("enrollments", "granted_by")

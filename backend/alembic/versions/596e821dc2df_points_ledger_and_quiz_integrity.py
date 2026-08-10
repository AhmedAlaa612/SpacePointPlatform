"""point_events + item_progress quiz-integrity columns (P2-1/P2-3, LMS
Phase 2 Stage 2, 2026-08-10).

point_events is the whole ledger — append-only, UNIQUE(user_id, source,
idempotency_key) is the idempotency mechanism, a total is always a
SUM...GROUP BY, never a cached column (see models/lms/points.py).

item_progress gains hints_used (incremented by the live per-question
check endpoint) and first_score/first_scored_at (written once by
submit_quiz, never updated) — the audit's §9.2 fix for the quiz answer
oracle: the point award keys on the first submission, never on
best_score, because submit_quiz's own review sheet leaks every
correct_text on unlimited retries.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "596e821dc2df"
down_revision = "a08aaf200471"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "point_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("ref", postgresql.JSONB(), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "source", "idempotency_key", name="uq_point_events_user_source_key"),
    )
    op.create_index("ix_point_events_user_id", "point_events", ["user_id"])

    op.add_column("item_progress", sa.Column("hints_used", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("item_progress", sa.Column("first_score", sa.Numeric(5, 2), nullable=True))
    op.add_column("item_progress", sa.Column("first_scored_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("item_progress", "first_scored_at")
    op.drop_column("item_progress", "first_score")
    op.drop_column("item_progress", "hints_used")
    op.drop_index("ix_point_events_user_id", table_name="point_events")
    op.drop_table("point_events")

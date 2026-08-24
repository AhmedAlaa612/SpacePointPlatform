"""Instructor daily loop: checklist, attendance and day approval

Operations process doc §4-§12, scoped in by the operator on 2026-08-24. Until
now nothing recorded whether the *instructor* turned up (only students have
attendance), nor what they did on the day beyond one optional file upload.
That matters beyond record-keeping: §18 makes an ops-approved day the
eligibility gate for payment, and the cohort-aggregated payment line landing
in the next migration counts approved days, not assigned ones.

`delivery_checklist_items` copies `session_materials`' three-level shape,
CHECK included — attached at exactly one of program/cohort/session and
resolved override-not-merge, the nearest level with any rows winning outright.
See the model docstring for why this is not built on the applicant-onboarding
`checklist_items` tables in the instructors domain.

`instructor_session_days` holds attendance and the day submission in one row,
because they are the same object seen from two sides. `status='approved'` AND
`att_status='present'` is the definition of a paid day; approved + absent is
an acknowledged absence, recorded but not paid.

`instructor_checklist_progress` points its proof at an existing
`session_reports` row rather than introducing a second upload path — the
bucket, the service, the assigned-instructor check and the ops-facing list all
already exist. SET NULL so deleting a file leaves the tick readable.

No backfill: there is nothing to backfill from. Sessions delivered before this
existed have no per-instructor day rows, and the payment accrual in the next
migration treats a cohort with no day rows as "not yet reviewed" rather than
inventing approvals nobody gave.

Revision ID: c7b34e18d902
Revises: f2a91c47b013
Create Date: 2026-08-24
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "c7b34e18d902"
down_revision = "f2a91c47b013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "delivery_checklist_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("program_id", UUID(as_uuid=True), sa.ForeignKey("programs.id", ondelete="CASCADE"), nullable=True),
        sa.Column("cohort_id", UUID(as_uuid=True), sa.ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=True),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("requires_proof", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(CASE WHEN program_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN cohort_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN session_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_delivery_checklist_exactly_one_owner",
        ),
    )
    op.create_index("ix_delivery_checklist_items_program_id", "delivery_checklist_items", ["program_id"])
    op.create_index("ix_delivery_checklist_items_cohort_id", "delivery_checklist_items", ["cohort_id"])
    op.create_index("ix_delivery_checklist_items_session_id", "delivery_checklist_items", ["session_id"])

    op.create_table(
        "instructor_session_days",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("att_status", sa.String(16), nullable=True),
        sa.Column("absence_reason", sa.Text(), nullable=True),
        sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=True),
        sa.Column("instructor_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("session_id", "user_id", name="uq_instructor_session_day"),
    )
    op.create_index("ix_instructor_session_days_session_id", "instructor_session_days", ["session_id"])
    op.create_index("ix_instructor_session_days_user_id", "instructor_session_days", ["user_id"])

    op.create_table(
        "instructor_checklist_progress",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "day_id", UUID(as_uuid=True),
            sa.ForeignKey("instructor_session_days.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "checklist_item_id", UUID(as_uuid=True),
            sa.ForeignKey("delivery_checklist_items.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("is_done", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "proof_report_id", UUID(as_uuid=True),
            sa.ForeignKey("session_reports.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("day_id", "checklist_item_id", name="uq_instructor_checklist_progress"),
    )
    op.create_index("ix_instructor_checklist_progress_day_id", "instructor_checklist_progress", ["day_id"])


def downgrade() -> None:
    op.drop_index("ix_instructor_checklist_progress_day_id", table_name="instructor_checklist_progress")
    op.drop_table("instructor_checklist_progress")

    op.drop_index("ix_instructor_session_days_user_id", table_name="instructor_session_days")
    op.drop_index("ix_instructor_session_days_session_id", table_name="instructor_session_days")
    op.drop_table("instructor_session_days")

    op.drop_index("ix_delivery_checklist_items_session_id", table_name="delivery_checklist_items")
    op.drop_index("ix_delivery_checklist_items_cohort_id", table_name="delivery_checklist_items")
    op.drop_index("ix_delivery_checklist_items_program_id", table_name="delivery_checklist_items")
    op.drop_table("delivery_checklist_items")

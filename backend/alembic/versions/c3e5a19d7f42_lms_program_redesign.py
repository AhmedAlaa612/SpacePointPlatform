"""LMS Program redesign — checklist-driven programs (2026-08-21)

Replaces `program_curriculum`/`cohort_curriculum` (a flat, course-only
list) with a real checklist: `lms_programs` (template, attached to a
Sessions `programs` row) x `lms_program_cohort_overrides` (a cohort's own
checklist, replacing its program's outright — same nearest-wins idiom the
old tables used) x `lms_program_items` (course/mission_run/external_link/
submission/article/manual steps, polymorphic owner) x
`lms_program_assignments` (one student's instance) x
`lms_program_item_progress` (per-student per-item completion).

`program_curriculum`/`cohort_curriculum` are dropped outright rather than
migrated — confirmed empty in production (no LMS students registered
yet) by the operator, 2026-08-21.

Revision ID: c3e5a19d7f42
Revises: 8b3f21a0e6c1
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c3e5a19d7f42"
down_revision = "8b3f21a0e6c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("cohort_curriculum")
    op.drop_table("program_curriculum")

    op.create_table(
        "lms_programs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("program_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("programs.id", ondelete="CASCADE"), nullable=True, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("certificate_required", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "lms_program_cohort_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("cohort_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("lms_program_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lms_programs.id", ondelete="CASCADE"), nullable=False),
    )

    op.create_table(
        "lms_program_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_type", sa.String(16), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("item_type", sa.String(16), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("optional", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("requires_confirmation", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=True),
        sa.Column("mission_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("missions.id", ondelete="CASCADE"), nullable=True),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mission_variants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("external_url", sa.String(512), nullable=True),
        sa.Column("submission_prompt", sa.Text(), nullable=True),
        sa.UniqueConstraint("owner_type", "owner_id", "position", name="uq_lms_program_items_owner_position"),
        sa.UniqueConstraint("owner_type", "owner_id", "course_id", name="uq_lms_program_items_owner_course"),
    )
    op.create_index("ix_lms_program_items_owner", "lms_program_items", ["owner_type", "owner_id"])

    op.create_table(
        "lms_program_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lms_program_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lms_programs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cohort_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cohorts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("registration_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("registrations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "cohort_id", name="uq_lms_program_assignments_user_cohort"),
    )

    op.create_table(
        "lms_program_item_progress",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lms_program_assignments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lms_program_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("mission_attempt_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mission_attempts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("submitted_url", sa.String(512), nullable=True),
        sa.UniqueConstraint("assignment_id", "item_id", name="uq_lms_program_item_progress_assignment_item"),
    )


def downgrade() -> None:
    op.drop_table("lms_program_item_progress")
    op.drop_table("lms_program_assignments")
    op.drop_index("ix_lms_program_items_owner", table_name="lms_program_items")
    op.drop_table("lms_program_items")
    op.drop_table("lms_program_cohort_overrides")
    op.drop_table("lms_programs")

    op.create_table(
        "program_curriculum",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("program_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("programs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("program_id", "course_id", name="uq_program_curriculum_program_course"),
        sa.UniqueConstraint("program_id", "position", name="uq_program_curriculum_program_position"),
    )
    op.create_table(
        "cohort_curriculum",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("cohort_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("cohort_id", "course_id", name="uq_cohort_curriculum_cohort_course"),
        sa.UniqueConstraint("cohort_id", "position", name="uq_cohort_curriculum_cohort_position"),
    )
    op.create_index("ix_cohort_curriculum_cohort_id", "cohort_curriculum", ["cohort_id"])

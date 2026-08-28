"""Competition domain, stage 1: program_type="competition" + team-scoped items (2026-08-24)

Opening move of the Competition domain (Ru'ya Space Race first), per the
boss-approved plan. Two additive pieces, nothing existing changes shape:

- A competition is just a `Program` whose `program_type` is `"competition"`
  — no new column. `program_type` is a plain `String(24)`, not a DB-level
  enum, so this needed no schema change at all; `Program.is_competition`
  (see `models/sessions/program.py`) is a read-only Python property over
  it, kept so the many `program.is_competition` call sites in
  services/competitions/ didn't need touching.
- `lms_program_items.scope` (`individual`|`team`, default `individual`) —
  every existing item stays individual, unchanged. `team` is for a
  competition's link-only deliverables (poster, video, circuit, CAD,
  dashboard) where the whole team shares one submission.
- `lms_program_team_item_progress` — mirrors `lms_program_item_progress`
  exactly (see `models/lms/program.py`'s docstring), keyed by `(item_id,
  team_id)` instead of `(item_id, assignment_id)`, so a team-scoped item's
  progress is one shared row every member reads and writes, rather than
  bolting a nullable second key onto the existing per-student table.

`learner_teams` (2026-08-17) already exists — this is the first thing
outside Missions to actually reference it, exactly as its own docstring
anticipated ("Competition needs teams too").

Revision ID: 18143df669a7
Revises: b5d477e213ed
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "18143df669a7"
down_revision = "b5d477e213ed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "lms_program_items",
        sa.Column("scope", sa.String(16), nullable=False, server_default="individual"),
    )

    op.create_table(
        "lms_program_team_item_progress",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lms_program_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("learner_teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("submitted_url", sa.String(512), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("item_id", "team_id", name="uq_lms_program_team_item_progress_item_team"),
    )
    op.create_index(
        "ix_lms_program_team_item_progress_team_id", "lms_program_team_item_progress", ["team_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_lms_program_team_item_progress_team_id", table_name="lms_program_team_item_progress")
    op.drop_table("lms_program_team_item_progress")
    op.drop_column("lms_program_items", "scope")

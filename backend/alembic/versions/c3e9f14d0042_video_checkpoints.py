"""video checkpoints — timeline notes and mid-video quizzes on video items (2026-08-07)

Mid-video quizzes used to be authored as a *separate* `quiz` module item
carrying `mid_video_at_seconds`, linked to "the module's one video item" by a
service-level rule. The operator correctly called that out as backwards — in
the design (and in every reference product, e.g. Coursera) a checkpoint is
authored *on the video itself*, at a timestamp, and shows up as a marker on
the video's own scrubber. `video_checkpoints` makes that the real model:
every checkpoint (note or quiz) is a child row of the video item it belongs
to, positioned by `start_seconds` (and `end_seconds` for notes — a note is a
banner shown for a window, not an instant; a quiz has no duration, it just
pauses at one moment, so `end_seconds` stays null for that kind).

`content` is JSONB for the same reason `module_items.content` is (LMS_EXECUTION_PLAN.md
§2): the authored shape is read as a whole unit, never filtered or joined,
and the two kinds (note/quiz) don't share fields. Quiz `content` carries
`question_type` (mcq|multiselect|open) — `correct` answers live here since
this is the authoring/storage row; the student-facing route strips them the
same way `services/lms/serialize.py` already does for module quiz items.

Revision ID: c3e9f14d0042
Revises: a1f4c73d0041
Create Date: 2026-08-07
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "c3e9f14d0042"
down_revision = "a1f4c73d0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "video_checkpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "item_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("module_items.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("start_seconds", sa.Integer(), nullable=False),
        # null for quiz checkpoints (a single moment, not a window)
        sa.Column("end_seconds", sa.Integer(), nullable=True),
        # note|quiz
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.create_index(
        "ix_video_checkpoints_item_id", "video_checkpoints", ["item_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_video_checkpoints_item_id", table_name="video_checkpoints")
    op.drop_table("video_checkpoints")

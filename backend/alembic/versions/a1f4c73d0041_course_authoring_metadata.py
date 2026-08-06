"""course authoring metadata — image, outcomes, level, track, instructor (LMS redesign, 2026-08-06)

The redesigned student surface (LMS_REDESIGN_FOLLOWUPS.md #2) assumes a course
has a cover image, an outcomes checklist, a level/track for catalog filtering,
and an instructor to show on the course landing page — none of which existed
on `courses`, and none of which the authoring UI could set. All nullable/
defaulted so every existing course keeps working unauthored.

`instructor_id` is a plain nullable FK to `users`, SET NULL on delete (an
instructor leaving doesn't need to take their courses' metadata down with
them) — deliberately not `created_by`, which stays what it always was: who
authored the content, not who's the public-facing instructor.

Revision ID: a1f4c73d0041
Revises: e2f7a93d0040
Create Date: 2026-08-06
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "a1f4c73d0041"
down_revision = "e2f7a93d0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("courses", sa.Column("image_bucket", sa.String(64), nullable=True))
    op.add_column("courses", sa.Column("image_path", sa.String(512), nullable=True))
    op.add_column(
        "courses", sa.Column("outcomes", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    # beginner|intermediate|advanced — free-text VARCHAR, same idiom as
    # courses.kind, not a DB enum (LMS convention throughout this schema).
    op.add_column("courses", sa.Column("level", sa.String(20), nullable=True))
    # Free-text catalog grouping (e.g. "Spacecraft systems") — no fixed
    # taxonomy yet; a real category table is a later decision, not blocking.
    op.add_column("courses", sa.Column("track", sa.String(80), nullable=True))
    op.add_column(
        "courses",
        sa.Column(
            "instructor_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
    )
    op.add_column("courses", sa.Column("instructor_title", sa.String(120), nullable=True))


def downgrade() -> None:
    op.drop_column("courses", "instructor_title")
    op.drop_column("courses", "instructor_id")
    op.drop_column("courses", "track")
    op.drop_column("courses", "level")
    op.drop_column("courses", "outcomes")
    op.drop_column("courses", "image_path")
    op.drop_column("courses", "image_bucket")

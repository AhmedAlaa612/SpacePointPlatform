"""Add course_ratings table.

Revision ID: b1a2c3d4e5f6
Revises: a8c4e2f91b05
Create Date: 2026-10-25 04:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b1a2c3d4e5f6"
down_revision: Union[str, None] = "a8c4e2f91b05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "course_ratings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("review_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("rating >= 1 AND rating <= 5", name="ck_course_ratings_rating_range"),
        sa.UniqueConstraint("user_id", "course_id", name="uq_course_ratings_user_course"),
    )
    op.create_index("ix_course_ratings_user_id", "course_ratings", ["user_id"], unique=False)
    op.create_index("ix_course_ratings_course_id", "course_ratings", ["course_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_course_ratings_course_id", table_name="course_ratings")
    op.drop_index("ix_course_ratings_user_id", table_name="course_ratings")
    op.drop_table("course_ratings")

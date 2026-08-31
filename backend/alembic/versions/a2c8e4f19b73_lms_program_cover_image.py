"""LMS program checklist cover image (2026-08-31)

Adds a header/cover image to `LmsProgram`, the same bucket/path-only shape
`Course`/`LearningPath` already use — the URL is never stored, only resolved
fresh at read time via storage.resolve_url.

Revision ID: a2c8e4f19b73
Revises: e4b7d92a5c18
"""

import sqlalchemy as sa
from alembic import op

revision = "a2c8e4f19b73"
down_revision = "e4b7d92a5c18"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("lms_programs", sa.Column("image_bucket", sa.String(length=64), nullable=True))
    op.add_column("lms_programs", sa.Column("image_path", sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column("lms_programs", "image_path")
    op.drop_column("lms_programs", "image_bucket")

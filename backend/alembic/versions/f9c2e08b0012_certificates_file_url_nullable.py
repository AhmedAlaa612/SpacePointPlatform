"""make certificates.file_url nullable — student_completion certs are emailed
directly, not stored; instructor workshop_delivery certs still populate it.

Revision ID: f9c2e08b0012
Revises: e2b5c9d0011
Create Date: 2026-07-25

"""
from alembic import op

revision = "f9c2e08b0012"
down_revision = "e2b5c9d0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Student completion certs are now emailed as PDF attachments and carry
    # no file_url/bucket/file_path. Only instructor workshop_delivery certs
    # still populate these columns. Drop the NOT NULL constraint so the
    # student_completion insert doesn't crash.
    op.alter_column("certificates", "file_url", nullable=True)


def downgrade() -> None:
    # Restore NOT NULL — will fail if any NULL rows exist.
    op.alter_column("certificates", "file_url", nullable=False)

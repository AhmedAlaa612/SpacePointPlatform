"""Add student_id to contacts and users.

Revision ID: f9a3c95e0052
Revises: f8a2c94e0051
Create Date: 2026-11-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f9a3c95e0052"
down_revision: Union[str, None] = "f8a2c94e0051"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("contacts", sa.Column("student_id", sa.String(100), nullable=True))
    op.add_column("users", sa.Column("student_id", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "student_id")
    op.drop_column("contacts", "student_id")

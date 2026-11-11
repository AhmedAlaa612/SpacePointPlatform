"""Add application_reviews deadlines and extension tracking columns.

Revision ID: fc16d08f0055
Revises: fb15d07f0054
Create Date: 2026-11-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "fc16d08f0055"
down_revision: Union[str, None] = "fb15d07f0054"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE application_reviews ADD COLUMN IF NOT EXISTS phase_deadline TIMESTAMPTZ"))
    conn.execute(sa.text("ALTER TABLE application_reviews ADD COLUMN IF NOT EXISTS extension_used BOOLEAN NOT NULL DEFAULT FALSE"))
    conn.execute(sa.text("ALTER TABLE application_reviews ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()"))
    conn.execute(sa.text("ALTER TABLE application_reviews ADD COLUMN IF NOT EXISTS last_status_change_at TIMESTAMPTZ NOT NULL DEFAULT now()"))
    conn.execute(sa.text("""
        UPDATE application_reviews ar
        SET created_at = u.created_at,
            last_status_change_at = COALESCE(ar.reviewed_at, ar.submitted_at, u.created_at)
        FROM users u
        WHERE ar.user_id = u.id
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE application_reviews DROP COLUMN IF EXISTS last_status_change_at"))
    conn.execute(sa.text("ALTER TABLE application_reviews DROP COLUMN IF EXISTS created_at"))
    conn.execute(sa.text("ALTER TABLE application_reviews DROP COLUMN IF EXISTS extension_used"))
    conn.execute(sa.text("ALTER TABLE application_reviews DROP COLUMN IF EXISTS phase_deadline"))

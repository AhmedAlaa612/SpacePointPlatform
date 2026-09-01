"""learning_paths.access_mode (2026-09-01).

Mirrors `courses.access_mode` (85cc0825c220): open|invite|paid. Existing
paths default to 'open', which is exactly today's self-`/start` behaviour,
so this is a no-op for every existing row. `invite` paths are hidden from
`GET /lms/learning-paths` and 403/404 on detail/`/start` unless the caller
already holds an active enrollment — only an admin/invite-code grant gets
someone in, same posture as invite-mode courses.

Revision ID: e8a85d1c464b
Revises: c8e1f9a4d2b6
Create Date: 2026-09-01
"""

import sqlalchemy as sa
from alembic import op

revision = "e8a85d1c464b"
down_revision = "c8e1f9a4d2b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "learning_paths",
        sa.Column("access_mode", sa.String(12), nullable=False, server_default="open"),
    )


def downgrade() -> None:
    op.drop_column("learning_paths", "access_mode")

"""Give a user a persistent default avatar.

Avatars previously existed only on `game_participants` — chosen in a lobby,
discarded with the run. That left nothing for an admin (or the student
outside a lobby) to actually set, which is why "change his avatar" had no
answer. The run still snapshots its own value; this is what it defaults
from.

Revision ID: c7a2e5f1d093
Revises: b3f1c9d47a10
"""

import sqlalchemy as sa
from alembic import op

revision = "c7a2e5f1d093"
down_revision = "b3f1c9d47a10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "avatar")

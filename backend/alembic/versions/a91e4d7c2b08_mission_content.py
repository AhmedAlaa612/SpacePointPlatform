"""missions.content — authored explanatory content (Design v2, 7D-8 / D8)

Splits what a published mission may change. `mission_variants.config` holds
grading criteria and is frozen once published, because editing a threshold
retroactively changes what already-graded attempts were measured against.
`missions.content` holds explanation — briefing copy, handbook wording,
advice text — and is always editable, by staff and by that mission's
assigned manager.

That split is what makes an intern mission-owner useful rather than
decorative: they can improve how the mission teaches without being able to
move the goalposts.

Stores *overrides* only. Anything absent falls back to the authored
defaults in `services/missions/design/content.py`, so a mission with an
empty `content` behaves exactly as it does today.

Revision ID: a91e4d7c2b08
Revises: f8c3d21b7e45
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a91e4d7c2b08"
down_revision = "f8c3d21b7e45"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "missions",
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()),
                  server_default=sa.text("'{}'::jsonb"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("missions", "content")

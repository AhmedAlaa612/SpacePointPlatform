"""Drop sessions.price — per-session price override retired

Operator ask (2026-08-30): people pay for the program/cohort, not a
specific session, and per-session pricing was never wired to a real
payment processor anyway (`price_charged` was only ever a recorded number
for desk/invoice tracking). `resolve_registration_price` now always uses
the program's own price; ops can no longer set a per-session override
through the API.

Revision ID: c4d9e2f6a813
Revises: b3f8c6a91d47
Create Date: 2026-08-30
"""

import sqlalchemy as sa
from alembic import op

revision = "c4d9e2f6a813"
down_revision = "b3f8c6a91d47"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("sessions", "price")


def downgrade() -> None:
    op.add_column("sessions", sa.Column("price", sa.Numeric(10, 2), nullable=True))

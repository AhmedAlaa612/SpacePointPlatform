"""ground_station_devices (2026-09) — the ported LoRa-Dashboard-V3 ground
station tool. Only new table: telemetry/commands/photos flow over Redis
pub/sub + R2, never a new time-series table (see models/ground_station/__init__.py).

Revision ID: 16162b6766ae
Revises: e1c9a4f2d685
Create Date: 2026-09-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = '16162b6766ae'
down_revision: Union[str, None] = 'e1c9a4f2d685'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'ground_station_devices',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('label', sa.String(length=128), nullable=False),
        sa.Column('secret_hash', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=8), nullable=False, server_default='offline'),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('ground_station_devices')

"""ground_station_history_alerts_images (2026-09) — full legacy parity pass:
telemetry history, alert thresholds/alerts, and the image registry, ported
from the legacy app's `telemetry`/`alert_thresholds`/`alerts`/`images` tables.

Revision ID: 7964f705a198
Revises: 16162b6766ae
Create Date: 2026-09-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = '7964f705a198'
down_revision: Union[str, None] = '16162b6766ae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'ground_station_telemetry',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('device_id', UUID(as_uuid=True), sa.ForeignKey('ground_station_devices.id', ondelete='CASCADE'), nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('temp', sa.Float(), nullable=True),
        sa.Column('voltage', sa.Float(), nullable=True),
        sa.Column('current', sa.Float(), nullable=True),
        sa.Column('power', sa.Float(), nullable=True),
        sa.Column('rssi', sa.Float(), nullable=True),
        sa.Column('snr', sa.Float(), nullable=True),
        sa.Column('uptime', sa.Integer(), nullable=True),
        sa.Column('lat', sa.Float(), nullable=True),
        sa.Column('lon', sa.Float(), nullable=True),
        sa.Column('alt', sa.Float(), nullable=True),
        sa.Column('pitch', sa.Float(), nullable=True),
        sa.Column('roll', sa.Float(), nullable=True),
        sa.Column('yaw', sa.Float(), nullable=True),
        sa.Column('data', JSONB(), nullable=False, server_default='{}'),
    )
    op.create_index('ix_ground_station_telemetry_device_recorded', 'ground_station_telemetry', ['device_id', 'recorded_at'])

    op.create_table(
        'ground_station_alert_thresholds',
        sa.Column('device_id', UUID(as_uuid=True), sa.ForeignKey('ground_station_devices.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('temp_max', sa.Float(), nullable=False, server_default='35.0'),
        sa.Column('temp_min', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('voltage_max', sa.Float(), nullable=False, server_default='5.5'),
        sa.Column('voltage_min', sa.Float(), nullable=False, server_default='3.0'),
        sa.Column('current_max', sa.Float(), nullable=False, server_default='1.0'),
        sa.Column('power_max', sa.Float(), nullable=False, server_default='2.0'),
    )

    op.create_table(
        'ground_station_alerts',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('device_id', UUID(as_uuid=True), sa.ForeignKey('ground_station_devices.id', ondelete='CASCADE'), nullable=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('alert_type', sa.String(length=16), nullable=False),
        sa.Column('threshold', sa.Float(), nullable=False),
        sa.Column('current_value', sa.Float(), nullable=False),
        sa.Column('severity', sa.String(length=16), nullable=False, server_default='critical'),
        sa.Column('acknowledged', sa.Boolean(), nullable=False, server_default='false'),
    )
    op.create_index('ix_ground_station_alerts_device_time', 'ground_station_alerts', ['device_id', 'occurred_at'])

    op.create_table(
        'ground_station_images',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('device_id', UUID(as_uuid=True), sa.ForeignKey('ground_station_devices.id', ondelete='CASCADE'), nullable=False),
        sa.Column('bucket', sa.String(length=64), nullable=False, server_default='ground-station'),
        sa.Column('path', sa.String(length=512), nullable=False),
        sa.Column('lat', sa.Float(), nullable=True),
        sa.Column('lon', sa.Float(), nullable=True),
        sa.Column('alt', sa.Float(), nullable=True),
        sa.Column('captured_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_ground_station_images_device_time', 'ground_station_images', ['device_id', 'captured_at'])


def downgrade() -> None:
    op.drop_table('ground_station_images')
    op.drop_table('ground_station_alerts')
    op.drop_table('ground_station_alert_thresholds')
    op.drop_table('ground_station_telemetry')

"""ground_station_mission_ownership (2026-09-14) — devices are now
provisioned per MissionAttempt (solo or team), private to that owner +
staff. secret_hash becomes nullable: ingest no longer checks it (operator
directive: no auth on ingest).

Revision ID: cacc3b82a3ee
Revises: 7964f705a198
Create Date: 2026-09-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = 'cacc3b82a3ee'
down_revision: Union[str, None] = '7964f705a198'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('ground_station_devices', 'secret_hash', nullable=True)
    op.add_column(
        'ground_station_devices',
        sa.Column('mission_attempt_id', UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_ground_station_devices_mission_attempt_id', 'ground_station_devices',
        'mission_attempts', ['mission_attempt_id'], ['id'], ondelete='CASCADE',
    )
    op.create_unique_constraint(
        'uq_ground_station_devices_mission_attempt_id', 'ground_station_devices', ['mission_attempt_id'],
    )


def downgrade() -> None:
    op.drop_constraint('uq_ground_station_devices_mission_attempt_id', 'ground_station_devices', type_='unique')
    op.drop_constraint('fk_ground_station_devices_mission_attempt_id', 'ground_station_devices', type_='foreignkey')
    op.drop_column('ground_station_devices', 'mission_attempt_id')
    op.alter_column('ground_station_devices', 'secret_hash', nullable=False)

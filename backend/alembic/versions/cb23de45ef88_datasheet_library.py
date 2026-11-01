"""datasheet library table and initial seeds

Revision ID: cb23de45ef88
Revises: ca12bc34de77
Create Date: 2026-11-01 00:30:00.000000

"""
import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "cb23de45ef88"
down_revision = "ca12bc34de77"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create pre_session_quiz_datasheets table
    op.create_table(
        "pre_session_quiz_datasheets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("url", sa.String(512), nullable=False),
        sa.Column("doc_type", sa.String(64), nullable=False, server_default="datasheet"),
        sa.Column("subsystem_tag", sa.String(64), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(512), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(
        "ix_pre_session_quiz_datasheets_subsystem_tag",
        "pre_session_quiz_datasheets",
        ["subsystem_tag"],
    )

    # 2. Seed initial standard hardware datasheets into library
    initial_datasheets = [
        {
            "id": uuid.uuid4(),
            "title": "ESP32-WROOM-32D CDHS Microcontroller Datasheet",
            "url": "/storage/docs/datasheets/esp32_wroom_32d_datasheet.pdf",
            "doc_type": "datasheet",
            "subsystem_tag": "CDHS",
            "description": "Standard CDHS main compute module with dual-core Xtensa 32-bit LX6, SPI master, and I2C buses.",
        },
        {
            "id": uuid.uuid4(),
            "title": "INA219 Zero-Drift Bi-directional Current/Power Monitor",
            "url": "/storage/docs/datasheets/ina219_power_monitor_datasheet.pdf",
            "doc_type": "datasheet",
            "subsystem_tag": "EPS",
            "description": "EPS subsystem I2C digital power and current monitor with programmable calibration.",
        },
        {
            "id": uuid.uuid4(),
            "title": "BNO055 Intelligent 9-Axis Absolute Orientation Sensor",
            "url": "/storage/docs/datasheets/bno055_orientation_sensor.pdf",
            "doc_type": "datasheet",
            "subsystem_tag": "ADCS/APC",
            "description": "ADCS subsystem attitude sensor with integrated sensor fusion and triaxial accelerometer/gyro/geomagnetic sensor.",
        },
        {
            "id": uuid.uuid4(),
            "title": "SX1278 Long-Range LoRa RF Transceiver",
            "url": "/storage/docs/datasheets/sx1278_lora_transceiver.pdf",
            "doc_type": "datasheet",
            "subsystem_tag": "COMMS",
            "description": "SpacePoint ground station telemetry downlink and payload communication transceiver.",
        },
        {
            "id": uuid.uuid4(),
            "title": "SpacePoint Hardware Delivery & Connector Reference Guide",
            "url": "/storage/docs/guides/spacepoint_hardware_delivery_guide.pdf",
            "doc_type": "user_guide",
            "subsystem_tag": "CDHS",
            "description": "Step-by-step physical assembly, connector J6 pinout jumpers, and troubleshooting quick reference.",
        },
    ]

    datasheets_table = sa.table(
        "pre_session_quiz_datasheets",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("title", sa.String),
        sa.column("url", sa.String),
        sa.column("doc_type", sa.String),
        sa.column("subsystem_tag", sa.String),
        sa.column("description", sa.Text),
        sa.column("is_active", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )

    now = datetime.now(timezone.utc)
    for ds in initial_datasheets:
        op.execute(
            datasheets_table.insert().values(
                id=ds["id"],
                title=ds["title"],
                url=ds["url"],
                doc_type=ds["doc_type"],
                subsystem_tag=ds["subsystem_tag"],
                description=ds["description"],
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )


def downgrade() -> None:
    op.drop_index("ix_pre_session_quiz_datasheets_subsystem_tag", table_name="pre_session_quiz_datasheets")
    op.drop_table("pre_session_quiz_datasheets")

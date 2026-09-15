"""Telemetry history, alert thresholds/alerts, and the image registry — the
legacy app's `telemetry`/`alert_thresholds`/`alerts`/`images` tables, ported
verbatim in shape (see `backend/serial_reader.py`'s `CREATE TABLE`
statements in the legacy zip). Unlike the rest of this domain, these ARE
persisted: the legacy app's history/alerts/gallery features are genuinely
backed by a database, not just live pub/sub, so full parity requires it."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class GroundStationTelemetry(Base):
    __tablename__ = "ground_station_telemetry"
    __table_args__ = (
        Index("ix_ground_station_telemetry_device_recorded", "device_id", "recorded_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id = Column(UUID(as_uuid=True), ForeignKey("ground_station_devices.id", ondelete="CASCADE"), nullable=False)
    recorded_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    temp = Column(Float, nullable=True)
    voltage = Column(Float, nullable=True)
    current = Column(Float, nullable=True)
    power = Column(Float, nullable=True)
    rssi = Column(Float, nullable=True)
    snr = Column(Float, nullable=True)
    uptime = Column(Integer, nullable=True)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    alt = Column(Float, nullable=True)
    pitch = Column(Float, nullable=True)
    roll = Column(Float, nullable=True)
    yaw = Column(Float, nullable=True)
    # The full raw frame — history/stats read the typed columns above, but
    # nothing about a telemetry frame's shape is lost.
    data = Column(JSONB, nullable=False, default=dict)


class GroundStationAlertThreshold(Base):
    __tablename__ = "ground_station_alert_thresholds"

    device_id = Column(UUID(as_uuid=True), ForeignKey("ground_station_devices.id", ondelete="CASCADE"), primary_key=True)
    temp_max = Column(Float, nullable=False, default=35.0, server_default="35.0")
    temp_min = Column(Float, nullable=False, default=0.0, server_default="0.0")
    voltage_max = Column(Float, nullable=False, default=5.5, server_default="5.5")
    voltage_min = Column(Float, nullable=False, default=3.0, server_default="3.0")
    current_max = Column(Float, nullable=False, default=1.0, server_default="1.0")
    power_max = Column(Float, nullable=False, default=2.0, server_default="2.0")


class GroundStationAlert(Base):
    __tablename__ = "ground_station_alerts"
    __table_args__ = (
        Index("ix_ground_station_alerts_device_time", "device_id", "occurred_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id = Column(UUID(as_uuid=True), ForeignKey("ground_station_devices.id", ondelete="CASCADE"), nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    alert_type = Column(String(16), nullable=False)  # temp|voltage|current|power
    threshold = Column(Float, nullable=False)
    current_value = Column(Float, nullable=False)
    severity = Column(String(16), nullable=False, default="critical", server_default="critical")
    acknowledged = Column(Boolean, nullable=False, default=False, server_default="false")


class GroundStationImage(Base):
    __tablename__ = "ground_station_images"
    __table_args__ = (
        Index("ix_ground_station_images_device_time", "device_id", "captured_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id = Column(UUID(as_uuid=True), ForeignKey("ground_station_devices.id", ondelete="CASCADE"), nullable=False)
    bucket = Column(String(64), nullable=False, default="ground-station", server_default="ground-station")
    path = Column(String(512), nullable=False)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    alt = Column(Float, nullable=True)
    captured_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

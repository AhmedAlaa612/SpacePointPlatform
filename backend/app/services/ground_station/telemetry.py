"""Telemetry persistence, threshold/alert checking, and the image registry —
ported from the legacy app's `process_telemetry`/`check_thresholds`/
`create_alert` (`backend/serial_reader.py` in the legacy zip). Field-name
dual support (`temp_C` vs `temp`, etc.) is intentional: real firmware in
the wild used both, and the legacy backend accepted either.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ground_station.telemetry import (
    GroundStationAlert,
    GroundStationAlertThreshold,
    GroundStationImage,
    GroundStationTelemetry,
)

DEFAULT_THRESHOLDS = {
    "temp_max": 35.0, "temp_min": 0.0,
    "voltage_max": 5.5, "voltage_min": 3.0,
    "current_max": 1.0, "power_max": 2.0,
}

# Debounce window — matches the legacy app's 5s "avoid overwhelming the
# user" debounce on repeated threshold violations.
_DEBOUNCE_SECONDS = 5


def _field(data: dict, *names: str) -> float | None:
    for n in names:
        if data.get(n) is not None:
            try:
                return float(data[n])
            except (TypeError, ValueError):
                return None
    return None


async def persist_telemetry(
    db: AsyncSession, device_id: uuid.UUID, data: dict, recorded_at: datetime | None = None,
) -> GroundStationTelemetry:
    row = GroundStationTelemetry(
        id=uuid.uuid4(), device_id=device_id, recorded_at=recorded_at or datetime.now(timezone.utc),
        temp=_field(data, "temp_C", "temp"),
        voltage=_field(data, "bus_voltage_V", "voltage"),
        current=_field(data, "current_mA", "current"),
        power=_field(data, "power_mW", "power"),
        rssi=_field(data, "rssi"),
        snr=_field(data, "snr"),
        uptime=int(v) if (v := _field(data, "uptime")) is not None else None,
        lat=_field(data, "lat"), lon=_field(data, "lon", "lng"), alt=_field(data, "alt"),
        pitch=_field(data, "pitch"), roll=_field(data, "roll"), yaw=_field(data, "yaw"),
        data=data,
    )
    db.add(row)
    await db.flush()
    return row


async def get_history(db: AsyncSession, device_id: uuid.UUID, minutes: int) -> list[GroundStationTelemetry]:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    rows = (await db.execute(
        select(GroundStationTelemetry)
        .where(GroundStationTelemetry.device_id == device_id, GroundStationTelemetry.recorded_at > cutoff)
        .order_by(GroundStationTelemetry.recorded_at.asc())
    )).scalars().all()
    return list(rows)


async def get_latest(db: AsyncSession, device_id: uuid.UUID) -> GroundStationTelemetry | None:
    return (await db.execute(
        select(GroundStationTelemetry)
        .where(GroundStationTelemetry.device_id == device_id)
        .order_by(GroundStationTelemetry.recorded_at.desc())
        .limit(1)
    )).scalars().first()


async def get_thresholds(db: AsyncSession, device_id: uuid.UUID) -> GroundStationAlertThreshold:
    row = (await db.execute(
        select(GroundStationAlertThreshold).where(GroundStationAlertThreshold.device_id == device_id)
    )).scalars().first()
    if row is None:
        row = GroundStationAlertThreshold(device_id=device_id, **DEFAULT_THRESHOLDS)
        db.add(row)
        await db.flush()
    return row


async def set_thresholds(db: AsyncSession, device_id: uuid.UUID, values: dict) -> GroundStationAlertThreshold:
    row = await get_thresholds(db, device_id)
    for key in DEFAULT_THRESHOLDS:
        if key in values and values[key] is not None:
            setattr(row, key, values[key])
    await db.flush()
    return row


async def _recent_alert_exists(db: AsyncSession, device_id: uuid.UUID, alert_type: str, severity: str) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=_DEBOUNCE_SECONDS)
    existing = (await db.execute(
        select(GroundStationAlert.id).where(
            GroundStationAlert.device_id == device_id,
            GroundStationAlert.alert_type == alert_type,
            GroundStationAlert.severity == severity,
            GroundStationAlert.occurred_at > cutoff,
        ).limit(1)
    )).scalars().first()
    return existing is not None


async def check_thresholds(db: AsyncSession, device_id: uuid.UUID, data: dict) -> list[GroundStationAlert]:
    """Evaluate one telemetry frame against this device's thresholds,
    creating (debounced) alert rows for any violation. Returns the newly
    created alerts, if any, for the caller to broadcast."""
    thresholds = await get_thresholds(db, device_id)
    checks = [
        ("temp", _field(data, "temp_C", "temp"), thresholds.temp_max, "max"),
        ("temp", _field(data, "temp_C", "temp"), thresholds.temp_min, "min"),
        ("voltage", _field(data, "bus_voltage_V", "voltage"), thresholds.voltage_max, "max"),
        ("voltage", _field(data, "bus_voltage_V", "voltage"), thresholds.voltage_min, "min"),
        ("current", _field(data, "current_mA", "current"), thresholds.current_max, "max"),
        ("power", _field(data, "power_mW", "power"), thresholds.power_max, "max"),
    ]
    created: list[GroundStationAlert] = []
    for alert_type, value, limit, mode in checks:
        if value is None or limit is None:
            continue
        violated = value >= limit if mode == "max" else value <= limit
        if not violated:
            continue
        if await _recent_alert_exists(db, device_id, alert_type, "critical"):
            continue
        alert = GroundStationAlert(
            id=uuid.uuid4(), device_id=device_id, alert_type=alert_type,
            threshold=limit, current_value=value, severity="critical",
        )
        db.add(alert)
        created.append(alert)
    if created:
        await db.flush()
    return created


async def list_alerts(db: AsyncSession, device_id: uuid.UUID, active_only: bool = False) -> list[GroundStationAlert]:
    stmt = select(GroundStationAlert).where(GroundStationAlert.device_id == device_id)
    if active_only:
        stmt = stmt.where(GroundStationAlert.acknowledged.is_(False))
    stmt = stmt.order_by(GroundStationAlert.occurred_at.desc()).limit(50)
    return list((await db.execute(stmt)).scalars().all())


async def acknowledge_alert(db: AsyncSession, alert_id: uuid.UUID) -> GroundStationAlert | None:
    alert = (await db.execute(
        select(GroundStationAlert).where(GroundStationAlert.id == alert_id)
    )).scalars().first()
    if alert is None:
        return None
    alert.acknowledged = True
    await db.flush()
    return alert


async def persist_image(
    db: AsyncSession, device_id: uuid.UUID, *, bucket: str, path: str,
    lat: float | None, lon: float | None, alt: float | None, captured_at: datetime,
) -> GroundStationImage:
    row = GroundStationImage(
        id=uuid.uuid4(), device_id=device_id, bucket=bucket, path=path,
        lat=lat, lon=lon, alt=alt, captured_at=captured_at,
    )
    db.add(row)
    await db.flush()
    return row


async def list_images(db: AsyncSession, device_id: uuid.UUID) -> list[GroundStationImage]:
    rows = (await db.execute(
        select(GroundStationImage)
        .where(GroundStationImage.device_id == device_id)
        .order_by(GroundStationImage.captured_at.desc())
    )).scalars().all()
    return list(rows)


async def device_stats(db: AsyncSession, device_id: uuid.UUID) -> dict:
    total = (await db.execute(
        select(GroundStationTelemetry.id).where(GroundStationTelemetry.device_id == device_id)
    )).scalars().all()
    first = (await db.execute(
        select(GroundStationTelemetry.recorded_at)
        .where(GroundStationTelemetry.device_id == device_id)
        .order_by(GroundStationTelemetry.recorded_at.asc()).limit(1)
    )).scalars().first()
    last = (await db.execute(
        select(GroundStationTelemetry.recorded_at)
        .where(GroundStationTelemetry.device_id == device_id)
        .order_by(GroundStationTelemetry.recorded_at.desc()).limit(1)
    )).scalars().first()
    return {"packets_received": len(total), "first_seen": first, "last_seen": last}

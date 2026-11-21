"""Telemetry persistence, threshold/alert checking, and the image registry —
ported from the legacy app's `process_telemetry`/`check_thresholds`/
`create_alert` (`backend/serial_reader.py` in the legacy zip). Field-name
dual support (`temp_C` vs `temp`, etc.) is intentional: real firmware in
the wild used both, and the legacy backend accepted either.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
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
        val = data
        for part in n.split("."):
            if isinstance(val, dict):
                val = val.get(part)
            else:
                val = None
                break
        if val is not None:
            try:
                f = float(val)
                if f == f:  # guard against NaN
                    return f
            except (TypeError, ValueError):
                pass
    return None


def normalize_telemetry_payload(data: dict) -> dict:
    """Normalize both flat Ground Station frames and nested AlFalaj_CDHS /
    AlFalaj_Sensors frames into a single flat+raw dictionary so downstream
    charts, thresholds, and WebSocket consumers always see standard keys."""
    temp = _field(data, "temp_C", "temp", "temp.c", "imu.temp_c", "ir.amb_c")
    voltage = _field(data, "bus_voltage_V", "voltage", "bus_v", "power.bus_v")
    current = _field(data, "current", "current_A")
    if current is None:
        ma = _field(data, "current_mA", "ma", "power.ma")
        if ma is not None:
            current = ma / 1000.0 if "power" in data or "ma" in data else ma
    power = _field(data, "power_mW", "power", "mw", "power.mw")
    if power is None and voltage is not None and current is not None:
        power = round(voltage * current * 1000.0 if current < 10 else voltage * current, 2)
    rssi = _field(data, "rssi", "wifi.rssi", "payload.rssi")
    snr = _field(data, "snr")
    uptime = _field(data, "uptime", "uptime_s")
    lat = _field(data, "lat", "gps.lat")
    lon = _field(data, "lon", "lng", "gps.lon")
    alt = _field(data, "alt", "gps.alt")
    pitch = _field(data, "pitch", "imu.pitch")
    roll = _field(data, "roll", "imu.roll")
    yaw = _field(data, "yaw", "heading", "mag.heading", "imu.gz")

    out = dict(data)
    if temp is not None:
        out["temp"] = temp
    if voltage is not None:
        out["voltage"] = voltage
    if current is not None:
        out["current"] = current
    if power is not None:
        out["power"] = power
    if rssi is not None:
        out["rssi"] = rssi
    if snr is not None:
        out["snr"] = snr
    if uptime is not None:
        out["uptime"] = int(uptime)
    if lat is not None:
        out["lat"] = lat
    if lon is not None:
        out["lon"] = lon
    if alt is not None:
        out["alt"] = alt
    if pitch is not None:
        out["pitch"] = pitch
    if roll is not None:
        out["roll"] = roll
    if yaw is not None:
        out["yaw"] = yaw
    return out


async def persist_telemetry(
    db: AsyncSession, device_id: uuid.UUID, data: dict, recorded_at: datetime | None = None,
) -> GroundStationTelemetry:
    norm = normalize_telemetry_payload(data)
    row = GroundStationTelemetry(
        id=uuid.uuid4(), device_id=device_id, recorded_at=recorded_at or datetime.now(timezone.utc),
        temp=_field(norm, "temp"),
        voltage=_field(norm, "voltage"),
        current=_field(norm, "current"),
        power=_field(norm, "power"),
        rssi=_field(norm, "rssi"),
        snr=_field(norm, "snr"),
        uptime=int(v) if (v := _field(norm, "uptime")) is not None else None,
        lat=_field(norm, "lat"), lon=_field(norm, "lon", "lng"), alt=_field(norm, "alt"),
        pitch=_field(norm, "pitch"), roll=_field(norm, "roll"), yaw=_field(norm, "yaw"),
        data=norm,
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


async def acknowledge_alert(db: AsyncSession, device_id: uuid.UUID, alert_id: uuid.UUID) -> GroundStationAlert | None:
    """Scoped by device as well as alert id — the route only proves the
    caller is authorized for `device_id`, so looking the alert up by id
    alone would let anyone acknowledge (and read back) an alert that
    belongs to a different device they don't own."""
    alert = (await db.execute(
        select(GroundStationAlert).where(
            GroundStationAlert.id == alert_id, GroundStationAlert.device_id == device_id,
        )
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
    total = await db.scalar(
        select(func.count()).select_from(GroundStationTelemetry)
        .where(GroundStationTelemetry.device_id == device_id)
    )
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
    return {"packets_received": total or 0, "first_seen": first, "last_seen": last}

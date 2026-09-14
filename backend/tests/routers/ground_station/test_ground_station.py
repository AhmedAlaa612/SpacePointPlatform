"""Ground Station — device auth, command allowlist, admin registration.
No `mission_attempts`/scoring involved (see models/ground_station/__init__.py) —
this is a plain auth+allowlist surface, so `client` (no Redis) covers most of
it; `realtime_client` covers the one broadcast-fan-out test.
"""

import uuid

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.ground_station.device import GroundStationDevice
from app.models.user import User
from app.services.ground_station.devices import register_device


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Ground Station User", email=f"gs-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) if roles else ["student"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


@pytest.mark.asyncio
async def test_ingest_rejects_wrong_device_secret(db, client):
    device, _secret = await register_device(db, label="Rig 1")
    await db.flush()

    resp = await client.post(
        f"/ground-station/devices/{device.id}/telemetry",
        json={"data": {"battery_v": 3.7}},
        headers={"X-Device-Secret": "not-the-real-secret"},
    )
    assert resp.status_code == http_status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_ingest_accepts_correct_device_secret(db, client):
    device, secret = await register_device(db, label="Rig 1")
    await db.flush()

    resp = await client.post(
        f"/ground-station/devices/{device.id}/telemetry",
        json={"data": {"battery_v": 3.7}},
        headers={"X-Device-Secret": secret},
    )
    assert resp.status_code == http_status.HTTP_202_ACCEPTED

    refreshed = await db.get(GroundStationDevice, device.id)
    assert refreshed.status == "online"
    assert refreshed.last_seen_at is not None


@pytest.mark.asyncio
async def test_command_rejects_unknown_command_name(db, client):
    device, _secret = await register_device(db, label="Rig 1")
    user = await _user(db)
    await db.flush()

    resp = await client.post(
        f"/ground-station/devices/{device.id}/commands",
        json={"name": "DROP_TABLE_USERS"},
        headers=_headers(user),
    )
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_command_requires_login(db, client):
    device, _secret = await register_device(db, label="Rig 1")
    await db.flush()

    resp = await client.post(
        f"/ground-station/devices/{device.id}/commands",
        json={"name": "PING"},
    )
    assert resp.status_code == http_status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_command_queues_and_broadcasts_for_allowed_command(db, realtime_client, realtime_redis):
    device, _secret = await register_device(db, label="Rig 1")
    user = await _user(db)
    await db.flush()

    pubsub = realtime_redis.pubsub()
    await pubsub.subscribe(f"ground-station:device:{device.id}")

    resp = await realtime_client.post(
        f"/ground-station/devices/{device.id}/commands",
        json={"name": "ping"},  # lower-case on the way in — normalized to PING
        headers=_headers(user),
    )
    assert resp.status_code == http_status.HTTP_200_OK
    assert resp.json()["name"] == "PING"

    # Skip the subscribe confirmation message, assert the actual broadcast.
    await pubsub.get_message(timeout=1)
    message = await pubsub.get_message(timeout=1)
    assert message is not None
    assert "command_queued" in message["data"]

    await pubsub.unsubscribe()
    await pubsub.aclose()


@pytest.mark.asyncio
async def test_admin_register_device_requires_operations_role(db, client):
    student = await _user(db, roles=["student"])
    await db.flush()

    resp = await client.post(
        "/ground-station/admin/devices", json={"label": "New Rig"}, headers=_headers(student),
    )
    assert resp.status_code == http_status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_admin_register_device_returns_secret_once(db, client):
    ops = await _user(db, roles=["operations"])
    await db.flush()

    resp = await client.post(
        "/ground-station/admin/devices", json={"label": "New Rig"}, headers=_headers(ops),
    )
    assert resp.status_code == http_status.HTTP_200_OK
    body = resp.json()
    assert body["device"]["label"] == "New Rig"
    assert body["device"]["status"] == "offline"
    assert len(body["secret"]) > 20

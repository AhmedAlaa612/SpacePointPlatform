"""Ground Station — mission-attempt ownership (2026-09-14 rework), no auth
on ingest, command allowlist. `client` (no Redis) covers most of it;
`realtime_client` covers the one broadcast-fan-out test.
"""

import uuid

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.ground_station.device import GroundStationDevice
from app.models.missions.mission import Mission, MissionVariant
from app.models.user import User


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


async def _ground_station_mission(db, *, author) -> tuple[Mission, MissionVariant]:
    mission = Mission(
        id=uuid.uuid4(), title="Router Ground Station", slug=f"router-ground-station-{uuid.uuid4().hex[:8]}",
        kind="ground_station", authored_by=author.id, status="published", team_policy="either",
        summary="Wire it up.",
    )
    db.add(mission)
    await db.flush()
    variant = MissionVariant(id=uuid.uuid4(), mission_id=mission.id, label="Standard", position=1, points=0, config={})
    db.add(variant)
    await db.flush()
    return mission, variant


async def _start_attempt_and_get_device(client, mission, variant, student) -> tuple[str, str]:
    """Returns (attempt_id, device_id)."""
    res = await client.post(
        f"/missions/{mission.id}/attempts", headers=_headers(student), json={"variant_id": str(variant.id)},
    )
    assert res.status_code == 201, res.text
    attempt_id = res.json()["id"]

    res = await client.get(f"/ground-station/attempts/{attempt_id}/device", headers=_headers(student))
    assert res.status_code == 200, res.text
    return attempt_id, res.json()["device"]["id"]


async def _other_kind_mission(db, *, author) -> tuple[Mission, MissionVariant]:
    """A same-shape, different-`kind` mission — for proving the
    `/ground-station/attempts/*` routes are scoped to `ground_station`
    attempts specifically, not any attempt the caller happens to own."""
    mission = Mission(
        id=uuid.uuid4(), title="Build a Radio", slug=f"not-ground-station-{uuid.uuid4().hex[:8]}",
        kind="submission", authored_by=author.id, status="published", team_policy="either",
        summary="Unrelated mission kind.",
    )
    db.add(mission)
    await db.flush()
    variant = MissionVariant(id=uuid.uuid4(), mission_id=mission.id, label="Standard", position=1, points=50, config={})
    db.add(variant)
    await db.flush()
    return mission, variant


@pytest.mark.asyncio
async def test_ingest_requires_no_auth_at_all(db, client):
    """Operator directive: the surface is private via attempt ownership,
    so ingest itself takes nothing but a valid device id — no header."""
    author = await _user(db, roles=["operations"])
    mission, variant = await _ground_station_mission(db, author=author)
    student = await _user(db)
    await db.commit()

    _attempt_id, device_id = await _start_attempt_and_get_device(client, mission, variant, student)

    resp = await client.post(f"/ground-station/devices/{device_id}/telemetry", json={"data": {"temp": 25.0}})
    assert resp.status_code == http_status.HTTP_202_ACCEPTED

    refreshed = await db.get(GroundStationDevice, uuid.UUID(device_id))
    assert refreshed.status == "online"
    assert refreshed.last_seen_at is not None


@pytest.mark.asyncio
async def test_ingest_rejects_unknown_device(client):
    resp = await client.post(f"/ground-station/devices/{uuid.uuid4()}/telemetry", json={"data": {"temp": 25.0}})
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_device_is_private_to_its_attempt_owner(db, client):
    """The whole point of the rework: a device belongs to one attempt, and
    nobody outside it (student-side) can see or touch it."""
    author = await _user(db, roles=["operations"])
    mission, variant = await _ground_station_mission(db, author=author)
    owner = await _user(db)
    stranger = await _user(db)
    await db.commit()

    _attempt_id, device_id = await _start_attempt_and_get_device(client, mission, variant, owner)

    resp = await client.get(f"/ground-station/devices/{device_id}", headers=_headers(stranger))
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND

    resp = await client.get("/ground-station/devices", headers=_headers(stranger))
    assert resp.status_code == 200
    assert resp.json() == []

    resp = await client.get(f"/ground-station/devices/{device_id}", headers=_headers(owner))
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_staff_can_see_every_device(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _ground_station_mission(db, author=author)
    owner = await _user(db)
    ops = await _user(db, roles=["operations"])
    await db.commit()

    _attempt_id, device_id = await _start_attempt_and_get_device(client, mission, variant, owner)

    resp = await client.get(f"/ground-station/devices/{device_id}", headers=_headers(ops))
    assert resp.status_code == 200

    resp = await client.get("/ground-station/admin/attempts", headers=_headers(ops))
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_command_rejects_unknown_command_name(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _ground_station_mission(db, author=author)
    student = await _user(db)
    await db.commit()

    _attempt_id, device_id = await _start_attempt_and_get_device(client, mission, variant, student)

    resp = await client.post(
        f"/ground-station/devices/{device_id}/commands",
        json={"name": "DROP_TABLE_USERS"},
        headers=_headers(student),
    )
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_command_requires_login(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _ground_station_mission(db, author=author)
    student = await _user(db)
    await db.commit()

    _attempt_id, device_id = await _start_attempt_and_get_device(client, mission, variant, student)

    resp = await client.post(f"/ground-station/devices/{device_id}/commands", json={"name": "PING"})
    assert resp.status_code == http_status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_command_requires_ownership(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _ground_station_mission(db, author=author)
    owner = await _user(db)
    stranger = await _user(db)
    await db.commit()

    _attempt_id, device_id = await _start_attempt_and_get_device(client, mission, variant, owner)

    resp = await client.post(
        f"/ground-station/devices/{device_id}/commands", json={"name": "PING"}, headers=_headers(stranger),
    )
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_command_queues_and_broadcasts_for_allowed_command(db, realtime_client, realtime_redis):
    author = await _user(db, roles=["operations"])
    mission, variant = await _ground_station_mission(db, author=author)
    student = await _user(db)
    await db.commit()

    _attempt_id, device_id = await _start_attempt_and_get_device(realtime_client, mission, variant, student)

    pubsub = realtime_redis.pubsub()
    await pubsub.subscribe(f"ground-station:device:{device_id}")

    resp = await realtime_client.post(
        f"/ground-station/devices/{device_id}/commands",
        json={"name": "ping"},  # lower-case on the way in — normalized to PING
        headers=_headers(student),
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
async def test_complete_attempt_sets_passed_with_no_score(db, client):
    """Checklist tracking (`mission_run` auto-done) reads `status ==
    'passed'` — this is the self-serve way to reach it without any
    grading path running (score stays null, no points minted)."""
    author = await _user(db, roles=["operations"])
    mission, variant = await _ground_station_mission(db, author=author)
    student = await _user(db)
    await db.commit()

    attempt_id, _device_id = await _start_attempt_and_get_device(client, mission, variant, student)

    resp = await client.post(f"/ground-station/attempts/{attempt_id}/complete", headers=_headers(student))
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "passed"

    resp = await client.get(f"/missions/attempts/{attempt_id}", headers=_headers(student))
    assert resp.json()["status"] == "passed"
    assert resp.json()["score"] is None

    # Idempotent — calling again doesn't error or change anything.
    resp = await client.post(f"/ground-station/attempts/{attempt_id}/complete", headers=_headers(student))
    assert resp.status_code == 200
    assert resp.json()["status"] == "passed"


@pytest.mark.asyncio
async def test_complete_attempt_requires_ownership(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _ground_station_mission(db, author=author)
    owner = await _user(db)
    stranger = await _user(db)
    await db.commit()

    attempt_id, _device_id = await _start_attempt_and_get_device(client, mission, variant, owner)

    resp = await client.post(f"/ground-station/attempts/{attempt_id}/complete", headers=_headers(stranger))
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_complete_attempt_rejects_a_non_ground_station_attempt(db, client):
    """The security-review finding: `complete_attempt` must not let a
    student self-pass an attempt against some other mission kind just
    because they own it — ownership alone isn't enough, it has to be a
    ground_station attempt too."""
    author = await _user(db, roles=["operations"])
    mission, variant = await _other_kind_mission(db, author=author)
    student = await _user(db)
    await db.commit()

    res = await client.post(
        f"/missions/{mission.id}/attempts", headers=_headers(student), json={"variant_id": str(variant.id)},
    )
    assert res.status_code == 201, res.text
    attempt_id = res.json()["id"]
    assert res.json()["status"] != "passed"

    resp = await client.post(f"/ground-station/attempts/{attempt_id}/complete", headers=_headers(student))
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND

    resp = await client.get(f"/missions/attempts/{attempt_id}", headers=_headers(student))
    assert resp.json()["status"] != "passed"


@pytest.mark.asyncio
async def test_get_attempt_device_rejects_a_non_ground_station_attempt(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _other_kind_mission(db, author=author)
    student = await _user(db)
    await db.commit()

    res = await client.post(
        f"/missions/{mission.id}/attempts", headers=_headers(student), json={"variant_id": str(variant.id)},
    )
    assert res.status_code == 201, res.text
    attempt_id = res.json()["id"]

    resp = await client.get(f"/ground-station/attempts/{attempt_id}/device", headers=_headers(student))
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_acknowledge_alert_is_scoped_to_its_own_device(db, client):
    """The other security-review finding: `acknowledge_alert` looked an
    alert up by id alone, so someone authorized for device A's URL could
    acknowledge (and read back) an alert that actually belongs to device
    B, as long as they had or guessed its id. Must 404 instead."""
    author = await _user(db, roles=["operations"])
    mission, variant = await _ground_station_mission(db, author=author)
    owner_a = await _user(db)
    owner_b = await _user(db)
    await db.commit()

    _attempt_a, device_a = await _start_attempt_and_get_device(client, mission, variant, owner_a)
    _attempt_b, device_b = await _start_attempt_and_get_device(client, mission, variant, owner_b)

    resp = await client.post(f"/ground-station/devices/{device_b}/telemetry", json={"data": {"temp": 999}})
    assert resp.status_code == http_status.HTTP_202_ACCEPTED

    resp = await client.get(f"/ground-station/devices/{device_b}/alerts", headers=_headers(owner_b))
    assert resp.status_code == 200
    alerts = resp.json()
    assert len(alerts) == 1
    alert_id = alerts[0]["id"]
    assert alerts[0]["acknowledged"] is False

    # device_a's own owner, hitting device_a's ack URL with device_b's alert id.
    resp = await client.post(
        f"/ground-station/devices/{device_a}/alerts/{alert_id}/acknowledge", headers=_headers(owner_a),
    )
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND

    # Untouched — still unacknowledged on its real device.
    resp = await client.get(f"/ground-station/devices/{device_b}/alerts", headers=_headers(owner_b))
    assert resp.json()[0]["acknowledged"] is False


@pytest.mark.asyncio
async def test_admin_register_device_requires_operations_role(db, client):
    student = await _user(db, roles=["student"])
    await db.flush()

    resp = await client.post(
        "/ground-station/admin/devices", json={"label": "New Rig"}, headers=_headers(student),
    )
    assert resp.status_code == http_status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_admin_register_device_needs_no_secret(db, client):
    ops = await _user(db, roles=["operations"])
    await db.flush()

    resp = await client.post(
        "/ground-station/admin/devices", json={"label": "New Rig"}, headers=_headers(ops),
    )
    assert resp.status_code == http_status.HTTP_200_OK
    body = resp.json()
    assert body["label"] == "New Rig"
    assert body["status"] == "offline"
    assert body["mission_attempt_id"] is None

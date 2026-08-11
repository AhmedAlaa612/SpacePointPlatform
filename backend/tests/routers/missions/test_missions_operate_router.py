"""Stage 7B-3 router tests — the operate mission HTTP surface end to end.
Redis-free (uses the `client` fixture).
"""

import uuid

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.missions.mission import Mission, MissionVariant
from app.models.user import User


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Operate Router User", email=f"opr-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) if roles else ["student"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _operate_mission(db, *, author, pass_threshold=70) -> tuple[Mission, MissionVariant]:
    mission = Mission(
        id=uuid.uuid4(), title="Router Operate Mission", slug=f"router-operate-{uuid.uuid4().hex[:8]}",
        kind="operate", authored_by=author.id, status="published", team_policy="solo",
    )
    db.add(mission)
    await db.flush()
    variant = MissionVariant(
        id=uuid.uuid4(), mission_id=mission.id, label="Cadet", position=1, points=120,
        config={
            "pass_threshold": pass_threshold,
            "anomalies": [
                {"trigger_after_commands": 1, "subsystem": "EPS", "correct_command": "EPS_RECONFIG"},
            ],
        },
    )
    db.add(variant)
    await db.flush()
    return mission, variant


@pytest.mark.asyncio
async def test_get_state_before_any_command_shows_zero_events_and_full_score(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _operate_mission(db, author=author)
    student = await _user(db)
    await db.commit()

    start = await client.post(
        f"/missions/{mission.id}/attempts", headers=_headers(student), json={"variant_id": str(variant.id)},
    )
    assert start.status_code == 201, start.text
    attempt_id = start.json()["id"]

    state = await client.get(f"/missions/operate/attempts/{attempt_id}", headers=_headers(student))
    assert state.status_code == 200, state.text
    body = state.json()
    assert body["events"] == []
    assert body["score"] == 100.0  # nothing triggered yet


@pytest.mark.asyncio
async def test_issue_command_appends_an_event(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _operate_mission(db, author=author)
    student = await _user(db)
    await db.commit()

    start = await client.post(
        f"/missions/{mission.id}/attempts", headers=_headers(student), json={"variant_id": str(variant.id)},
    )
    attempt_id = start.json()["id"]

    resp = await client.post(
        f"/missions/operate/attempts/{attempt_id}/command", headers=_headers(student), json={"command": "HELP"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["event"]["command"] == "HELP"
    assert resp.json()["event"]["success"] is True
    assert len(resp.json()["state"]["events"]) == 1


@pytest.mark.asyncio
async def test_full_flow_resolve_anomaly_and_pass(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _operate_mission(db, author=author, pass_threshold=70)
    student = await _user(db)
    await db.commit()
    h = _headers(student)

    start = await client.post(f"/missions/{mission.id}/attempts", headers=h, json={"variant_id": str(variant.id)})
    attempt_id = start.json()["id"]

    # Anomaly triggers after 1 command.
    await client.post(f"/missions/operate/attempts/{attempt_id}/command", headers=h, json={"command": "HELP"})
    fix = await client.post(
        f"/missions/operate/attempts/{attempt_id}/command", headers=h, json={"command": "EPS_RECONFIG"},
    )
    assert fix.json()["state"]["resolved_count"] == 1

    finish = await client.post(f"/missions/operate/attempts/{attempt_id}/finish", headers=h)
    assert finish.status_code == 200, finish.text
    assert finish.json()["passed"] is True
    assert finish.json()["state"]["attempt_status"] == "passed"


@pytest.mark.asyncio
async def test_full_flow_ignore_anomaly_and_fail(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _operate_mission(db, author=author, pass_threshold=70)
    student = await _user(db)
    await db.commit()
    h = _headers(student)

    start = await client.post(f"/missions/{mission.id}/attempts", headers=h, json={"variant_id": str(variant.id)})
    attempt_id = start.json()["id"]

    await client.post(f"/missions/operate/attempts/{attempt_id}/command", headers=h, json={"command": "HELP"})
    await client.post(f"/missions/operate/attempts/{attempt_id}/command", headers=h, json={"command": "DOWNLOAD_TM"})

    finish = await client.post(f"/missions/operate/attempts/{attempt_id}/finish", headers=h)
    assert finish.status_code == 200
    assert finish.json()["passed"] is False
    assert finish.json()["state"]["attempt_status"] == "failed"


@pytest.mark.asyncio
async def test_cannot_issue_a_command_after_finishing(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _operate_mission(db, author=author)
    student = await _user(db)
    await db.commit()
    h = _headers(student)

    start = await client.post(f"/missions/{mission.id}/attempts", headers=h, json={"variant_id": str(variant.id)})
    attempt_id = start.json()["id"]
    await client.post(f"/missions/operate/attempts/{attempt_id}/finish", headers=h)

    resp = await client.post(
        f"/missions/operate/attempts/{attempt_id}/command", headers=h, json={"command": "HELP"},
    )
    assert resp.status_code == http_status.HTTP_409_CONFLICT


@pytest.mark.asyncio
async def test_retry_after_failing_is_a_new_attempt_and_can_still_pass(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _operate_mission(db, author=author, pass_threshold=70)
    student = await _user(db)
    await db.commit()
    h = _headers(student)

    first = await client.post(f"/missions/{mission.id}/attempts", headers=h, json={"variant_id": str(variant.id)})
    first_id = first.json()["id"]
    # Trigger the anomaly (1 command) but never fix it -- fails.
    await client.post(f"/missions/operate/attempts/{first_id}/command", headers=h, json={"command": "HELP"})
    first_finish = await client.post(f"/missions/operate/attempts/{first_id}/finish", headers=h)
    assert first_finish.json()["passed"] is False

    second = await client.post(f"/missions/{mission.id}/attempts", headers=h, json={"variant_id": str(variant.id)})
    second_id = second.json()["id"]
    assert second_id != first_id

    await client.post(f"/missions/operate/attempts/{second_id}/command", headers=h, json={"command": "HELP"})
    await client.post(f"/missions/operate/attempts/{second_id}/command", headers=h, json={"command": "EPS_RECONFIG"})
    finish = await client.post(f"/missions/operate/attempts/{second_id}/finish", headers=h)
    assert finish.json()["passed"] is True


@pytest.mark.asyncio
async def test_cannot_act_on_another_students_operate_attempt(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _operate_mission(db, author=author)
    await db.commit()
    alice = await _user(db)
    bob = await _user(db)
    await db.commit()

    start = await client.post(
        f"/missions/{mission.id}/attempts", headers=_headers(alice), json={"variant_id": str(variant.id)},
    )
    attempt_id = start.json()["id"]

    resp = await client.get(f"/missions/operate/attempts/{attempt_id}", headers=_headers(bob))
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND

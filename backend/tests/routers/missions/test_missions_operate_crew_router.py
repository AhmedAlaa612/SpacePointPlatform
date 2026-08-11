"""Stage 7B-5 router tests — crew role assignment and gating for team
operate attempts, over real HTTP. Redis-free.
"""

import uuid

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.missions.mission import Mission, MissionVariant
from app.models.user import User


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Crew Router User", email=f"crew-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) if roles else ["student"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _operate_mission(db, *, author) -> tuple[Mission, MissionVariant]:
    mission = Mission(
        id=uuid.uuid4(), title="Crew Router Mission", slug=f"crew-router-{uuid.uuid4().hex[:8]}",
        kind="operate", authored_by=author.id, status="published", team_policy="team",
    )
    db.add(mission)
    await db.flush()
    variant = MissionVariant(
        id=uuid.uuid4(), mission_id=mission.id, label="Engineer", position=2, points=200,
        config={
            "pass_threshold": 50,
            "anomalies": [{"trigger_after_commands": 1, "subsystem": "EPS", "correct_command": "EPS_RECONFIG"}],
        },
    )
    db.add(variant)
    await db.flush()
    return mission, variant


@pytest.mark.asyncio
async def test_solo_attempts_cannot_assign_crew_roles(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _operate_mission(db, author=author)
    mission.team_policy = "either"
    await db.commit()
    student = await _user(db)
    await db.commit()
    h = _headers(student)

    start = await client.post(f"/missions/{mission.id}/attempts", headers=h, json={"variant_id": str(variant.id)})
    attempt_id = start.json()["id"]

    resp = await client.post(f"/missions/operate/attempts/{attempt_id}/crew", headers=h, json={"role": "eps"})
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_team_member_can_take_and_vacate_a_role(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _operate_mission(db, author=author)
    await db.commit()
    alice = await _user(db)
    await db.commit()
    h = _headers(alice)

    team = await client.post("/missions/teams", headers=h, json={"name": "Crew Team A"})
    team_id = team.json()["id"]
    start = await client.post(
        f"/missions/{mission.id}/attempts", headers=h, json={"variant_id": str(variant.id), "team_id": team_id},
    )
    attempt_id = start.json()["id"]

    take = await client.post(f"/missions/operate/attempts/{attempt_id}/crew", headers=h, json={"role": "eps"})
    assert take.status_code == 200, take.text
    assert take.json()["crew"]["eps"] == str(alice.id)

    vacate = await client.post(f"/missions/operate/attempts/{attempt_id}/crew", headers=h, json={"role": None})
    assert vacate.json()["crew"] == {}


@pytest.mark.asyncio
async def test_unfilled_role_lets_anyone_issue_the_fix_and_filled_role_gates_it(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _operate_mission(db, author=author)
    await db.commit()
    alice = await _user(db)
    bob = await _user(db)
    await db.commit()
    h_alice, h_bob = _headers(alice), _headers(bob)

    team = await client.post("/missions/teams", headers=h_alice, json={"name": "Crew Team B", "member_ids": [str(bob.id)]})
    team_id = team.json()["id"]
    start = await client.post(
        f"/missions/{mission.id}/attempts", headers=h_alice,
        json={"variant_id": str(variant.id), "team_id": team_id},
    )
    attempt_id = start.json()["id"]

    # Trigger the anomaly first (unfilled role -- anyone may act).
    trigger = await client.post(
        f"/missions/operate/attempts/{attempt_id}/command", headers=h_bob, json={"command": "HELP"},
    )
    assert trigger.json()["state"]["triggered_count"] == 1

    # Still unfilled -- Bob can fix it.
    fix_open = await client.post(
        f"/missions/operate/attempts/{attempt_id}/command", headers=h_bob, json={"command": "EPS_RECONFIG"},
    )
    assert fix_open.status_code == 200
    assert fix_open.json()["state"]["resolved_count"] == 1


@pytest.mark.asyncio
async def test_filled_role_blocks_a_non_assigned_teammate(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _operate_mission(db, author=author)
    await db.commit()
    alice = await _user(db)
    bob = await _user(db)
    await db.commit()
    h_alice, h_bob = _headers(alice), _headers(bob)

    team = await client.post("/missions/teams", headers=h_alice, json={"name": "Crew Team C", "member_ids": [str(bob.id)]})
    team_id = team.json()["id"]
    start = await client.post(
        f"/missions/{mission.id}/attempts", headers=h_alice,
        json={"variant_id": str(variant.id), "team_id": team_id},
    )
    attempt_id = start.json()["id"]

    await client.post(f"/missions/operate/attempts/{attempt_id}/crew", headers=h_alice, json={"role": "eps"})
    await client.post(f"/missions/operate/attempts/{attempt_id}/command", headers=h_bob, json={"command": "HELP"})

    blocked = await client.post(
        f"/missions/operate/attempts/{attempt_id}/command", headers=h_bob, json={"command": "EPS_RECONFIG"},
    )
    assert blocked.status_code == http_status.HTTP_403_FORBIDDEN

    fixed = await client.post(
        f"/missions/operate/attempts/{attempt_id}/command", headers=h_alice, json={"command": "EPS_RECONFIG"},
    )
    assert fixed.status_code == 200
    assert fixed.json()["state"]["resolved_count"] == 1


@pytest.mark.asyncio
async def test_state_roster_lists_every_team_member_with_their_role(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _operate_mission(db, author=author)
    await db.commit()
    alice = await _user(db)
    bob = await _user(db)
    await db.commit()
    h_alice = _headers(alice)

    team = await client.post("/missions/teams", headers=h_alice, json={"name": "Crew Team D", "member_ids": [str(bob.id)]})
    team_id = team.json()["id"]
    start = await client.post(
        f"/missions/{mission.id}/attempts", headers=h_alice,
        json={"variant_id": str(variant.id), "team_id": team_id},
    )
    attempt_id = start.json()["id"]
    await client.post(f"/missions/operate/attempts/{attempt_id}/crew", headers=h_alice, json={"role": "commander"})

    state = await client.get(f"/missions/operate/attempts/{attempt_id}", headers=h_alice)
    roster = {m["user_id"]: m["role"] for m in state.json()["roster"]}
    assert roster[str(alice.id)] == "commander"
    assert roster[str(bob.id)] is None
    assert state.json()["is_team"] is True

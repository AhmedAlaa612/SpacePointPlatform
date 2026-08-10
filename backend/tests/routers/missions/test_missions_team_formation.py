"""P6-4 router tests — team formation (ops-assign + self-form) and the team
mission attempt flow over HTTP. Redis-free (uses the `client` fixture).
"""

import uuid

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.missions.mission import Mission, MissionVariant
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.user import User


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Team Formation User", email=f"tf-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) if roles else ["student"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _mission(db, *, author, team_policy="either") -> tuple[Mission, MissionVariant]:
    mission = Mission(
        id=uuid.uuid4(), title="Team Formation Mission", slug=f"team-formation-{uuid.uuid4().hex[:8]}",
        kind="submission", authored_by=author.id, status="published", team_policy=team_policy,
    )
    db.add(mission)
    await db.flush()
    variant = MissionVariant(id=uuid.uuid4(), mission_id=mission.id, label="Standard", position=1, points=20)
    db.add(variant)
    await db.flush()
    return mission, variant


async def _cohort(db) -> Cohort:
    program = Program(
        id=uuid.uuid4(), code=f"TFP-{uuid.uuid4().hex[:8]}", name="Team Formation Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Team Formation Cohort", status="running")
    db.add(cohort)
    await db.flush()
    return cohort


@pytest.mark.asyncio
async def test_teams_routes_are_not_swallowed_by_mission_id_route(db, client):
    student = await _user(db)
    resp = await client.get("/missions/teams/mine", headers=_headers(student))
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_self_form_creates_a_cohort_less_team_and_adds_creator(db, client):
    alice = await _user(db)
    bob = await _user(db)
    await db.commit()

    resp = await client.post(
        "/missions/teams", headers=_headers(alice),
        json={"name": "Self Formed Squad", "member_ids": [str(bob.id)]},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["cohort_id"] is None
    assert set(body["member_ids"]) == {str(alice.id), str(bob.id)}

    mine = await client.get("/missions/teams/mine", headers=_headers(alice))
    assert any(t["id"] == body["id"] for t in mine.json())


@pytest.mark.asyncio
async def test_ops_assign_requires_content_role_and_a_cohort(db, client):
    ops = await _user(db, roles=["operations"])
    student = await _user(db)
    cohort = await _cohort(db)
    await db.commit()

    forbidden = await client.post(
        "/missions/admin/teams", headers=_headers(student),
        json={"name": "Ops Team", "cohort_id": str(cohort.id), "member_ids": []},
    )
    assert forbidden.status_code == http_status.HTTP_403_FORBIDDEN

    ok = await client.post(
        "/missions/admin/teams", headers=_headers(ops),
        json={"name": "Ops Team", "cohort_id": str(cohort.id), "member_ids": [str(student.id)]},
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["cohort_id"] == str(cohort.id)


@pytest.mark.asyncio
async def test_solo_mission_rejects_a_team_attempt(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _mission(db, author=author, team_policy="solo")
    await db.commit()
    student = await _user(db)
    await db.commit()

    team_resp = await client.post("/missions/teams", headers=_headers(student), json={"name": "Solo Reject Team"})
    team_id = team_resp.json()["id"]

    resp = await client.post(
        f"/missions/{mission.id}/attempts", headers=_headers(student),
        json={"variant_id": str(variant.id), "team_id": team_id},
    )
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_team_only_mission_rejects_a_solo_attempt(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _mission(db, author=author, team_policy="team")
    await db.commit()
    student = await _user(db)
    await db.commit()

    resp = await client.post(
        f"/missions/{mission.id}/attempts", headers=_headers(student), json={"variant_id": str(variant.id)},
    )
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_non_member_cannot_start_an_attempt_for_a_team(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _mission(db, author=author, team_policy="team")
    await db.commit()
    alice = await _user(db)
    outsider = await _user(db)
    await db.commit()

    team_resp = await client.post("/missions/teams", headers=_headers(alice), json={"name": "Members Only Team"})
    team_id = team_resp.json()["id"]

    resp = await client.post(
        f"/missions/{mission.id}/attempts", headers=_headers(outsider),
        json={"variant_id": str(variant.id), "team_id": team_id},
    )
    assert resp.status_code == http_status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_full_team_attempt_flow_any_teammate_can_view_and_submit(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _mission(db, author=author, team_policy="team")
    await db.commit()
    alice = await _user(db)
    bob = await _user(db)
    await db.commit()

    team_resp = await client.post(
        "/missions/teams", headers=_headers(alice), json={"name": "Full Flow Team", "member_ids": [str(bob.id)]},
    )
    team_id = team_resp.json()["id"]

    start = await client.post(
        f"/missions/{mission.id}/attempts", headers=_headers(alice),
        json={"variant_id": str(variant.id), "team_id": team_id},
    )
    assert start.status_code == 201, start.text
    attempt_id = start.json()["id"]
    assert start.json()["team_id"] == team_id
    assert start.json()["team_name"] == "Full Flow Team"

    # Bob (a teammate who did not start it) can see and submit the same attempt.
    fetched = await client.get(f"/missions/attempts/{attempt_id}", headers=_headers(bob))
    assert fetched.status_code == 200

    submit = await client.post(
        f"/missions/attempts/{attempt_id}/submit", headers=_headers(bob),
        json={"artifact_url": "https://example.com/team-work"},
    )
    assert submit.status_code == 200, submit.text
    assert submit.json()["attempt"]["status"] == "submitted"


@pytest.mark.asyncio
async def test_mission_detail_lists_my_teams_for_a_team_policy_mission(db, client):
    author = await _user(db, roles=["operations"])
    mission, _ = await _mission(db, author=author, team_policy="either")
    await db.commit()
    alice = await _user(db)
    await db.commit()

    await client.post("/missions/teams", headers=_headers(alice), json={"name": "Detail Listed Team"})

    detail = await client.get(f"/missions/{mission.id}", headers=_headers(alice))
    assert detail.status_code == 200
    assert detail.json()["team_policy"] == "either"
    assert any(t["name"] == "Detail Listed Team" for t in detail.json()["my_teams"])

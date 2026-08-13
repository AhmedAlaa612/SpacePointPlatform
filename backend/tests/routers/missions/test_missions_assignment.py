"""2026-08-12 — mission delete and mission assignment (`/missions/admin/{id}`,
`/missions/admin/{id}/assignments*`, `/missions/admin/{id}/roster`). Redis-free.
"""

import uuid

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.missions.mission import Mission, MissionAttempt, MissionVariant
from app.models.user import User


async def _user(db, *, full_name="Missions Admin User", roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name=full_name, email=f"ma-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) if roles else ["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _mission(db, *, author, kind="submission", status="draft", access_mode="open") -> Mission:
    mission = Mission(
        id=uuid.uuid4(), title="Test Mission", slug=f"test-{uuid.uuid4().hex[:8]}",
        kind=kind, status=status, access_mode=access_mode, authored_by=author.id,
    )
    db.add(mission)
    await db.flush()
    return mission


@pytest.mark.asyncio
async def test_delete_mission_with_no_attempts_succeeds(db, client):
    ops = await _user(db)
    mission = await _mission(db, author=ops)
    await db.commit()

    resp = await client.delete(f"/missions/admin/{mission.id}", headers=_headers(ops))
    assert resp.status_code == http_status.HTTP_204_NO_CONTENT

    gone = await client.get(f"/missions/admin/{mission.id}", headers=_headers(ops))
    assert gone.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_delete_mission_with_attempts_is_refused(db, client):
    ops = await _user(db)
    mission = await _mission(db, author=ops)
    variant = MissionVariant(id=uuid.uuid4(), mission_id=mission.id, label="Standard", position=1, points=25)
    db.add(variant)
    await db.flush()
    student = await _user(db, full_name="Attempting Student", roles=["student"])
    db.add(MissionAttempt(
        id=uuid.uuid4(), mission_id=mission.id, variant_id=variant.id, user_id=student.id,
        attempt_no=1, status="in_progress", payload={},
    ))
    await db.commit()

    resp = await client.delete(f"/missions/admin/{mission.id}", headers=_headers(ops))
    assert resp.status_code == http_status.HTTP_409_CONFLICT

    still_there = await client.get(f"/missions/admin/{mission.id}", headers=_headers(ops))
    assert still_there.status_code == 200


@pytest.mark.asyncio
async def test_grant_and_revoke_mission_assignment(db, client):
    ops = await _user(db)
    mission = await _mission(db, author=ops)
    facilitator = await _user(db, full_name="Target Facilitator", roles=["facilitator"])
    await db.commit()

    grant = await client.post(
        f"/missions/admin/{mission.id}/assignments", headers=_headers(ops), json={"user_id": str(facilitator.id)},
    )
    assert grant.status_code == 201, grant.text
    body = grant.json()
    assert body["user_id"] == str(facilitator.id)
    assert body["status"] == "active"
    assert body["source"] == "ops"

    roster = await client.get(f"/missions/admin/{mission.id}/roster", headers=_headers(ops))
    assert roster.status_code == 200
    assert len(roster.json()) == 1
    assert roster.json()[0]["user_name"] == "Target Facilitator"

    revoke = await client.post(f"/missions/admin/assignments/{body['id']}/revoke", headers=_headers(ops))
    assert revoke.status_code == 200
    assert revoke.json()["status"] == "inactive"


@pytest.mark.asyncio
async def test_grant_is_idempotent_and_reactivates(db, client):
    ops = await _user(db)
    mission = await _mission(db, author=ops)
    facilitator = await _user(db, full_name="Repeat Facilitator", roles=["facilitator"])
    await db.commit()

    first = await client.post(
        f"/missions/admin/{mission.id}/assignments", headers=_headers(ops), json={"user_id": str(facilitator.id)},
    )
    await client.post(f"/missions/admin/assignments/{first.json()['id']}/revoke", headers=_headers(ops))

    second = await client.post(
        f"/missions/admin/{mission.id}/assignments", headers=_headers(ops), json={"user_id": str(facilitator.id)},
    )
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["status"] == "active"


@pytest.mark.asyncio
async def test_bulk_grant_assigns_every_user_with_role(db, client):
    ops = await _user(db)
    mission = await _mission(db, author=ops)
    fac_1 = await _user(db, full_name="Bulk Facilitator One", roles=["facilitator"])
    fac_2 = await _user(db, full_name="Bulk Facilitator Two", roles=["facilitator"])
    intern = await _user(db, full_name="Bulk Intern", roles=["intern"])
    await db.commit()

    resp = await client.post(
        f"/missions/admin/{mission.id}/assignments/bulk", headers=_headers(ops), json={"role": "facilitator"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["granted"] == 2
    assert resp.json()["already_assigned"] == 0

    roster = await client.get(f"/missions/admin/{mission.id}/roster", headers=_headers(ops))
    names = {row["user_name"] for row in roster.json()}
    assert names == {"Bulk Facilitator One", "Bulk Facilitator Two"}
    assert "Bulk Intern" not in names

    # Second call is idempotent — nobody gets a duplicate row.
    again = await client.post(
        f"/missions/admin/{mission.id}/assignments/bulk", headers=_headers(ops), json={"role": "facilitator"},
    )
    assert again.json()["granted"] == 0
    assert again.json()["already_assigned"] == 2

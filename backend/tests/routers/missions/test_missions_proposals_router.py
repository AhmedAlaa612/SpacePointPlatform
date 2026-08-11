"""7B-6 (Missions Phase 2B, 2026-08-12) — intern mission proposal pipeline:
`/missions/proposals/*`. Redis-free (uses the `client` fixture).
"""

import uuid

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.missions.mission import Mission
from app.models.user import User


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Proposal User", email=f"prop-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) if roles else ["intern"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


@pytest.mark.asyncio
async def test_only_interns_can_submit_a_proposal(db, client):
    ops = await _user(db, roles=["operations"])
    await db.commit()
    resp = await client.post(
        "/missions/proposals", headers=_headers(ops),
        json={"title": "Ground Station Sim", "description": "A telemetry sim.", "repo_url": "https://example.com/x"},
    )
    assert resp.status_code == http_status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_intern_submits_and_lists_only_their_own_proposals(db, client):
    alice = await _user(db, roles=["intern"])
    bob = await _user(db, roles=["intern"])
    await db.commit()

    create = await client.post(
        "/missions/proposals", headers=_headers(alice),
        json={"title": "Ground Station Sim", "description": "A telemetry sim.", "repo_url": "https://example.com/x"},
    )
    assert create.status_code == 201, create.text
    body = create.json()
    assert body["status"] == "submitted"
    assert body["submitted_by_name"] == "Proposal User"
    assert body["zip_url"] is None

    mine_alice = await client.get("/missions/proposals/mine", headers=_headers(alice))
    assert len(mine_alice.json()) == 1

    mine_bob = await client.get("/missions/proposals/mine", headers=_headers(bob))
    assert mine_bob.json() == []


@pytest.mark.asyncio
async def test_zip_upload_requires_ownership_zip_content_type_and_a_pending_proposal(db, client):
    alice = await _user(db, roles=["intern"])
    bob = await _user(db, roles=["intern"])
    ops = await _user(db, roles=["operations"])
    await db.commit()

    create = await client.post(
        "/missions/proposals", headers=_headers(alice),
        json={"title": "No Repo Yet", "description": "Zip incoming."},
    )
    proposal_id = create.json()["id"]

    not_owner = await client.post(
        f"/missions/proposals/{proposal_id}/zip", headers=_headers(bob),
        files={"file": ("mission.zip", b"PK\x03\x04fake", "application/zip")},
    )
    assert not_owner.status_code == http_status.HTTP_404_NOT_FOUND

    wrong_type = await client.post(
        f"/missions/proposals/{proposal_id}/zip", headers=_headers(alice),
        files={"file": ("notes.txt", b"not a zip", "text/plain")},
    )
    assert wrong_type.status_code == http_status.HTTP_400_BAD_REQUEST

    ok = await client.post(
        f"/missions/proposals/{proposal_id}/zip", headers=_headers(alice),
        files={"file": ("mission.zip", b"PK\x03\x04fake", "application/zip")},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["zip_url"] is not None

    # once staff has moved it into review, the artifact is frozen
    await client.post(
        f"/missions/proposals/{proposal_id}/review", headers=_headers(ops),
        json={"status": "in_review"},
    )
    frozen = await client.post(
        f"/missions/proposals/{proposal_id}/zip", headers=_headers(alice),
        files={"file": ("mission2.zip", b"PK\x03\x04fake2", "application/zip")},
    )
    assert frozen.status_code == http_status.HTTP_409_CONFLICT


@pytest.mark.asyncio
async def test_review_requires_content_role_and_an_artifact_to_review(db, client):
    alice = await _user(db, roles=["intern"])
    ops = await _user(db, roles=["operations"])
    await db.commit()

    create = await client.post(
        "/missions/proposals", headers=_headers(alice),
        json={"title": "Nothing Attached", "description": "Oops, forgot the link."},
    )
    proposal_id = create.json()["id"]

    denied = await client.post(
        f"/missions/proposals/{proposal_id}/review", headers=_headers(alice),
        json={"status": "approved"},
    )
    assert denied.status_code == http_status.HTTP_403_FORBIDDEN

    empty = await client.post(
        f"/missions/proposals/{proposal_id}/review", headers=_headers(ops),
        json={"status": "in_review"},
    )
    assert empty.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_review_queue_and_full_review_lifecycle(db, client):
    alice = await _user(db, roles=["intern"])
    ops = await _user(db, roles=["operations"])
    await db.commit()

    create = await client.post(
        "/missions/proposals", headers=_headers(alice),
        json={"title": "Rover Chassis Sim", "description": "A physics sandbox.", "repo_url": "https://example.com/rover"},
    )
    proposal_id = create.json()["id"]

    queue = await client.get("/missions/proposals/queue", headers=_headers(ops))
    assert any(p["id"] == proposal_id for p in queue.json())

    approve = await client.post(
        f"/missions/proposals/{proposal_id}/review", headers=_headers(ops),
        json={"status": "approved", "review_notes": "Great scope, let's build it"},
    )
    assert approve.status_code == 200, approve.text
    body = approve.json()
    assert body["status"] == "approved"
    assert body["reviewed_by"] == str(ops.id)
    assert body["review_notes"] == "Great scope, let's build it"
    assert body["decided_at"] is not None

    queue_after = await client.get("/missions/proposals/queue", headers=_headers(ops))
    assert not any(p["id"] == proposal_id for p in queue_after.json())


@pytest.mark.asyncio
async def test_link_mission_sets_traceability_pointer(db, client):
    alice = await _user(db, roles=["intern"])
    ops = await _user(db, roles=["operations"])
    mission = Mission(
        id=uuid.uuid4(), title="Rover Chassis Sim", slug=f"rover-sim-{uuid.uuid4().hex[:8]}",
        kind="submission", authored_by=ops.id, status="draft",
    )
    db.add(mission)
    await db.commit()

    create = await client.post(
        "/missions/proposals", headers=_headers(alice),
        json={"title": "Rover Chassis Sim", "description": "d", "repo_url": "https://example.com/rover"},
    )
    proposal_id = create.json()["id"]
    await client.post(
        f"/missions/proposals/{proposal_id}/review", headers=_headers(ops), json={"status": "approved"},
    )

    link = await client.post(
        f"/missions/proposals/{proposal_id}/link-mission", headers=_headers(ops),
        json={"mission_id": str(mission.id)},
    )
    assert link.status_code == 200, link.text
    assert link.json()["mission_id"] == str(mission.id)

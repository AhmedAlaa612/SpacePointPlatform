"""Delivery roles, openings and add-ons over HTTP (I5-3, I5-4, §G-addons).

The guard split is the point. Roles and openings are ops decisions. Add-ons
are the exception: an instructor has to be able to *raise* one, but never to
approve one — that separation is the only thing proposed/agreed exists for.
Redis-free.
"""

import uuid
from datetime import date

import pytest
from sqlalchemy import select

from app.core.security import create_access_token, get_password_hash
from app.models.sessions.cohort import Cohort
from app.models.sessions.delivery_role import DeliveryRole
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor
from app.models.user import User


async def _user(db, *roles: str) -> User:
    u = User(
        id=uuid.uuid4(), full_name=f"P{uuid.uuid4().hex[:4]}",
        email=f"u-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("x"), roles=list(roles), status="active",
    )
    db.add(u)
    await db.flush()
    return u


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _role_id(db, name: str = "Lead Facilitator"):
    return await db.scalar(select(DeliveryRole.id).where(DeliveryRole.name == name))


async def _session(db, instructor: User | None = None) -> Session:
    program = Program(
        id=uuid.uuid4(), code=f"P-{uuid.uuid4().hex[:8]}", name="P",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="C", status="running")
    db.add(cohort)
    await db.flush()
    session = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date.today())
    db.add(session)
    await db.flush()
    if instructor:
        db.add(SessionInstructor(
            id=uuid.uuid4(), session_id=session.id, user_id=instructor.id,
            role_id=await _role_id(db),
        ))
        await db.flush()
    return session


# ── delivery roles ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_three_seeded_roles_are_there_in_seniority_order(client, db):
    """Seeded by migration `c2a7b49e0022`, because `session_instructors.role_id`
    is NOT NULL and the backfill could not run without them."""
    ops = await _user(db, "operations")
    r = await client.get("/sessions/delivery-roles", headers=_headers(ops))
    assert r.status_code == 200
    names = [row["name"] for row in r.json()]
    assert names[:3] == ["Lead Facilitator", "Facilitator", "Assistant Facilitator"]


@pytest.mark.asyncio
async def test_an_instructor_can_read_roles_but_not_add_one(client, db):
    """They need the vocabulary — their own session shows the role they hold —
    but defining it is an ops decision."""
    instructor = await _user(db, "instructor")
    assert (await client.get(
        "/sessions/delivery-roles", headers=_headers(instructor)
    )).status_code == 200
    assert (await client.post(
        "/sessions/delivery-roles", json={"name": "Sneaky"}, headers=_headers(instructor)
    )).status_code == 403


@pytest.mark.asyncio
async def test_ops_can_add_a_role_and_it_appends_to_the_end(client, db):
    """The CEO's "+ to add more". Appending rather than inserting means adding
    a role never silently reorders seniority."""
    ops = await _user(db, "operations")
    r = await client.post(
        "/sessions/delivery-roles", json={"name": "Observer"}, headers=_headers(ops)
    )
    assert r.status_code == 201
    assert r.json()["sort_order"] > 3


# ── openings ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ops_sets_openings_and_remaining_is_derived(client, db):
    ops = await _user(db, "operations")
    session = await _session(db)
    lead = await _role_id(db)
    assistant = await _role_id(db, "Assistant Facilitator")

    r = await client.put(
        f"/sessions/{session.id}/openings",
        json={"openings": [
            {"role_id": str(lead), "slots": 1, "amount_aed": "2000"},
            {"role_id": str(assistant), "slots": 2, "amount_aed": "400"},
        ]},
        headers=_headers(ops),
    )
    assert r.status_code == 200
    rows = r.json()
    assert [row["role_name"] for row in rows] == ["Lead Facilitator", "Assistant Facilitator"]
    assert [row["remaining"] for row in rows] == [1, 2]


@pytest.mark.asyncio
async def test_an_instructor_can_see_openings_but_not_set_them(client, db):
    """They are what the invite is made of, so instructors read them."""
    ops = await _user(db, "operations")
    instructor = await _user(db, "instructor")
    session = await _session(db, instructor)
    await client.put(
        f"/sessions/{session.id}/openings",
        json={"openings": [{"role_id": str(await _role_id(db)), "slots": 1}]},
        headers=_headers(ops),
    )

    assert (await client.get(
        f"/sessions/{session.id}/openings", headers=_headers(instructor)
    )).status_code == 200
    assert (await client.put(
        f"/sessions/{session.id}/openings", json={"openings": []},
        headers=_headers(instructor),
    )).status_code == 403


@pytest.mark.asyncio
async def test_an_unrelated_instructor_gets_404_on_openings(client, db):
    ops = await _user(db, "operations")
    instructor = await _user(db, "instructor")
    stranger = await _user(db, "instructor")
    session = await _session(db, instructor)
    await client.put(
        f"/sessions/{session.id}/openings",
        json={"openings": [{"role_id": str(await _role_id(db)), "slots": 1}]},
        headers=_headers(ops),
    )

    r = await client.get(f"/sessions/{session.id}/openings", headers=_headers(stranger))
    assert r.status_code == 404


# ── add-ons ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_an_ops_offer_lands_agreed_and_an_instructor_request_lands_proposed(client, db):
    """One column doing the work of an approval feature."""
    ops = await _user(db, "operations")
    instructor = await _user(db, "instructor")
    session = await _session(db, instructor)

    r = await client.post(
        f"/sessions/{session.id}/addons",
        json={"description": "Poster printing", "amount_aed": "200", "source": "offer"},
        headers=_headers(ops),
    )
    assert r.status_code == 201 and r.json()["status"] == "agreed"

    r = await client.post(
        f"/sessions/{session.id}/addons",
        json={"description": "Taxi", "amount_aed": "80", "source": "survey"},
        headers=_headers(instructor),
    )
    assert r.status_code == 201 and r.json()["status"] == "proposed"


@pytest.mark.asyncio
async def test_an_instructor_cannot_smuggle_in_a_pre_agreed_addon(client, db):
    """Claiming `source: offer` would otherwise arrive `agreed` — the router
    forces an instructor-side source and pins it to them."""
    instructor = await _user(db, "instructor")
    other = await _user(db, "instructor")
    session = await _session(db, instructor)

    r = await client.post(
        f"/sessions/{session.id}/addons",
        json={
            "description": "Definitely approved", "amount_aed": "5000",
            "source": "offer", "user_id": str(other.id),
        },
        headers=_headers(instructor),
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "proposed"
    assert body["source"] in {"interest", "survey"}
    assert body["user_id"] == str(instructor.id)   # not `other`


@pytest.mark.asyncio
async def test_only_ops_can_answer_a_request(client, db):
    """The one thing proposed/agreed exists to prevent is self-approval."""
    ops = await _user(db, "operations")
    instructor = await _user(db, "instructor")
    session = await _session(db, instructor)

    created = (await client.post(
        f"/sessions/{session.id}/addons",
        json={"description": "Extra hour", "amount_aed": "100", "source": "interest"},
        headers=_headers(instructor),
    )).json()

    assert (await client.put(
        f"/sessions/addons/{created['id']}/decision",
        json={"status": "agreed"}, headers=_headers(instructor),
    )).status_code == 403

    r = await client.put(
        f"/sessions/addons/{created['id']}/decision",
        json={"status": "agreed"}, headers=_headers(ops),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "agreed" and r.json()["decided_at"] is not None


@pytest.mark.asyncio
async def test_mine_narrows_to_this_persons_addons(client, db):
    ops = await _user(db, "operations")
    instructor = await _user(db, "instructor")
    session = await _session(db, instructor)

    await client.post(
        f"/sessions/{session.id}/addons",
        json={"description": "Mine", "amount_aed": "50", "source": "offer",
              "user_id": str(instructor.id)},
        headers=_headers(ops),
    )
    await client.post(
        f"/sessions/{session.id}/addons",
        json={"description": "Somebody else's", "amount_aed": "50", "source": "offer",
              "user_id": str(ops.id)},
        headers=_headers(ops),
    )

    r = await client.get(
        f"/sessions/{session.id}/addons", params={"mine": True}, headers=_headers(instructor)
    )
    assert [row["description"] for row in r.json()] == ["Mine"]

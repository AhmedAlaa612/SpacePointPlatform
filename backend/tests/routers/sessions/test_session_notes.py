"""The session comment box (I2-7 follow-up, operator 2026-07-30).

Its reason for existing is narrow: equipment pickup can only offer what
`stock_levels` says is on the shelf, so until ops has entered the co-working
stock, an instructor who took something the register has never heard of has
nowhere to say so. This is that nowhere-else. Redis-free.
"""

import uuid
from datetime import date

import pytest

from app.core.security import create_access_token, get_password_hash
from app.models.sessions.cohort import Cohort
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


async def _session(db, lead: User | None = None) -> Session:
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
    if lead:
        db.add(SessionInstructor(
            id=uuid.uuid4(), session_id=session.id, user_id=lead.id, role="lead"
        ))
        await db.flush()
    return session


@pytest.mark.asyncio
async def test_an_instructor_can_leave_a_note_and_read_it_back(client, db):
    instructor = await _user(db, "instructor")
    session = await _session(db, instructor)

    r = await client.put(
        f"/sessions/{session.id}/delivery/notes",
        json={"notes": "Took a mic speaker that isn't in the list"},
        headers=_headers(instructor),
    )
    assert r.status_code == 200
    assert r.json()["notes"] == "Took a mic speaker that isn't in the list"

    r = await client.get(f"/sessions/{session.id}/delivery", headers=_headers(instructor))
    assert r.json()["notes"] == "Took a mic speaker that isn't in the list"


@pytest.mark.asyncio
async def test_a_session_with_no_note_reports_null_not_empty_string(client, db):
    """So "nobody wrote anything" and "someone cleared it" look the same to
    every reader, and the UI has one case to render rather than two."""
    instructor = await _user(db, "instructor")
    session = await _session(db, instructor)

    r = await client.get(f"/sessions/{session.id}/delivery", headers=_headers(instructor))
    assert r.json()["notes"] is None

    r = await client.put(
        f"/sessions/{session.id}/delivery/notes",
        json={"notes": "   "}, headers=_headers(instructor),
    )
    assert r.json()["notes"] is None


@pytest.mark.asyncio
async def test_saving_again_replaces_the_text(client, db):
    """It is one text area, not a log — the client sends what is now in it."""
    instructor = await _user(db, "instructor")
    session = await _session(db, instructor)

    await client.put(f"/sessions/{session.id}/delivery/notes",
                     json={"notes": "first"}, headers=_headers(instructor))
    r = await client.put(f"/sessions/{session.id}/delivery/notes",
                         json={"notes": "second"}, headers=_headers(instructor))
    assert r.json()["notes"] == "second"


@pytest.mark.asyncio
async def test_an_unrelated_instructor_gets_404_not_403(client, db):
    """Same don't-leak-existence rule as the rest of the delivery flow."""
    instructor = await _user(db, "instructor")
    stranger = await _user(db, "instructor")
    session = await _session(db, instructor)

    r = await client.put(
        f"/sessions/{session.id}/delivery/notes",
        json={"notes": "nope"}, headers=_headers(stranger),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_ops_can_read_and_write_it_too(client, db):
    """Ops is the audience — the box exists so they find out about the gap."""
    instructor = await _user(db, "instructor")
    ops = await _user(db, "operations")
    session = await _session(db, instructor)

    await client.put(f"/sessions/{session.id}/delivery/notes",
                     json={"notes": "speaker not on the register"},
                     headers=_headers(instructor))

    r = await client.get(f"/sessions/{session.id}/delivery", headers=_headers(ops))
    assert r.status_code == 200
    assert r.json()["notes"] == "speaker not on the register"


@pytest.mark.asyncio
async def test_a_note_can_still_be_left_after_the_session_is_done(client, db):
    """A note remembered on the drive home is exactly the note worth keeping,
    so this deliberately does not lock on `completed_at`."""
    instructor = await _user(db, "instructor")
    session = await _session(db, instructor)
    await client.post(f"/sessions/{session.id}/delivery/start", headers=_headers(instructor))
    await client.post(f"/sessions/{session.id}/delivery/done", headers=_headers(instructor))

    r = await client.put(
        f"/sessions/{session.id}/delivery/notes",
        json={"notes": "forgot to mention the charger"}, headers=_headers(instructor),
    )
    assert r.status_code == 200
    assert r.json()["notes"] == "forgot to mention the charger"

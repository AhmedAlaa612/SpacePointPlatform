"""Delete endpoints for programs, cohorts, sessions and registrations
(operator request 2026-07-26 — none of these existed; only edit did).

Every one of these cascades hard in the schema: programs -> cohorts ->
registrations -> attendance. So the interesting cases here aren't the happy
paths, they're the refusals — each endpoint must decline rather than quietly
destroy real history, and say why.
"""

import uuid
from datetime import date

import httpx
import pytest
from sqlalchemy import select

from app.db.session import get_db
from app.main import app
from app.models.certificate import Certificate
from app.models.enums import CertificateType
from app.models.sessions.attendance import AttendanceRecord
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.sessions.session import Session
from app.models.spine.contact import Contact
from app.models.user import User
from app.workers.settings import get_arq_redis


@pytest.fixture
async def client(db):
    """Redis-free: none of the delete endpoints enqueue a job, so requiring a
    live Redis to test them only makes the suite fragile."""
    async def _override_get_db():
        yield db

    async def _override_get_arq_redis():
        return None

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_arq_redis] = _override_get_arq_redis
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    app.dependency_overrides.clear()


async def _make_program(db, **overrides) -> Program:
    defaults = dict(
        id=uuid.uuid4(), code=f"DEL-{uuid.uuid4().hex[:8]}", name="Deletable Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    defaults.update(overrides)
    program = Program(**defaults)
    db.add(program)
    await db.flush()
    return program


async def _make_cohort(db, program: Program, **overrides) -> Cohort:
    defaults = dict(
        id=uuid.uuid4(), program_id=program.id, name="Deletable Cohort",
        status="planned", visibility="public",
    )
    defaults.update(overrides)
    cohort = Cohort(**defaults)
    db.add(cohort)
    await db.flush()
    return cohort


async def _make_session(db, cohort: Cohort, **overrides) -> Session:
    defaults = dict(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 9, 1))
    defaults.update(overrides)
    session = Session(**defaults)
    db.add(session)
    await db.flush()
    return session


async def _make_registration(db, cohort: Cohort, name="Deletable Student") -> Registration:
    contact = Contact(id=uuid.uuid4(), full_name=name, email=f"{uuid.uuid4().hex[:8]}@example.com")
    db.add(contact)
    await db.flush()
    registration = Registration(
        id=uuid.uuid4(), contact_id=contact.id, cohort_id=cohort.id,
        ticket_token=uuid.uuid4().hex, registered_via="desk",
    )
    db.add(registration)
    await db.flush()
    return registration


# ── Programs ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_empty_program(db, client, operations_headers):
    program = await _make_program(db)
    await db.commit()

    resp = await client.delete(f"/sessions/programs/{program.id}", headers=operations_headers)
    assert resp.status_code == 204, resp.text
    assert await db.get(Program, program.id) is None


@pytest.mark.asyncio
async def test_delete_program_with_cohorts_refused(db, client, operations_headers):
    """Unguarded, this would cascade every cohort and registration away."""
    program = await _make_program(db)
    cohort = await _make_cohort(db, program)
    await db.commit()

    resp = await client.delete(f"/sessions/programs/{program.id}", headers=operations_headers)
    assert resp.status_code == 409, resp.text
    assert "cohort" in resp.json()["detail"].lower()
    assert await db.get(Program, program.id) is not None
    assert await db.get(Cohort, cohort.id) is not None


@pytest.mark.asyncio
async def test_delete_program_requires_operations(db, client, other_role_headers):
    program = await _make_program(db)
    await db.commit()
    resp = await client.delete(f"/sessions/programs/{program.id}", headers=other_role_headers)
    assert resp.status_code == 403


# ── Cohorts ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_cohort_takes_its_sessions_with_it(db, client, operations_headers):
    program = await _make_program(db)
    cohort = await _make_cohort(db, program)
    session = await _make_session(db, cohort)
    await db.commit()

    resp = await client.delete(f"/sessions/cohorts/{cohort.id}", headers=operations_headers)
    assert resp.status_code == 204, resp.text
    assert await db.get(Cohort, cohort.id) is None

    # The session goes via ON DELETE CASCADE in the database, which the ORM
    # never sees — db.get would hand back the still-cached identity-map object.
    # Query for it instead of trusting the session's cache.
    db.expunge_all()
    remaining = (await db.execute(select(Session).where(Session.id == session.id))).scalars().first()
    # No registrations means no attendance could hang off these, so cascading
    # the sessions away is safe.
    assert remaining is None


@pytest.mark.asyncio
async def test_delete_cohort_with_registrations_refused(db, client, operations_headers):
    program = await _make_program(db)
    cohort = await _make_cohort(db, program)
    registration = await _make_registration(db, cohort)
    await db.commit()

    resp = await client.delete(f"/sessions/cohorts/{cohort.id}", headers=operations_headers)
    assert resp.status_code == 409, resp.text
    assert "cancelled" in resp.json()["detail"].lower()
    assert await db.get(Registration, registration.id) is not None


@pytest.mark.asyncio
async def test_cancelled_registration_still_blocks_cohort_delete(db, client, operations_headers):
    """A cancellation is a record of something that happened, not a free slot."""
    program = await _make_program(db)
    cohort = await _make_cohort(db, program)
    registration = await _make_registration(db, cohort)
    registration.status = "cancelled"
    await db.commit()

    resp = await client.delete(f"/sessions/cohorts/{cohort.id}", headers=operations_headers)
    assert resp.status_code == 409, resp.text


# ── Sessions ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_session_without_attendance(db, client, operations_headers):
    program = await _make_program(db)
    cohort = await _make_cohort(db, program)
    session = await _make_session(db, cohort)
    await db.commit()

    resp = await client.delete(
        f"/sessions/cohorts/{cohort.id}/sessions/{session.id}", headers=operations_headers,
    )
    assert resp.status_code == 204, resp.text
    assert await db.get(Session, session.id) is None


@pytest.mark.asyncio
async def test_delete_session_with_attendance_refused(
    db, client, operations_headers, operations_user: User,
):
    program = await _make_program(db)
    cohort = await _make_cohort(db, program)
    session = await _make_session(db, cohort)
    registration = await _make_registration(db, cohort)
    db.add(AttendanceRecord(
        id=uuid.uuid4(), registration_id=registration.id, session_id=session.id,
        att_status="present", method="manual", recorded_by_user_id=operations_user.id,
    ))
    await db.commit()

    resp = await client.delete(
        f"/sessions/cohorts/{cohort.id}/sessions/{session.id}", headers=operations_headers,
    )
    assert resp.status_code == 409, resp.text
    assert await db.get(Session, session.id) is not None


@pytest.mark.asyncio
async def test_delete_session_from_wrong_cohort_is_404(db, client, operations_headers):
    program = await _make_program(db)
    cohort_a = await _make_cohort(db, program)
    cohort_b = await _make_cohort(db, program, name="Other Cohort")
    session = await _make_session(db, cohort_a)
    await db.commit()

    resp = await client.delete(
        f"/sessions/cohorts/{cohort_b.id}/sessions/{session.id}", headers=operations_headers,
    )
    assert resp.status_code == 404, resp.text
    assert await db.get(Session, session.id) is not None


# ── Registrations ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_registration_leaves_the_contact_alone(db, client, operations_headers):
    """Removing a wrong-cohort sign-up must not delete the person."""
    program = await _make_program(db)
    cohort = await _make_cohort(db, program)
    registration = await _make_registration(db, cohort)
    contact_id = registration.contact_id
    await db.commit()

    resp = await client.delete(
        f"/sessions/registrations/{registration.id}", headers=operations_headers,
    )
    assert resp.status_code == 204, resp.text
    assert await db.get(Registration, registration.id) is None
    assert await db.get(Contact, contact_id) is not None


@pytest.mark.asyncio
async def test_delete_registration_takes_attendance_and_certificate_with_it(
    db, client, operations_headers, operations_user: User,
):
    """Delete is the destructive option (operator, 2026-07-26) — it no longer
    holds back once attendance exists. Certificates are removed explicitly:
    certificates.registration_id is SET NULL, so they'd otherwise survive as
    orphans pointing at nobody."""
    program = await _make_program(db)
    cohort = await _make_cohort(db, program)
    session = await _make_session(db, cohort)
    registration = await _make_registration(db, cohort)
    db.add(AttendanceRecord(
        id=uuid.uuid4(), registration_id=registration.id, session_id=session.id,
        att_status="present", method="manual", recorded_by_user_id=operations_user.id,
    ))
    db.add(Certificate(
        id=uuid.uuid4(), contact_id=registration.contact_id, registration_id=registration.id,
        type=CertificateType.student_completion, workshop_name=program.name,
    ))
    await db.commit()
    registration_id, contact_id = registration.id, registration.contact_id

    resp = await client.delete(
        f"/sessions/registrations/{registration_id}", headers=operations_headers,
    )
    assert resp.status_code == 204, resp.text

    db.expunge_all()
    assert (await db.execute(
        select(Registration).where(Registration.id == registration_id)
    )).scalars().first() is None
    assert (await db.execute(
        select(AttendanceRecord).where(AttendanceRecord.registration_id == registration_id)
    )).scalars().first() is None
    assert (await db.execute(
        select(Certificate).where(Certificate.registration_id == registration_id)
    )).scalars().first() is None
    # The person stays unless explicitly asked for.
    assert await db.get(Contact, contact_id) is not None


@pytest.mark.asyncio
async def test_delete_registration_can_also_delete_the_contact(db, client, operations_headers):
    program = await _make_program(db)
    cohort = await _make_cohort(db, program)
    registration = await _make_registration(db, cohort)
    await db.commit()
    contact_id = registration.contact_id

    resp = await client.delete(
        f"/sessions/registrations/{registration.id}?delete_contact=true", headers=operations_headers,
    )
    assert resp.status_code == 204, resp.text

    db.expunge_all()
    assert (await db.execute(
        select(Contact).where(Contact.id == contact_id)
    )).scalars().first() is None


@pytest.mark.asyncio
async def test_delete_contact_refused_when_registered_elsewhere(db, client, operations_headers):
    """contacts.id cascades to nine tables, so this would silently erase the
    other cohort's registration and its attendance."""
    program = await _make_program(db)
    cohort_a = await _make_cohort(db, program)
    cohort_b = await _make_cohort(db, program, name="Other Cohort")
    registration = await _make_registration(db, cohort_a)
    db.add(Registration(
        id=uuid.uuid4(), contact_id=registration.contact_id, cohort_id=cohort_b.id,
        ticket_token=uuid.uuid4().hex, registered_via="desk",
    ))
    await db.commit()

    resp = await client.delete(
        f"/sessions/registrations/{registration.id}?delete_contact=true", headers=operations_headers,
    )
    assert resp.status_code == 409, resp.text
    assert "other cohort" in resp.json()["detail"].lower()
    assert await db.get(Contact, registration.contact_id) is not None
    # Refused before anything was removed.
    assert await db.get(Registration, registration.id) is not None


@pytest.mark.asyncio
async def test_delete_contact_refused_for_a_staff_account(
    db, client, operations_headers, operations_user: User,
):
    """Never delete the person record behind a real login."""
    program = await _make_program(db)
    cohort = await _make_cohort(db, program)
    registration = await _make_registration(db, cohort)
    operations_user.contact_id = registration.contact_id
    await db.commit()

    resp = await client.delete(
        f"/sessions/registrations/{registration.id}?delete_contact=true", headers=operations_headers,
    )
    assert resp.status_code == 409, resp.text
    assert "staff account" in resp.json()["detail"].lower()
    assert await db.get(Registration, registration.id) is not None

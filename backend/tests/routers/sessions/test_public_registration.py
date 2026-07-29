"""Mandatory e2e test for V2 R1-5 (see MASTER_EXECUTION_PLAN_V2.md R1-5):
POST -> contact + guardian + relationship + registration + touchpoint +
email-sent flag all correct; second POST same phone+cohort -> 409; honeypot
dropped. No age/DOB, no consent record — both removed from this flow
entirely (see MASTER_EXECUTION_PLAN.md amendment).
"""

import uuid

import httpx
import pytest
from sqlalchemy import select

from app.db.session import get_db
from app.main import app
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.spine.contact import Contact, ContactRelationship
from app.models.spine.identity_alias import IdentityAlias
from app.models.sessions.registration import Registration
from app.models.spine.touchpoint import Touchpoint
from app.workers.settings import get_arq_redis


async def _make_public_cohort(db) -> Cohort:
    program = Program(
        id=uuid.uuid4(), code=f"E2E-{uuid.uuid4().hex[:8]}", name="E2E Workshop",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(
        id=uuid.uuid4(), program_id=program.id, name="E2E Cohort",
        status="registration_open", visibility="public",
    )
    db.add(cohort)
    await db.flush()
    return cohort


# `client` (Redis-free) and `arq_client` (real ARQ pool) live in
# tests/conftest.py. The local copy that used to be here bound *every* test in
# this file to a live Redis, including ones that never enqueue anything (I0-1b).


def _unique_ip_headers(tag: str) -> dict:
    # The rate limiter's bucket key comes from X-Forwarded-For; give each
    # test its own fake IP so they don't share a bucket across the whole
    # pytest session (the limiter's state is module-level, not per-test).
    return {"X-Forwarded-For": f"203.0.113.{abs(hash(tag)) % 250 + 1}"}


@pytest.mark.asyncio
async def test_registration_creates_everything_correctly(db, arq_client, arq_redis):
    # arq_client (not client): this test asserts the ticket job actually
    # reached the queue, so it needs a real ARQ pool wired into the app.
    cohort = await _make_public_cohort(db)
    headers = _unique_ip_headers("registration")

    resp = await arq_client.post(
        f"/public/register/{cohort.id}",
        json={
            "student_name": "New Student",
            "email": "new.student@example.com",
            "phone": "050 111 2222",
            "city": "Dubai",
        },
        headers=headers,
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["email"].startswith("ne") and body["email"].endswith("@example.com")

    contact = (await db.execute(
        select(Contact).where(Contact.email == "new.student@example.com")
    )).scalars().first()
    assert contact is not None
    assert contact.contact_roles == ["student"]

    alias = (await db.execute(
        select(IdentityAlias).where(IdentityAlias.contact_id == contact.id, IdentityAlias.alias_type == "email")
    )).scalars().first()
    assert alias is not None  # identity_aliases actually got populated

    registration = (await db.execute(
        select(Registration).where(Registration.contact_id == contact.id, Registration.cohort_id == cohort.id)
    )).scalars().first()
    assert registration is not None
    assert registration.registered_via == "form"

    touchpoint = (await db.execute(
        select(Touchpoint).where(Touchpoint.contact_id == contact.id, Touchpoint.touchpoint_type == "registration")
    )).scalars().first()
    assert touchpoint is not None

    # Ticket email is now dispatched via ARQ (V2 R2-1), not sent synchronously
    # in the request — so ticket_sent_at stays NULL here regardless of SMTP
    # config, because no worker process is running during this test to
    # actually consume the job. What we can and must verify is that the job
    # was genuinely enqueued, not silently dropped. The arq_redis fixture
    # flushes its DB after every test, so any job present here can only be
    # the one this request just queued.
    await db.refresh(registration)
    assert registration.ticket_sent_at is None
    queued_jobs = await arq_redis.zrange("arq:queue", 0, -1)
    assert len(queued_jobs) == 1


@pytest.mark.asyncio
async def test_registration_with_parent_info_creates_guardian_and_relationship(db, client):
    """Parent info is always optional — no age/minor detection or enforcement
    anywhere in this system. If given, it creates/links a guardian contact
    and sets them as payer."""
    cohort = await _make_public_cohort(db)
    headers = _unique_ip_headers("registration_with_parent")

    resp = await client.post(
        f"/public/register/{cohort.id}",
        json={
            "student_name": "Student With Parent",
            "email": "student.withparent@example.com",
            "phone": "050 333 4444",
            "parent_name": "The Parent",
            "parent_phone": "050 555 6666",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text

    student = (await db.execute(
        select(Contact).where(Contact.email == "student.withparent@example.com")
    )).scalars().first()

    guardian = (await db.execute(
        select(Contact).where(Contact.contact_roles.any("parent_guardian"))
    )).scalars().first()
    assert guardian is not None
    assert guardian.full_name == "The Parent"

    relationship = (await db.execute(
        select(ContactRelationship).where(
            ContactRelationship.contact_id == guardian.id,
            ContactRelationship.related_contact_id == student.id,
        )
    )).scalars().first()
    assert relationship is not None
    assert relationship.relation == "guardian_of"

    registration = (await db.execute(
        select(Registration).where(Registration.contact_id == student.id)
    )).scalars().first()
    assert registration.payer_contact_id == guardian.id


@pytest.mark.asyncio
async def test_registration_without_parent_info_has_no_payer(db, client):
    cohort = await _make_public_cohort(db)
    headers = _unique_ip_headers("registration_no_parent")

    resp = await client.post(
        f"/public/register/{cohort.id}",
        json={
            "student_name": "No Parent Info",
            "email": "no.parent.public@example.com",
            "phone": "050 777 8888",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text

    student = (await db.execute(
        select(Contact).where(Contact.email == "no.parent.public@example.com")
    )).scalars().first()
    registration = (await db.execute(
        select(Registration).where(Registration.contact_id == student.id)
    )).scalars().first()
    assert registration.payer_contact_id is None


@pytest.mark.asyncio
async def test_duplicate_registration_same_phone_and_cohort_returns_409(db, client):
    cohort = await _make_public_cohort(db)
    headers = _unique_ip_headers("duplicate_registration")
    payload = {
        "student_name": "Repeat Student",
        "email": "repeat.student@example.com",
        "phone": "050 999 0000",
    }

    first = await client.post(f"/public/register/{cohort.id}", json=payload, headers=headers)
    assert first.status_code == 201, first.text

    second = await client.post(f"/public/register/{cohort.id}", json=payload, headers=headers)
    assert second.status_code == 409
    assert "already registered" in second.json()["detail"].lower()


@pytest.mark.asyncio
async def test_honeypot_filled_drops_silently(db, client):
    cohort = await _make_public_cohort(db)
    headers = _unique_ip_headers("honeypot")

    resp = await client.post(
        f"/public/register/{cohort.id}",
        json={
            "student_name": "Bot",
            "email": "bot@example.com",
            "phone": "050 123 9999",
            "website": "http://spammy-bot.example",  # a human never fills this
        },
        headers=headers,
    )
    assert resp.status_code == 201  # looks like success to the bot...

    contact = (await db.execute(
        select(Contact).where(Contact.email == "bot@example.com")
    )).scalars().first()
    assert contact is None  # ...but nothing was actually created


@pytest.mark.asyncio
async def test_nonexistent_cohort_returns_404(db, client):
    headers = _unique_ip_headers("nonexistent_cohort")
    resp = await client.post(
        f"/public/register/{uuid.uuid4()}",
        json={"student_name": "X", "email": "x@example.com", "phone": "0501234567"},
        headers=headers,
    )
    assert resp.status_code == 404

"""POST /public/interest — "Notify me" for a `planned` cohort (2026-08-07).

Same identity-resolution posture as public_register (resolve_or_create_contact,
honeypot, rate limit) but writes to `cohort_interest`, not `Registration` — see
the model docstring for why. Redis-free (`client` fixture) — this endpoint
itself never enqueues; the notify job is enqueued by `update_cohort` when a
cohort's status actually flips, tested separately below.
"""

import uuid

import pytest
from sqlalchemy import select

from app.models.sessions.cohort import Cohort
from app.models.sessions.cohort_interest import CohortInterest
from app.models.sessions.program import Program
from app.models.spine.contact import Contact


async def _make_program(db, **overrides) -> Program:
    defaults = dict(
        id=uuid.uuid4(), code=f"INT-{uuid.uuid4().hex[:8]}", name="Interest Test Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    defaults.update(overrides)
    program = Program(**defaults)
    db.add(program)
    await db.flush()
    return program


async def _make_cohort(db, program: Program, **overrides) -> Cohort:
    defaults = dict(
        id=uuid.uuid4(), program_id=program.id, name="Interest Test Cohort",
        status="planned", visibility="public",
    )
    defaults.update(overrides)
    cohort = Cohort(**defaults)
    db.add(cohort)
    await db.flush()
    return cohort


def _unique_ip_headers(tag: str) -> dict:
    return {"X-Forwarded-For": f"203.0.113.{abs(hash(tag)) % 250 + 1}"}


@pytest.mark.asyncio
async def test_interest_creates_a_contact_and_a_cohort_interest_row(db, client):
    program = await _make_program(db)
    cohort = await _make_cohort(db, program)

    resp = await client.post(
        f"/public/interest/{cohort.id}",
        json={"student_name": "Interested Student", "email": "interested@example.com", "phone": "050 111 2222"},
        headers=_unique_ip_headers("interest-create"),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["email"].endswith("@example.com")

    contact = (await db.execute(
        select(Contact).where(Contact.email == "interested@example.com")
    )).scalars().first()
    assert contact is not None and contact.contact_roles == ["student"]

    row = (await db.execute(
        select(CohortInterest).where(CohortInterest.contact_id == contact.id, CohortInterest.cohort_id == cohort.id)
    )).scalars().first()
    assert row is not None
    assert row.notified_at is None


@pytest.mark.asyncio
async def test_interest_is_idempotent_for_the_same_contact_and_cohort(db, client):
    program = await _make_program(db)
    cohort = await _make_cohort(db, program)
    body = {"student_name": "Repeat Student", "email": "repeat@example.com", "phone": "050 333 4444"}

    first = await client.post(f"/public/interest/{cohort.id}", json=body, headers=_unique_ip_headers("interest-repeat"))
    second = await client.post(f"/public/interest/{cohort.id}", json=body, headers=_unique_ip_headers("interest-repeat"))
    assert first.status_code == 201 and second.status_code == 201

    rows = (await db.execute(
        select(CohortInterest).join(Contact, Contact.id == CohortInterest.contact_id)
        .where(Contact.email == "repeat@example.com")
    )).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_interest_rejects_non_planned_and_private_cohorts(db, client):
    program = await _make_program(db)
    already_open = await _make_cohort(db, program, status="registration_open")
    private_planned = await _make_cohort(db, program, visibility="private")
    body = {"student_name": "X", "email": "x@example.com", "phone": "050 000 0000"}

    resp1 = await client.post(f"/public/interest/{already_open.id}", json=body, headers=_unique_ip_headers("interest-open"))
    assert resp1.status_code == 404

    resp2 = await client.post(f"/public/interest/{private_planned.id}", json=body, headers=_unique_ip_headers("interest-private"))
    assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_interest_honeypot_drops_silently(db, client):
    program = await _make_program(db)
    cohort = await _make_cohort(db, program)

    resp = await client.post(
        f"/public/interest/{cohort.id}",
        json={"student_name": "Bot", "email": "bot@example.com", "phone": "0", "website": "http://spam.example"},
        headers=_unique_ip_headers("interest-honeypot"),
    )
    assert resp.status_code == 201
    row = (await db.execute(select(CohortInterest))).scalars().first()
    assert row is None

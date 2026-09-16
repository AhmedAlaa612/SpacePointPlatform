"""Tests for the registration desk's registrations list + manual-registration
+ ticket/payment actions (V2 R2-3). Reuses the same assertions
test_public_registration.py already makes for contact/registration/touchpoint
creation, since desk_register in routers/sessions/cohorts.py is a deliberate
near-duplicate of public_register (registered_via="desk" instead of "form").
"""

import uuid

import httpx
import pytest
from sqlalchemy import select

from app.db.session import get_db
from app.main import app
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact, ContactRelationship
from app.models.spine.touchpoint import Touchpoint
from app.services.sessions.registration import register
from app.workers.settings import get_arq_redis


# `client` (Redis-free) and `arq_client` (real ARQ pool) live in
# tests/conftest.py. The local copy that used to be here bound *every* test in
# this file to a live Redis, including ones that never enqueue anything (I0-1b).


async def _make_cohort(db, **overrides) -> Cohort:
    program = Program(
        id=uuid.uuid4(), code=f"DESK-{uuid.uuid4().hex[:8]}", name="Desk Test Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    defaults = dict(
        id=uuid.uuid4(), program_id=program.id, name="Desk Test Cohort",
        status="registration_open", visibility="public",
    )
    defaults.update(overrides)
    cohort = Cohort(**defaults)
    db.add(cohort)
    await db.flush()
    return cohort


def _new_contact(**overrides) -> Contact:
    defaults = dict(
        id=uuid.uuid4(), full_name="Existing Contact", contact_roles=["student"],
        secondary_phones=[], preferred_language="ar", lifecycle_stage="lead",
    )
    defaults.update(overrides)
    return Contact(**defaults)


# ── Manual (desk) registration ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_desk_register_creates_contact_registration_and_touchpoint(db, arq_client, operations_headers, arq_redis):
    # arq_client (not client): asserts the ticket job reached the queue.
    cohort = await _make_cohort(db)

    resp = await arq_client.post(
        f"/sessions/cohorts/{cohort.id}/registrations",
        json={
            "student_name": "Desk Student",
            "email": "desk.student@example.com",
            "phone": "050 222 3333",
            "city": "Abu Dhabi",
        },
        headers=operations_headers,
    )
    assert resp.status_code == 201, resp.text

    contact = (await db.execute(
        select(Contact).where(Contact.email == "desk.student@example.com")
    )).scalars().first()
    assert contact is not None
    assert contact.contact_roles == ["student"]

    registration = (await db.execute(
        select(Registration).where(Registration.contact_id == contact.id, Registration.cohort_id == cohort.id)
    )).scalars().first()
    assert registration is not None
    assert registration.registered_via == "desk"

    touchpoint = (await db.execute(
        select(Touchpoint).where(Touchpoint.contact_id == contact.id, Touchpoint.touchpoint_type == "registration")
    )).scalars().first()
    assert touchpoint is not None
    assert touchpoint.channel == "offline"  # registered_via='desk' -> channel='offline'

    # Ticket email enqueued via ARQ (send_ticket_email defaults to true).
    queued_jobs = await arq_redis.zrange("arq:queue", 0, -1)
    assert len(queued_jobs) == 1


@pytest.mark.asyncio
async def test_desk_register_can_skip_ticket_email(db, arq_client, operations_headers, arq_redis):
    # arq_client (not client): asserts the queue stayed EMPTY. With a
    # Redis-free client that would pass vacuously — nothing can ever enqueue.
    cohort = await _make_cohort(db)

    resp = await arq_client.post(
        f"/sessions/cohorts/{cohort.id}/registrations",
        json={
            "student_name": "No Email Student",
            "email": "no.email.ticket@example.com",
            "phone": "050 111 4444",
            "send_ticket_email": False,
        },
        headers=operations_headers,
    )
    assert resp.status_code == 201, resp.text
    assert await arq_redis.zrange("arq:queue", 0, -1) == []


@pytest.mark.asyncio
async def test_desk_register_with_parent_info_creates_guardian_and_relationship(db, client, operations_headers):
    """Parent info is always optional — no age/minor detection or enforcement
    anywhere in this system. If given, it creates/links a guardian contact
    and sets them as payer."""
    cohort = await _make_cohort(db)

    resp = await client.post(
        f"/sessions/cohorts/{cohort.id}/registrations",
        json={
            "student_name": "Desk Student With Parent",
            "email": "desk.withparent@example.com",
            "phone": "050 444 5555",
            "parent_name": "Desk Parent",
            "parent_phone": "050 666 7777",
        },
        headers=operations_headers,
    )
    assert resp.status_code == 201, resp.text

    student = (await db.execute(
        select(Contact).where(Contact.email == "desk.withparent@example.com")
    )).scalars().first()

    guardian = (await db.execute(
        select(Contact).where(Contact.contact_roles.any("parent_guardian"))
    )).scalars().first()
    assert guardian is not None
    assert guardian.full_name == "Desk Parent"

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
async def test_desk_register_without_parent_info_has_no_payer(db, client, operations_headers):
    cohort = await _make_cohort(db)

    resp = await client.post(
        f"/sessions/cohorts/{cohort.id}/registrations",
        json={
            "student_name": "No Parent Info",
            "email": "no.parent.desk@example.com",
            "phone": "050 888 9999",
        },
        headers=operations_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["payer_contact_id"] is None


@pytest.mark.asyncio
async def test_desk_register_requires_operations_role(db, client, other_role_headers):
    cohort = await _make_cohort(db)
    resp = await client.post(
        f"/sessions/cohorts/{cohort.id}/registrations",
        json={
            "student_name": "Blocked",
            "email": "blocked@example.com",
            "phone": "0501112222",
        },
        headers=other_role_headers,
    )
    assert resp.status_code == 403


# ── Registrations list ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_registrations_shows_student_and_guardian_and_flags(db, client, operations_headers):
    cohort = await _make_cohort(db)
    student = _new_contact(
        full_name="Registration Student", primary_phone_e164="+971500000001", email="registration.student@example.com",
    )
    guardian = _new_contact(
        full_name="Registration Guardian", contact_roles=["parent_guardian"], primary_phone_e164="+971500000002",
    )
    db.add_all([student, guardian])
    await db.flush()

    registration = await register(
        db, contact_id=student.id, cohort_id=cohort.id, payer_contact_id=guardian.id, registered_via="desk",
    )
    await db.commit()

    resp = await client.get(f"/sessions/cohorts/{cohort.id}/registrations", headers=operations_headers)
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == str(registration.id)
    assert row["student_name"] == "Registration Student"
    assert row["student_phone"] == "+971500000001"
    assert row["guardian_name"] == "Registration Guardian"
    assert row["guardian_phone"] == "+971500000002"
    assert row["ticket_sent"] is False
    assert row["checked_in"] is False
    assert row["payment_status"] == "waived"  # free program
    assert row["certificate_url"] is None


@pytest.mark.asyncio
async def test_list_registrations_reports_last_login_at_of_the_linked_account(db, client, operations_headers):
    """2026-09-16 — resolved contact_id-first, email-fallback, same as
    get_or_create_student_account. A registrant with no LMS account at all,
    one with an account nobody's ever logged into, and one who's actually
    logged in should all read differently."""
    from app.models.user import User

    cohort = await _make_cohort(db)
    no_account = _new_contact(full_name="No Account Yet", email="no-account@example.com")
    never_logged_in = _new_contact(full_name="Never Logged In", email="never-logged-in@example.com")
    has_logged_in = _new_contact(full_name="Has Logged In", email="has-logged-in@example.com")
    db.add_all([no_account, never_logged_in, has_logged_in])
    await db.flush()

    from datetime import datetime, timezone
    login_time = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    db.add(User(
        id=uuid.uuid4(), full_name="Never Logged In", email=never_logged_in.email, password_hash="x",
        roles=["student"], status="active", contact_id=never_logged_in.id, must_change_password=False,
    ))
    # Resolved by email fallback, not contact_id — the account predates the
    # link, same gap get_or_create_student_account's own fallback covers.
    db.add(User(
        id=uuid.uuid4(), full_name="Has Logged In", email=has_logged_in.email, password_hash="x",
        roles=["student"], status="active", contact_id=None, must_change_password=False,
        last_login_at=login_time,
    ))
    await db.flush()

    for contact in (no_account, never_logged_in, has_logged_in):
        await register(db, contact_id=contact.id, cohort_id=cohort.id, registered_via="desk")
    await db.commit()

    resp = await client.get(f"/sessions/cohorts/{cohort.id}/registrations", headers=operations_headers)
    assert resp.status_code == 200, resp.text
    by_name = {r["student_name"]: r["last_login_at"] for r in resp.json()}
    assert by_name["No Account Yet"] is None
    assert by_name["Never Logged In"] is None
    assert by_name["Has Logged In"] is not None
    assert by_name["Has Logged In"].startswith("2026-09-01")


@pytest.mark.asyncio
async def test_list_registrations_requires_operations_role(db, client, other_role_headers):
    cohort = await _make_cohort(db)
    resp = await client.get(f"/sessions/cohorts/{cohort.id}/registrations", headers=other_role_headers)
    assert resp.status_code == 403


# ── Set-password link ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_set_password_link_returns_a_usable_token(db, client, operations_headers):
    from app.core.config import settings
    from app.core.security import decode_password_set_token
    from app.models.user import User

    cohort = await _make_cohort(db)
    contact = _new_contact(full_name="Needs A Password", email="needs-password@example.com")
    db.add(contact)
    await db.flush()
    user = User(
        id=uuid.uuid4(), full_name="Needs A Password", email=contact.email, password_hash="x",
        roles=["student"], status="active", contact_id=contact.id, must_change_password=True,
    )
    db.add(user)
    registration = await register(db, contact_id=contact.id, cohort_id=cohort.id, registered_via="desk")
    await db.commit()

    resp = await client.post(
        f"/sessions/registrations/{registration.id}/set-password-link", headers=operations_headers,
    )
    assert resp.status_code == 200, resp.text
    link = resp.json()["link"]
    assert link.startswith(f"{settings.FRONTEND_URL}/learn/set-password?token=")
    token = link.split("token=", 1)[1]
    assert decode_password_set_token(token) == str(user.id)


@pytest.mark.asyncio
async def test_get_set_password_link_404s_without_a_linked_account(db, client, operations_headers):
    cohort = await _make_cohort(db)
    contact = _new_contact(full_name="No Account Here")
    db.add(contact)
    await db.flush()
    registration = await register(db, contact_id=contact.id, cohort_id=cohort.id, registered_via="desk")
    await db.commit()

    resp = await client.post(
        f"/sessions/registrations/{registration.id}/set-password-link", headers=operations_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_set_password_link_requires_operations_role(db, client, other_role_headers):
    cohort = await _make_cohort(db)
    contact = _new_contact(full_name="Irrelevant")
    db.add(contact)
    await db.flush()
    registration = await register(db, contact_id=contact.id, cohort_id=cohort.id, registered_via="desk")
    await db.commit()

    resp = await client.post(
        f"/sessions/registrations/{registration.id}/set-password-link", headers=other_role_headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_registrations_includes_certificate_url_when_issued(db, client, operations_headers):
    from app.models.certificate import Certificate
    from app.models.enums import CertificateType

    cohort = await _make_cohort(db)
    student = _new_contact(full_name="Certified Student")
    db.add(student)
    await db.flush()
    registration = await register(db, contact_id=student.id, cohort_id=cohort.id, registered_via="desk")
    registration.status = "completed"
    db.add(Certificate(
        id=uuid.uuid4(), contact_id=student.id, registration_id=registration.id,
        type=CertificateType.student_completion, workshop_name=cohort.name,
        file_url="https://example.test/cert.pdf", bucket=None, file_path=None,
    ))
    await db.commit()

    resp = await client.get(f"/sessions/cohorts/{cohort.id}/registrations", headers=operations_headers)
    assert resp.status_code == 200, resp.text
    row = resp.json()[0]
    assert row["certificate_url"] == "https://example.test/cert.pdf"


@pytest.mark.asyncio
async def test_student_certificate_is_reported_issued_without_a_url(db, client, operations_headers):
    """Student completion certs are emailed, never stored, so they have a row
    and no file. The list keyed "has a certificate" off certificate_url, which
    made every one of them invisible to ops — certificate_issued is the flag."""
    from app.models.certificate import Certificate
    from app.models.enums import CertificateType

    cohort = await _make_cohort(db)
    student = _new_contact(full_name="Emailed Cert Student")
    db.add(student)
    await db.flush()
    registration = await register(db, contact_id=student.id, cohort_id=cohort.id, registered_via="desk")
    db.add(Certificate(
        id=uuid.uuid4(), contact_id=student.id, registration_id=registration.id,
        type=CertificateType.student_completion, workshop_name=cohort.name,
        file_url=None, bucket=None, file_path=None,
    ))
    await db.commit()

    resp = await client.get(f"/sessions/cohorts/{cohort.id}/registrations", headers=operations_headers)
    assert resp.status_code == 200, resp.text
    row = resp.json()[0]
    assert row["certificate_issued"] is True
    assert row["certificate_url"] is None


@pytest.mark.asyncio
async def test_registration_without_a_certificate_reports_not_issued(db, client, operations_headers):
    cohort = await _make_cohort(db)
    student = _new_contact(full_name="No Cert Student")
    db.add(student)
    await db.flush()
    await register(db, contact_id=student.id, cohort_id=cohort.id, registered_via="desk")
    await db.commit()

    resp = await client.get(f"/sessions/cohorts/{cohort.id}/registrations", headers=operations_headers)
    assert resp.json()[0]["certificate_issued"] is False


# ── Ticket / payment / cancel actions ────────────────────────────────────────

@pytest.mark.asyncio
async def test_resend_ticket_enqueues_job(db, arq_client, operations_headers, arq_redis):
    cohort = await _make_cohort(db)
    contact = _new_contact()
    db.add(contact)
    await db.flush()
    registration = await register(db, contact_id=contact.id, cohort_id=cohort.id, registered_via="desk")
    await db.commit()

    # Nothing queued yet — register() itself doesn't enqueue (only the router
    # endpoints do), so the queue should be empty before we call resend.
    assert await arq_redis.zrange("arq:queue", 0, -1) == []

    resp = await arq_client.post(f"/sessions/registrations/{registration.id}/resend-ticket", headers=operations_headers)
    assert resp.status_code == 200, resp.text

    queued_jobs = await arq_redis.zrange("arq:queue", 0, -1)
    assert len(queued_jobs) == 1


@pytest.mark.asyncio
async def test_resend_ticket_missing_registration_404(db, client, operations_headers):
    resp = await client.post(f"/sessions/registrations/{uuid.uuid4()}/resend-ticket", headers=operations_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cancel_registration(db, client, operations_headers):
    cohort = await _make_cohort(db)
    contact = _new_contact()
    db.add(contact)
    await db.flush()
    registration = await register(db, contact_id=contact.id, cohort_id=cohort.id, registered_via="desk")
    await db.commit()

    resp = await client.post(f"/sessions/registrations/{registration.id}/cancel", headers=operations_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "cancelled"

    await db.refresh(registration)
    assert registration.status == "cancelled"


@pytest.mark.asyncio
async def test_give_certificate_overrides_below_threshold(db, client, operations_headers):
    """Manual override (operator request 2026-07-25) — ops can hand a
    certificate to a student who never met the program's completion rule."""
    cohort = await _make_cohort(db)
    contact = _new_contact(full_name="Manual Override Student")
    db.add(contact)
    await db.flush()
    registration = await register(db, contact_id=contact.id, cohort_id=cohort.id, registered_via="desk")
    await db.commit()

    resp = await client.post(f"/sessions/registrations/{registration.id}/certificate", headers=operations_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "completed"
    # Student completion certs are emailed as a PDF attachment and never
    # uploaded to storage (see _issue_student_certificate), so there is no URL
    # to hand back — only the issued certificate's id. This assertion used to
    # expect a certificate_url, left over from the earlier store-the-file
    # design that migration f9c2e08b0012 (file_url nullable) superseded.
    assert body["certificate_id"]

    await db.refresh(registration)
    assert registration.status == "completed"


@pytest.mark.asyncio
async def test_give_certificate_requires_operations(db, client, other_role_headers):
    resp = await client.post(f"/sessions/registrations/{uuid.uuid4()}/certificate", headers=other_role_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_give_certificate_missing_registration_404(db, client, operations_headers):
    resp = await client.post(f"/sessions/registrations/{uuid.uuid4()}/certificate", headers=operations_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_confirm_payment(db, client, operations_headers):
    cohort = await _make_cohort(db)
    contact = _new_contact()
    db.add(contact)
    await db.flush()
    registration = await register(db, contact_id=contact.id, cohort_id=cohort.id, registered_via="desk")
    await db.commit()

    resp = await client.post(
        f"/sessions/registrations/{registration.id}/confirm-payment",
        json={"amount": "150.00", "status": "paid"},
        headers=operations_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["payment_status"] == "paid"

    await db.refresh(registration)
    assert registration.payment_status == "paid"
    assert float(registration.price_charged) == 150.00


@pytest.mark.asyncio
async def test_confirm_payment_supports_partial(db, client, operations_headers):
    cohort = await _make_cohort(db)
    contact = _new_contact()
    db.add(contact)
    await db.flush()
    registration = await register(db, contact_id=contact.id, cohort_id=cohort.id, registered_via="desk")
    await db.commit()

    resp = await client.post(
        f"/sessions/registrations/{registration.id}/confirm-payment",
        json={"amount": "50.00", "status": "partial"},
        headers=operations_headers,
    )
    assert resp.status_code == 200, resp.text

    await db.refresh(registration)
    assert registration.payment_status == "partial"

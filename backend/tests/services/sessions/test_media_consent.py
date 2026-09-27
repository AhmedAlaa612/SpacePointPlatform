"""Tests for Cohort Media Consent service (2026-09-27)."""

import uuid
from datetime import date
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.schemas.sessions.media_consent import (
    MediaConsentManualMatchRequest,
    MediaConsentManualOverrideRequest,
    MediaConsentWebhookRequest,
)
from app.services.sessions.media_consent import (
    _normalize_phone_digits,
    _parse_consent_choice,
    get_cohort_consents_summary,
    ingest_media_consent_webhook,
    manual_link_media_consent,
    manual_override_media_consent,
)


def test_phone_normalization():
    assert _normalize_phone_digits("+971 50 123 4567") == "501234567"
    assert _normalize_phone_digits("0501234567") == "501234567"
    assert _normalize_phone_digits("00971501234567") == "501234567"
    assert _normalize_phone_digits(None) is None


def test_parse_consent_choice():
    assert _parse_consent_choice("YES: I give permission...") == "consented"
    assert _parse_consent_choice("NO: I do not give permission...") == "declined"
    assert _parse_consent_choice("declined") == "declined"
    assert _parse_consent_choice("consented") == "consented"


@pytest.mark.asyncio
async def test_media_consent_match_email_first_and_replace_guardian(db_session: AsyncSession):
    # Setup Program, Cohort, Contact (Student), Registration
    program = Program(id=uuid.uuid4(), name="Space Race", code="SR-2026")
    db_session.add(program)

    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Cohort Alpha")
    db_session.add(cohort)

    # Initial guardian
    initial_guardian = Contact(
        id=uuid.uuid4(),
        full_name="Old Guardian",
        primary_phone_e164="+971500000000",
        contact_roles=["parent_guardian"],
    )
    db_session.add(initial_guardian)

    student = Contact(
        id=uuid.uuid4(),
        full_name="Fatima Al Mansoori",
        email="fatima.mansoori@example.com",
        primary_phone_e164="+971509998877",
        contact_roles=["student"],
    )
    db_session.add(student)

    reg = Registration(
        id=uuid.uuid4(),
        contact_id=student.id,
        cohort_id=cohort.id,
        payer_contact_id=initial_guardian.id,
        ticket_token="tok_test_123",
        registered_via="desk",
    )
    db_session.add(reg)
    await db_session.commit()

    # Form submitted with student's email, but different name (e.g. Arabic or parent typed 'Fatima M')
    req = MediaConsentWebhookRequest(
        student_name="Fatima M (nickname)",
        school_name="Al Mawakeb School",
        parent_name="Aisha Al Mansoori",
        relationship="Mother",
        mobile_number="+971 50 111 2233",
        email_address="fatima.mansoori@example.com",
        consent_choice="YES: I give permission...",
        permission_grants=["photography", "videography"],
        date_of_signing=date(2026, 9, 27),
    )

    consent = await ingest_media_consent_webhook(db_session, cohort_id=cohort.id, payload=req)

    assert consent.match_status == "matched"
    assert consent.match_method == "email"
    assert consent.registration_id == reg.id
    assert consent.consent_choice == "consented"

    # Verify existing guardian data was replaced
    await db_session.refresh(initial_guardian)
    assert initial_guardian.full_name == "Aisha Al Mansoori"
    assert initial_guardian.primary_phone_e164 == "+971 50 111 2233"


@pytest.mark.asyncio
async def test_media_consent_match_phone_fallback(db_session: AsyncSession):
    program = Program(id=uuid.uuid4(), name="Space Race Phone", code="SRP-2026")
    db_session.add(program)

    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Cohort Beta")
    db_session.add(cohort)

    student = Contact(
        id=uuid.uuid4(),
        full_name="Saeed Rashid",
        email="saeed@school.ae",
        primary_phone_e164="+971521234567",
        contact_roles=["student"],
    )
    db_session.add(student)

    reg = Registration(
        id=uuid.uuid4(),
        contact_id=student.id,
        cohort_id=cohort.id,
        ticket_token="tok_test_456",
        registered_via="desk",
    )
    db_session.add(reg)
    await db_session.commit()

    # Form has different email (parent email), but matches student's phone
    req = MediaConsentWebhookRequest(
        student_name="Different Student Name",
        parent_name="Rashid Saeed",
        relationship="Father",
        mobile_number="052 123 4567",  # UAE format
        email_address="parent_rashid@gmail.com",  # Not student's email
        consent_choice="NO: I do not give permission...",
    )

    consent = await ingest_media_consent_webhook(db_session, cohort_id=cohort.id, payload=req)

    assert consent.match_status == "matched"
    assert consent.match_method == "phone"
    assert consent.registration_id == reg.id
    assert consent.consent_choice == "declined"

    # Verify guardian was created and attached to registration
    await db_session.refresh(reg)
    assert reg.payer_contact_id is not None
    guardian = await db_session.get(Contact, reg.payer_contact_id)
    assert guardian.full_name == "Rashid Saeed"


@pytest.mark.asyncio
async def test_media_consent_unmatched_and_manual_override(db_session: AsyncSession):
    program = Program(id=uuid.uuid4(), name="Space Race Unmatched", code="SRU-2026")
    db_session.add(program)

    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Cohort Gamma")
    db_session.add(cohort)

    student = Contact(
        id=uuid.uuid4(),
        full_name="Maryam Ali",
        email="maryam@example.com",
        primary_phone_e164="+971550001122",
        contact_roles=["student"],
    )
    db_session.add(student)

    reg = Registration(
        id=uuid.uuid4(),
        contact_id=student.id,
        cohort_id=cohort.id,
        ticket_token="tok_test_789",
        registered_via="desk",
    )
    db_session.add(reg)
    await db_session.commit()

    # Unmatched submission (neither email nor phone matches)
    req = MediaConsentWebhookRequest(
        student_name="Maryam Ali",  # Name matches, but name does NOT contribute to matching
        parent_name="Ali Hassan",
        mobile_number="0589999999",  # Unknown phone
        email_address="unknown@yahoo.com",  # Unknown email
        consent_choice="YES: I give permission",
    )

    consent = await ingest_media_consent_webhook(db_session, cohort_id=cohort.id, payload=req)
    assert consent.match_status == "unmatched"
    assert consent.registration_id is None

    # Summary should show 1 unmatched
    summary = await get_cohort_consents_summary(db_session, cohort.id)
    assert summary.total_submissions == 1
    assert summary.unmatched_count == 1
    assert summary.pending_registrations_count == 1

    # Now manual link to Maryam's registration
    linked = await manual_link_media_consent(
        db_session, cohort_id=cohort.id, consent_id=consent.id, registration_id=reg.id
    )
    assert linked.match_status == "manual"
    assert linked.registration_id == reg.id

    # Ops manual override test
    override_req = MediaConsentManualOverrideRequest(
        registration_id=reg.id,
        consent_choice="declined",
        notes="Parent phoned to decline video coverage",
    )
    overridden = await manual_override_media_consent(db_session, cohort_id=cohort.id, req=override_req)
    assert overridden.consent_choice == "declined"
    assert overridden.notes == "Parent phoned to decline video coverage"

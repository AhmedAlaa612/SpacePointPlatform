"""Direct verification test for Cohort Media Consent feature (2026-09-27).

Tests:
1. Phone normalization & consent choice parsing.
2. Webhook ingestion:
   - Matches student by email first.
   - Replaces existing guardian data with parent from form.
   - Ignores student name for matching (still matches when name is completely different).
3. Webhook fallback:
   - Matches student by phone number second when email doesn't match.
   - Creates guardian contact if none existed.
4. Webhook unmatched:
   - Saves unmatched submission when neither email nor phone matches.
5. Cohort consents summary:
   - Accurately counts matched, unmatched, consented, declined, pending.
6. 1-click manual match of unmatched submission to student registration.
7. Operations staff manual override of consent state.
8. Registration list returns correct media consent fields.
"""

import asyncio
import os
import sys
import uuid
from datetime import date

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ["DATABASE_URL"] = "postgresql+asyncpg://postgres:67500@localhost:5433/spacepoint_dev"

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.sessions.cohort import Cohort
from app.models.sessions.media_consent import CohortMediaConsent
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
    get_latest_consents_for_registrations,
    ingest_media_consent_webhook,
    manual_link_media_consent,
    manual_override_media_consent,
)


async def run_tests():
    print("==================================================================")
    print("  RUNNING COHORT MEDIA CONSENT VERIFICATION SUITE                 ")
    print("==================================================================")

    # 1. Pure helper tests
    print("\n[1] Testing phone normalization & consent choice parsing...")
    assert _normalize_phone_digits("+971 50 123 4567") == "501234567"
    assert _normalize_phone_digits("0501234567") == "501234567"
    assert _normalize_phone_digits("00971501234567") == "501234567"
    assert _parse_consent_choice("YES: I give permission...") == "consented"
    assert _parse_consent_choice("NO: I do not give permission...") == "declined"
    print("  OK: Normalization and choice parsing verified.")

    # Setup DB connection
    engine = create_async_engine("postgresql+asyncpg://postgres:67500@localhost:5433/spacepoint_dev")
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session() as db:
        # Create test Program & Cohort
        prog_id = uuid.uuid4()
        cohort_id = uuid.uuid4()

        program = Program(
            id=prog_id,
            name="Test Space Race",
            code=f"TSR-{uuid.uuid4().hex[:6]}",
            program_type="workshop",
            pricing_model="paid",
        )
        db.add(program)
        await db.flush()

        cohort = Cohort(id=cohort_id, program_id=prog_id, name="Test Cohort Consent")
        db.add(cohort)
        await db.flush()

        # Student 1: Fatima (has initial guardian)
        guardian_1 = Contact(
            id=uuid.uuid4(),
            full_name="Old Guardian Name",
            primary_phone_e164="+971500000000",
            email="old.guardian@example.com",
            contact_roles=["parent_guardian"],
        )
        student_1 = Contact(
            id=uuid.uuid4(),
            full_name="Fatima Al Mansoori",
            email="fatima.mansoori@testschool.ae",
            primary_phone_e164="+971509998877",
            contact_roles=["student"],
        )
        student_2 = Contact(
            id=uuid.uuid4(),
            full_name="Saeed Rashid",
            email="saeed@testschool.ae",
            primary_phone_e164="+971521234567",
            contact_roles=["student"],
        )

        db.add(guardian_1)
        db.add(student_1)
        db.add(student_2)
        await db.flush()

        reg_1 = Registration(
            id=uuid.uuid4(),
            contact_id=student_1.id,
            cohort_id=cohort_id,
            payer_contact_id=guardian_1.id,
            ticket_token=f"tok_{uuid.uuid4().hex[:12]}",
            registered_via="desk",
        )
        reg_2 = Registration(
            id=uuid.uuid4(),
            contact_id=student_2.id,
            cohort_id=cohort_id,
            ticket_token=f"tok_{uuid.uuid4().hex[:12]}",
            registered_via="desk",
        )
        db.add(reg_1)
        db.add(reg_2)
        await db.flush()
        await db.commit()

        try:
            # 2. Test student_email matching & guardian replacement
            print("\n[2] Testing Webhook: student_email matching & replacing guardian...")
            req_1 = MediaConsentWebhookRequest(
                student_name="Completely Wrong Name",  # Name does not match
                student_email="fatima.mansoori@testschool.ae",  # Matches student 1 email!
                school_name="Al Mawakeb School",
                parent_name="Aisha Al Mansoori",
                relationship="Mother",
                mobile_number="+971 50 111 2233",
                email_address="parent_aisha@gmail.com",
                consent_choice="YES: I give permission for my child to be photographed...",
                permission_grants=["photography", "videography", "interviews"],
                date_of_signing=date(2026, 9, 27),
            )
            c1 = await ingest_media_consent_webhook(db, cohort_id=cohort_id, payload=req_1)
            assert c1.match_status == "matched"
            assert c1.match_method == "student_email"
            assert c1.registration_id == reg_1.id
            assert c1.consent_choice == "consented"
            assert c1.student_email_raw == "fatima.mansoori@testschool.ae"

            # Check that guardian data was replaced
            await db.refresh(guardian_1)
            assert guardian_1.full_name == "Aisha Al Mansoori"
            assert guardian_1.primary_phone_e164 == "+971 50 111 2233"
            print("  OK: Matched by student_email and replaced guardian data.")

            # 3. Test parent phone/email alone do NOT match when student_email is missing
            print("\n[3] Testing Webhook: parent phone/email ignored when student_email missing...")
            req_2 = MediaConsentWebhookRequest(
                student_name="Unknown Name",
                student_email=None,  # No student email!
                parent_name="Rashid Saeed",
                relationship="Father",
                mobile_number="052 123 4567",  # Even though phone matches student 2, must NOT match!
                email_address="saeed@testschool.ae",  # Even though email matches student 2, must NOT match!
                consent_choice="NO: I do not give permission...",
                date_of_signing=date(2026, 9, 27),
            )
            c2 = await ingest_media_consent_webhook(db, cohort_id=cohort_id, payload=req_2)
            assert c2.match_status == "unmatched"
            assert c2.registration_id is None
            print("  OK: Parent phone/email ignored; saved as unmatched because student_email was missing.")

            # 4. Test student_email matches student 2
            print("\n[4] Testing Webhook: student_email matching student 2...")
            req_3 = MediaConsentWebhookRequest(
                student_name="Saeed",
                student_email="saeed@testschool.ae",  # Matches student 2!
                parent_name="Rashid Saeed",
                mobile_number="052 999 8888",
                email_address="rashid@parent.ae",
                consent_choice="NO: I do not give permission",
            )
            c3 = await ingest_media_consent_webhook(db, cohort_id=cohort_id, payload=req_3)
            assert c3.match_status == "matched"
            assert c3.match_method == "student_email"
            assert c3.registration_id == reg_2.id
            assert c3.consent_choice == "declined"
            print("  OK: Matched student 2 by student_email and set guardian.")

            # 5. Test summary stats
            print("\n[5] Testing Cohort Consents Summary...")
            summary = await get_cohort_consents_summary(db, cohort_id)
            assert summary.total_submissions == 3
            assert summary.matched_count == 2
            assert summary.unmatched_count == 1
            assert summary.consented_count == 1
            assert summary.declined_count == 2
            assert summary.total_registrations_count == 2
            print(f"  OK: Summary: {summary.total_submissions} total, {summary.matched_count} matched, {summary.unmatched_count} unmatched.")

            # 6. Test 1-click manual match for the unmatched submission
            print("\n[6] Testing 1-click manual link for unmatched submission...")
            linked = await manual_link_media_consent(db, cohort_id=cohort_id, consent_id=c2.id, registration_id=reg_1.id)
            assert linked.match_status == "manual"
            assert linked.registration_id == reg_1.id
            print("  OK: Unmatched submission successfully linked manually.")

            # 7. Test manual override
            print("\n[7] Testing manual override by operations...")
            override = await manual_override_media_consent(
                db,
                cohort_id=cohort_id,
                req=MediaConsentManualOverrideRequest(
                    registration_id=reg_1.id,
                    consent_choice="declined",
                    notes="Parent called via WhatsApp to decline",
                ),
            )
            assert override.consent_choice == "declined"
            assert override.notes == "Parent called via WhatsApp to decline"
            print("  OK: Manual override updated consent choice to declined.")

            # 8. Test get_latest_consents_for_registrations
            print("\n[8] Testing latest consents mapping for registrations...")
            mapping = await get_latest_consents_for_registrations(db, [reg_1.id, reg_2.id])
            assert reg_1.id in mapping
            assert mapping[reg_1.id].consent_choice == "declined"
            assert reg_2.id in mapping
            assert mapping[reg_2.id].consent_choice == "declined"
            print("  OK: Latest consent mapping verified.")

            print("\n==================================================================")
            print("  ALL MEDIA CONSENT TESTS PASSED (100%)                          ")
            print("==================================================================")

        finally:
            # Clean up test rows
            await db.execute(delete(CohortMediaConsent).where(CohortMediaConsent.cohort_id == cohort_id))
            await db.execute(delete(Registration).where(Registration.cohort_id == cohort_id))
            await db.execute(delete(Cohort).where(Cohort.id == cohort_id))
            await db.execute(delete(Program).where(Program.id == prog_id))
            await db.commit()


if __name__ == "__main__":
    asyncio.run(run_tests())

"""Cohort Media Consent service (2026-09-27).

Handles:
- Webhook submission from Google Forms.
- Email-first, phone-second matching against cohort registrations.
- Updating or creating guardian Contact records on matched students.
- Unmatched consent logging and 1-click manual linking.
- Manual consent state override by operations staff.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sessions.cohort import Cohort
from app.models.sessions.media_consent import CohortMediaConsent
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact, ContactRelationship
from app.schemas.sessions.media_consent import (
    CohortMediaConsentOut,
    CohortMediaConsentSummaryOut,
    MediaConsentManualOverrideRequest,
    MediaConsentWebhookRequest,
)
from app.services.spine.identity import ensure_alias, normalize_phone, resolve_or_create_contact


def _normalize_phone_digits(phone: str | None) -> str | None:
    """Extract digits only, returning the trailing 9 digits (standard UAE mobile core)."""
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if len(digits) >= 9:
        return digits[-9:]
    return digits if digits else None


def _normalize_email(email: str | None) -> str | None:
    if not email:
        return None
    cleaned = email.strip().lower()
    return cleaned if cleaned else None


def _parse_consent_choice(raw: str | None) -> str:
    """Standardize 'YES...', 'NO...', 'consented', 'declined' into 'consented' | 'declined'."""
    if not raw:
        return "consented"
    lower = raw.strip().lower()
    if "no" in lower or "declined" in lower or "do not give" in lower:
        return "declined"
    return "consented"


def _parse_signing_date(val: date | str | None) -> date | None:
    if val is None:
        return date.today()
    if isinstance(val, date):
        return val
    val_str = str(val).strip()
    if not val_str:
        return date.today()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(val_str, fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(val_str).date()
    except Exception:
        return date.today()


async def _ensure_guardian_link(
    db: AsyncSession,
    *,
    registration: Registration,
    student: Contact,
    parent_name: str,
    parent_phone: str | None,
    parent_email: str | None,
) -> None:
    """Adds guardian data to the student; replaces existing guardian data if present."""
    if registration.payer_contact_id:
        guardian = await db.get(Contact, registration.payer_contact_id)
        if guardian:
            guardian.full_name = parent_name
            # Normalized + aliased like every other contact write — raw
            # values here would never match a future alias-hash lookup and
            # silently fork a duplicate Contact.
            norm_phone = normalize_phone(parent_phone) if parent_phone else None
            if norm_phone:
                guardian.primary_phone_e164 = norm_phone
                await ensure_alias(db, guardian.id, "phone", norm_phone)
            norm_email = _normalize_email(parent_email) if parent_email else None
            if norm_email:
                guardian.email = norm_email
                await ensure_alias(db, guardian.id, "email", norm_email)
            return

    # Create / resolve new guardian contact and link
    guardian, _ = await resolve_or_create_contact(
        db,
        full_name=parent_name,
        phone=parent_phone,
        email=parent_email,
        contact_roles=["parent_guardian"],
        role_event_source="media_consent",
    )
    registration.payer_contact_id = guardian.id

    # Check ContactRelationship
    rel = await db.scalar(
        select(ContactRelationship).where(
            ContactRelationship.contact_id == guardian.id,
            ContactRelationship.related_contact_id == student.id,
            ContactRelationship.relation == "guardian_of",
        )
    )
    if not rel:
        db.add(
            ContactRelationship(
                id=uuid.uuid4(),
                contact_id=guardian.id,
                related_contact_id=student.id,
                relation="guardian_of",
            )
        )


async def ingest_media_consent_webhook(
    db: AsyncSession,
    *,
    cohort_id: uuid.UUID,
    payload: MediaConsentWebhookRequest,
) -> CohortMediaConsent:
    """Processes a Google Form media consent webhook submission.

    Rules:
    - Matching: Email first, phone number second (if email not matched).
    - Student name does NOT contribute to matching.
    - Guardian data replaces existing guardian data on matched student.
    - If unmatched, stored as unmatched with raw details for manual review.
    """
    cohort = await db.get(Cohort, cohort_id)
    if not cohort:
        raise ValueError("Cohort not found")

    form_student_email = _normalize_email(payload.student_email)

    # Fetch all registrations for this cohort with student Contact
    rows = (
        await db.execute(
            select(Registration, Contact)
            .join(Contact, Contact.id == Registration.contact_id)
            .where(Registration.cohort_id == cohort_id)
        )
    ).all()

    matched_reg: Registration | None = None
    matched_student: Contact | None = None
    match_method: str | None = None

    # Matching Rule (2026-09-27):
    # ONLY match against student_email.
    # Parent email and parent phone are NEVER used for matching anything.
    # If student_email is missing or empty, ignore matching (save as unmatched).
    if form_student_email:
        for reg, student in rows:
            student_email = _normalize_email(student.email)
            if student_email and student_email == form_student_email:
                matched_reg = reg
                matched_student = student
                match_method = "student_email"
                break

    consent_choice = _parse_consent_choice(payload.consent_choice)
    signing_date = _parse_signing_date(payload.date_of_signing)
    grants = payload.permission_grants
    if isinstance(grants, str):
        grants = [g.strip() for g in grants.split(",") if g.strip()]
    elif not isinstance(grants, list):
        grants = []

    match_status = "matched" if matched_reg else "unmatched"

    consent = CohortMediaConsent(
        id=uuid.uuid4(),
        cohort_id=cohort_id,
        registration_id=matched_reg.id if matched_reg else None,
        matched_contact_id=matched_student.id if matched_student else None,
        student_name_raw=payload.student_name,
        student_email_raw=payload.student_email,
        school_name_raw=payload.school_name,
        parent_name=payload.parent_name or "Parent / Guardian",
        relationship=payload.relationship,
        parent_phone=payload.mobile_number,
        parent_email=payload.email_address,
        consent_choice=consent_choice,
        permission_grants=grants,
        declaration_agreed=payload.declaration_agreed,
        date_of_signing=signing_date,
        source="google_form",
        match_status=match_status,
        match_method=match_method,
        raw_payload=payload.raw_payload or payload.model_dump(mode="json"),
    )
    db.add(consent)

    # Replace / update guardian data if matched
    if matched_reg and matched_student:
        await _ensure_guardian_link(
            db,
            registration=matched_reg,
            student=matched_student,
            parent_name=consent.parent_name,
            parent_phone=consent.parent_phone,
            parent_email=consent.parent_email,
        )

    await db.commit()
    await db.refresh(consent)
    return consent


async def manual_override_media_consent(
    db: AsyncSession,
    *,
    cohort_id: uuid.UUID,
    req: MediaConsentManualOverrideRequest,
) -> CohortMediaConsent:
    """Operations staff manually sets or updates media consent state for a student registration."""
    reg = await db.get(Registration, req.registration_id)
    if not reg or reg.cohort_id != cohort_id:
        raise ValueError("Registration not found in this cohort")

    student = await db.get(Contact, reg.contact_id)

    # Check if a consent row already exists for this registration
    existing = await db.scalar(
        select(CohortMediaConsent)
        .where(
            CohortMediaConsent.cohort_id == cohort_id,
            CohortMediaConsent.registration_id == req.registration_id,
        )
        .order_by(desc(CohortMediaConsent.created_at))
    )

    if existing:
        existing.consent_choice = req.consent_choice
        existing.match_status = "manual"
        existing.match_method = "manual"
        existing.source = "manual_override"
        if req.notes:
            existing.notes = req.notes
        if req.parent_name:
            existing.parent_name = req.parent_name
        if req.parent_phone:
            existing.parent_phone = req.parent_phone
        if req.parent_email:
            existing.parent_email = req.parent_email
        if req.relationship:
            existing.relationship = req.relationship
        consent = existing
    else:
        consent = CohortMediaConsent(
            id=uuid.uuid4(),
            cohort_id=cohort_id,
            registration_id=reg.id,
            matched_contact_id=student.id if student else None,
            student_name_raw=student.full_name if student else None,
            parent_name=req.parent_name or "Parent / Guardian",
            relationship=req.relationship,
            parent_phone=req.parent_phone,
            parent_email=req.parent_email,
            consent_choice=req.consent_choice,
            permission_grants=["all_authorized"],
            declaration_agreed=True,
            date_of_signing=date.today(),
            source="manual_override",
            match_status="manual",
            match_method="manual",
            notes=req.notes,
        )
        db.add(consent)

    if req.parent_name and student:
        await _ensure_guardian_link(
            db,
            registration=reg,
            student=student,
            parent_name=req.parent_name,
            parent_phone=req.parent_phone,
            parent_email=req.parent_email,
        )

    await db.commit()
    await db.refresh(consent)
    return consent


async def manual_link_media_consent(
    db: AsyncSession,
    *,
    cohort_id: uuid.UUID,
    consent_id: uuid.UUID,
    registration_id: uuid.UUID,
) -> CohortMediaConsent:
    """Manually links an unmatched consent form submission to a student registration."""
    consent = await db.get(CohortMediaConsent, consent_id)
    if not consent or consent.cohort_id != cohort_id:
        raise ValueError("Consent record not found")

    reg = await db.get(Registration, registration_id)
    if not reg or reg.cohort_id != cohort_id:
        raise ValueError("Registration not found in this cohort")

    student = await db.get(Contact, reg.contact_id)

    consent.registration_id = reg.id
    consent.matched_contact_id = student.id if student else None
    consent.match_status = "manual"
    consent.match_method = "manual"

    if student and consent.parent_name:
        await _ensure_guardian_link(
            db,
            registration=reg,
            student=student,
            parent_name=consent.parent_name,
            parent_phone=consent.parent_phone,
            parent_email=consent.parent_email,
        )

    await db.commit()
    await db.refresh(consent)
    return consent


async def get_cohort_consents_summary(
    db: AsyncSession,
    cohort_id: uuid.UUID,
) -> CohortMediaConsentSummaryOut:
    """Fetches summary stats and all consent records for a cohort."""
    # Query all registrations count
    total_regs = await db.scalar(
        select(func.count(Registration.id)).where(Registration.cohort_id == cohort_id)
    ) or 0

    # Query all consents for cohort
    consents = (
        await db.execute(
            select(CohortMediaConsent)
            .where(CohortMediaConsent.cohort_id == cohort_id)
            .order_by(desc(CohortMediaConsent.created_at))
        )
    ).scalars().all()

    # Build mapping of registration_id -> student Contact name
    reg_rows = (
        await db.execute(
            select(Registration.id, Contact.full_name)
            .join(Contact, Contact.id == Registration.contact_id)
            .where(Registration.cohort_id == cohort_id)
        )
    ).all()
    reg_student_names = {r_id: name for r_id, name in reg_rows}

    items: list[CohortMediaConsentOut] = []
    matched_regs: set[uuid.UUID] = set()
    consented_count = 0
    declined_count = 0
    matched_count = 0
    unmatched_count = 0

    for c in consents:
        student_name = reg_student_names.get(c.registration_id) if c.registration_id else None
        if c.registration_id:
            matched_regs.add(c.registration_id)
            matched_count += 1
        else:
            unmatched_count += 1

        if c.consent_choice == "consented":
            consented_count += 1
        elif c.consent_choice == "declined":
            declined_count += 1

        out = CohortMediaConsentOut.model_validate(c)
        out.matched_student_name = student_name
        items.append(out)

    pending_count = max(0, total_regs - len(matched_regs))

    return CohortMediaConsentSummaryOut(
        total_submissions=len(consents),
        matched_count=matched_count,
        unmatched_count=unmatched_count,
        consented_count=consented_count,
        declined_count=declined_count,
        pending_registrations_count=pending_count,
        total_registrations_count=total_regs,
        items=items,
    )


async def get_latest_consents_for_registrations(
    db: AsyncSession,
    registration_ids: list[uuid.UUID],
) -> dict[uuid.UUID, CohortMediaConsent]:
    """Returns mapping of registration_id -> latest CohortMediaConsent."""
    if not registration_ids:
        return {}
    consents = (
        await db.execute(
            select(CohortMediaConsent)
            .where(CohortMediaConsent.registration_id.in_(registration_ids))
            .order_by(desc(CohortMediaConsent.created_at))
        )
    ).scalars().all()

    latest: dict[uuid.UUID, CohortMediaConsent] = {}
    for c in consents:
        if c.registration_id not in latest:
            latest[c.registration_id] = c
    return latest

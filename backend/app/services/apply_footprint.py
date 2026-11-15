"""Cross-platform applicant footprint lookup for admin application reviews.

Aggregates any existing User account, Spine CRM Contact, previous/other
Applications, RoleRequests, Instructor Onboarding state, and InternProfile /
internship letters matched by email (and/or user_id) so admins can review an
application with complete context and zero blind spots.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.instructors.applicant_profile import ApplicantProfile
from app.models.instructors.application_review import ApplicationReview
from app.models.internship import InternProfile, RoleRequest
from app.models.inventory.city import City
from app.models.spine.contact import Contact
from app.models.spine.organization import Organization
from app.models.user import User
from app.services import storage
from app.services.documents.card_id import format_card_id
from app.services.spine.identity import normalize_user_email, user_email_matches


async def _find_contact(
    db: AsyncSession,
    norm_email: str,
    contact_id: uuid.UUID | None,
) -> Contact | None:
    if contact_id:
        c = await db.get(Contact, contact_id)
        if c and c.merged_into_id is None:
            return c
    if not norm_email:
        return None
    return (
        await db.execute(
            select(Contact)
            .where(
                Contact.merged_into_id.is_(None),
                func.lower(func.trim(Contact.email)) == norm_email,
            )
            .order_by(Contact.created_at.desc())
        )
    ).scalars().first()


async def get_platform_footprint(
    db: AsyncSession,
    email: str | None,
    *,
    user_id: uuid.UUID | None = None,
    exclude_app_id: uuid.UUID | None = None,
    exclude_role_request_id: uuid.UUID | None = None,
    exclude_user_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Build a complete cross-platform summary for an applicant."""
    norm_email = normalize_user_email(email or "")

    user: User | None = None
    if user_id:
        user = await db.get(User, user_id)
        if user and not norm_email:
            norm_email = normalize_user_email(user.email)
    elif norm_email:
        user = (
            await db.execute(select(User).where(user_email_matches(norm_email)))
        ).scalars().first()

    effective_uid = user.id if user else None

    existing_user_out = None
    if user and user.id != exclude_user_id:
        city_name = None
        if user.city_id:
            c_row = await db.get(City, user.city_id)
            city_name = c_row.name if c_row else None
        roles_list = user.role_values
        existing_user_out = {
            "id": str(user.id),
            "full_name": user.full_name,
            "email": user.email,
            "roles": roles_list,
            "status": user.status,
            "phone": user.phone,
            "country": user.country,
            "city": city_name or user.city_other,
            "birthdate": user.birthdate.isoformat() if user.birthdate else None,
            "card_id": format_card_id(user.card_number, roles_list) if user.card_number is not None else None,
            "student_id": user.student_id,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        }

    contact = await _find_contact(db, norm_email, user.contact_id if user else None)
    contact_out = None
    if contact:
        org_name = None
        if contact.organization_id:
            org = await db.get(Organization, contact.organization_id)
            org_name = org.name_latin if org else None
        contact_out = {
            "id": str(contact.id),
            "full_name": contact.full_name,
            "contact_roles": list(contact.contact_roles or []),
            "lifecycle_stage": contact.lifecycle_stage,
            "primary_phone": contact.primary_phone_e164,
            "whatsapp": contact.whatsapp_e164,
            "country": contact.country,
            "city": contact.city,
            "nationality": contact.nationality,
            "student_id": contact.student_id,
            "organization_name": org_name,
            "notes": contact.notes,
            "created_at": contact.created_at.isoformat() if contact.created_at else None,
        }

    other_apps_out: list[dict[str, Any]] = []
    if norm_email:
        q_apps = (
            select(Application)
            .where(func.lower(func.trim(Application.email)) == norm_email)
            .order_by(Application.created_at.desc())
        )
        if exclude_app_id:
            q_apps = q_apps.where(Application.id != exclude_app_id)
        for app in (await db.execute(q_apps)).scalars().all():
            other_apps_out.append(
                {
                    "id": str(app.id),
                    "role": app.role,
                    "status": app.status,
                    "full_name": app.full_name,
                    "country": app.country,
                    "created_at": app.created_at.isoformat() if app.created_at else None,
                    "reviewed_at": app.reviewed_at.isoformat() if app.reviewed_at else None,
                    "admin_notes": app.admin_notes,
                }
            )

    role_requests_out: list[dict[str, Any]] = []
    if effective_uid:
        q_rr = (
            select(RoleRequest)
            .where(RoleRequest.requester_user_id == effective_uid)
            .order_by(RoleRequest.created_at.desc())
        )
        if exclude_role_request_id:
            q_rr = q_rr.where(RoleRequest.id != exclude_role_request_id)
        for rr in (await db.execute(q_rr)).scalars().all():
            role_requests_out.append(
                {
                    "id": str(rr.id),
                    "target_role": rr.target_role,
                    "status": rr.status,
                    "created_at": rr.created_at.isoformat() if rr.created_at else None,
                    "reviewed_at": rr.reviewed_at.isoformat() if rr.reviewed_at else None,
                    "admin_notes": rr.admin_notes,
                }
            )

    onboarding_out = None
    intern_out = None
    if effective_uid:
        rev = (
            await db.execute(select(ApplicationReview).where(ApplicationReview.user_id == effective_uid))
        ).scalars().first()
        prof = (
            await db.execute(select(ApplicantProfile).where(ApplicantProfile.user_id == effective_uid))
        ).scalars().first()
        if rev or prof:
            onboarding_out = {
                "user_id": str(effective_uid),
                "status": rev.status.value if rev else None,
                "feedback": rev.feedback if rev else None,
                "submitted_at": rev.submitted_at.isoformat() if rev and rev.submitted_at else None,
                "reviewed_at": rev.reviewed_at.isoformat() if rev and rev.reviewed_at else None,
                "also_grant_role": prof.also_grant_role if prof else None,
                "nationality": prof.nationality if prof else None,
                "work_status": prof.work_status if prof else None,
            }

        intern_prof = await db.get(InternProfile, effective_uid)
        if intern_prof:
            work_city = None
            if intern_prof.work_city_id:
                wc = await db.get(City, intern_prof.work_city_id)
                work_city = wc.name if wc else None
            letter_url = (
                await storage.get_signed_url("internship-letters", intern_prof.letter_path)
                if intern_prof.letter_path
                else None
            )
            signed_letter_url = (
                await storage.get_signed_url("internship-letters", intern_prof.signed_letter_path)
                if intern_prof.signed_letter_path
                else None
            )
            intern_out = {
                "ref_number": intern_prof.ref_number,
                "university_id_number": intern_prof.university_id_number,
                "department": intern_prof.department,
                "start_date": intern_prof.start_date.isoformat() if intern_prof.start_date else None,
                "duration_weeks": intern_prof.duration_weeks,
                "hours_per_week": intern_prof.hours_per_week,
                "work_city": work_city,
                "letter_date": intern_prof.letter_date.isoformat() if intern_prof.letter_date else None,
                "has_letter": bool(intern_prof.letter_path),
                "has_signed_letter": bool(intern_prof.signed_letter_path),
                "letter_url": letter_url,
                "signed_letter_url": signed_letter_url,
                "letter_signed_at": intern_prof.letter_signed_at.isoformat()
                if intern_prof.letter_signed_at
                else None,
            }

    return {
        "existing_user": existing_user_out,
        "spine_contact": contact_out,
        "other_applications": other_apps_out,
        "role_requests": role_requests_out,
        "instructor_onboarding": onboarding_out,
        "intern_profile": intern_out,
    }


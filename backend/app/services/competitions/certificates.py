"""Competition cohort certificate issuance (2026-09).

Allows ops to evaluate submission progress for a competition cohort and issue
completion certificates to:
- Students who did at least one submission (>= 1 deliverable submitted)
- Students who completed all required submissions (all required deliverables submitted,
  or team locked its final submission)

Student completion certs are rendered as PDFs from the `student_completion` template,
emailed directly to the student contact, and recorded in the unified `certificates` table
(type='student_completion', contact-owned, registration-linked) matching
`services/sessions/delivery.py::_issue_student_certificate`.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from html import escape
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.certificate import Certificate
from app.models.document_template import DocumentTemplate
from app.models.enums import CertificateType
from app.models.lms.program import (
    LmsProgramAssignment, LmsProgramItem, LmsProgramItemProgress, LmsProgramTeamItemProgress,
)
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.models.team import Team, TeamMember
from app.models.user import User
from app.services.documents.certificate import generate_completion_certificate_pdf, merge_certificate_pdfs
from app.services.email import try_send_email
from app.services.lms.program import effective_cohort_program_items
from app.services.sessions.registration import ACTIVE_REGISTRATION_STATUSES, format_cohort_dates
from app.services.sessions.staffing import resolve_session_location_display


def _cert_email_body(student_name: str, program_name: str, dates: str) -> str:
    return (
        f"<p>Hi {escape(student_name)},</p>"
        f"<p>Congratulations on completing <strong>{escape(program_name)}</strong> ({escape(dates)})!</p>"
        "<p>Your certificate of completion is attached to this email as a PDF.</p>"
        "<p>— SpacePoint</p>"
    )


async def get_cohort_certificate_recipients(
    db: AsyncSession, *, cohort_id: uuid.UUID, filter_type: str = "all",
) -> dict:
    """Computes submission stats for every active registrant in this cohort,
    evaluating whether they completed at least one submission or all required
    submissions.
    """
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")

    # 1. Effective checklist items for this cohort
    resolved = await effective_cohort_program_items(db, cohort_id)
    items: list[LmsProgramItem] = resolved[1] if resolved else []

    # Identify submission items: items explicitly typed as 'submission',
    # or team deliverables if none are explicitly typed as 'submission'
    submission_items = [i for i in items if i.item_type == "submission"]
    if not submission_items:
        submission_items = [i for i in items if (i.scope == "team" and i.item_type != "mission_run")]
    if not submission_items:
        submission_items = [i for i in items if not i.optional]

    required_submission_items = [i for i in submission_items if not i.optional]
    if not required_submission_items and submission_items:
        required_submission_items = submission_items

    submission_item_ids = {i.id for i in submission_items}
    required_item_ids = {i.id for i in required_submission_items}
    total_required = len(required_item_ids)

    # 2. Active registrations
    registrations = (await db.execute(
        select(Registration).where(
            Registration.cohort_id == cohort_id,
            Registration.status.in_(ACTIVE_REGISTRATION_STATUSES),
        )
    )).scalars().all()

    if not registrations:
        return {
            "total_registered": 0,
            "submission_items_total": len(submission_items),
            "required_submissions_total": total_required,
            "at_least_one_count": 0,
            "all_completed_count": 0,
            "recipients": [],
        }

    contact_ids = [r.contact_id for r in registrations]
    contacts = {
        c.id: c for c in (await db.execute(select(Contact).where(Contact.id.in_(contact_ids)))).scalars().all()
    }

    # Map contact_id -> user
    users_by_contact = {
        u.contact_id: u for u in (await db.execute(
            select(User).where(User.contact_id.in_(contact_ids))
        )).scalars().all()
    }

    # 3. Teams in this cohort
    teams = (await db.execute(select(Team).where(Team.cohort_id == cohort_id))).scalars().all()
    team_by_id = {t.id: t for t in teams}

    # Map user_id -> team
    user_team_map: dict[uuid.UUID, Team] = {}
    if team_by_id:
        member_rows = (await db.execute(
            select(TeamMember.user_id, TeamMember.team_id).where(TeamMember.team_id.in_(team_by_id.keys()))
        )).all()
        for user_id, team_id in member_rows:
            if team_id in team_by_id:
                user_team_map[user_id] = team_by_id[team_id]

    # 4. Check existing certificates
    reg_ids = [r.id for r in registrations]
    existing_certs = {
        c.registration_id: c for c in (await db.execute(
            select(Certificate).where(Certificate.registration_id.in_(reg_ids))
        )).scalars().all()
    }

    # 5. Load team progress for team submission items
    team_submitted_items: dict[uuid.UUID, set[uuid.UUID]] = {t.id: set() for t in teams}
    if team_by_id and submission_item_ids:
        team_progress_rows = (await db.execute(
            select(LmsProgramTeamItemProgress).where(
                LmsProgramTeamItemProgress.team_id.in_(team_by_id.keys()),
                LmsProgramTeamItemProgress.item_id.in_(submission_item_ids),
            )
        )).scalars().all()
        for p in team_progress_rows:
            is_submitted = (
                p.status in ("done", "awaiting_confirmation")
                or bool(p.submitted_url)
                or bool(p.submitted_text)
                or bool(p.submitted_links)
            )
            if is_submitted:
                team_submitted_items[p.team_id].add(p.item_id)

    # 6. Load individual progress for individual submission items
    user_ids = [u.id for u in users_by_contact.values()]
    individual_submitted_items: dict[uuid.UUID, set[uuid.UUID]] = {uid: set() for uid in user_ids}
    if user_ids and submission_item_ids:
        assignments = (await db.execute(
            select(LmsProgramAssignment).where(
                LmsProgramAssignment.cohort_id == cohort_id,
                LmsProgramAssignment.user_id.in_(user_ids),
            )
        )).scalars().all()
        assignment_map = {a.id: a.user_id for a in assignments}
        if assignment_map:
            indiv_progress_rows = (await db.execute(
                select(LmsProgramItemProgress).where(
                    LmsProgramItemProgress.assignment_id.in_(assignment_map.keys()),
                    LmsProgramItemProgress.item_id.in_(submission_item_ids),
                )
            )).scalars().all()
            for p in indiv_progress_rows:
                is_submitted = (
                    p.status in ("done", "awaiting_confirmation")
                    or bool(p.submitted_url)
                    or bool(p.submitted_text)
                    or bool(p.submitted_links)
                )
                if is_submitted:
                    u_id = assignment_map.get(p.assignment_id)
                    if u_id:
                        individual_submitted_items[u_id].add(p.item_id)

    # 7. Evaluate each student
    recipients = []
    at_least_one_count = 0
    all_completed_count = 0

    for reg in registrations:
        contact = contacts.get(reg.contact_id)
        if contact is None:
            continue
        user = users_by_contact.get(contact.id)
        team = user_team_map.get(user.id) if user else None

        # Calculate completed submission items
        submitted_item_ids = set()
        if team:
            submitted_item_ids.update(team_submitted_items.get(team.id, set()))
        if user:
            submitted_item_ids.update(individual_submitted_items.get(user.id, set()))

        submissions_done = len(submitted_item_ids)
        meets_at_least_one = submissions_done >= 1

        team_locked = bool(team and team.final_locked_at is not None)
        has_all_required = total_required > 0 and required_item_ids.issubset(submitted_item_ids)
        meets_all_completed = has_all_required or team_locked

        if meets_at_least_one:
            at_least_one_count += 1
        if meets_all_completed:
            all_completed_count += 1

        cert = existing_certs.get(reg.id)

        # Check filter condition
        if filter_type == "at_least_one" and not meets_at_least_one:
            continue
        if filter_type == "all_completed" and not meets_all_completed:
            continue

        recipients.append({
            "registration_id": reg.id,
            "user_id": user.id if user else None,
            "contact_id": contact.id,
            "student_name": contact.full_name,
            "email": contact.email,
            "team_id": team.id if team else None,
            "team_name": team.name if team else None,
            "submissions_done": submissions_done,
            "submissions_total": len(submission_items),
            "required_submissions_total": total_required,
            "team_locked": team_locked,
            "meets_at_least_one": meets_at_least_one,
            "meets_all_completed": meets_all_completed,
            "certificate_issued": cert is not None,
            "certificate_id": cert.id if cert else None,
            "certificate_generated_at": cert.generated_at if cert else None,
        })

    # Sort recipients by student_name
    recipients.sort(key=lambda r: r["student_name"] or "")

    return {
        "total_registered": len(registrations),
        "submission_items_total": len(submission_items),
        "required_submissions_total": total_required,
        "at_least_one_count": at_least_one_count,
        "all_completed_count": all_completed_count,
        "recipients": recipients,
    }


async def send_cohort_certificates(
    db: AsyncSession,
    *,
    cohort_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    filter_type: str = "at_least_one",
    registration_ids: list[uuid.UUID] | None = None,
    theme: str = "dark",
    skip_already_issued: bool = True,
) -> dict:
    """Issues and emails completion certificates to the qualifying or selected
    students in the cohort. Updates registration status to 'completed'.
    """
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    program = await db.get(Program, cohort.program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program not found")

    # Get candidate recipients
    all_data = await get_cohort_certificate_recipients(db, cohort_id=cohort_id, filter_type="all")
    all_recipients = {r["registration_id"]: r for r in all_data["recipients"]}

    if registration_ids is not None and len(registration_ids) > 0:
        target_ids = [rid for rid in registration_ids if rid in all_recipients]
    elif filter_type == "all_completed":
        target_ids = [rid for rid, r in all_recipients.items() if r["meets_all_completed"]]
    elif filter_type == "at_least_one":
        target_ids = [rid for rid, r in all_recipients.items() if r["meets_at_least_one"]]
    else:
        target_ids = list(all_recipients.keys())

    if not target_ids:
        return {
            "sent_count": 0,
            "skipped_count": 0,
            "total_targeted": 0,
            "recipient_names": [],
            "errors": [],
        }

    # Fetch registrations
    registrations = (await db.execute(
        select(Registration).where(Registration.id.in_(target_ids))
    )).scalars().all()
    reg_by_id = {r.id: r for r in registrations}

    # Fetch contacts
    contact_ids = [r.contact_id for r in registrations]
    contacts = {
        c.id: c for c in (await db.execute(select(Contact).where(Contact.id.in_(contact_ids)))).scalars().all()
    }

    # Fetch existing certificates
    existing_certs = {
        c.registration_id: c for c in (await db.execute(
            select(Certificate).where(Certificate.registration_id.in_(target_ids))
        )).scalars().all()
    }

    dates = format_cohort_dates(cohort)
    location = await resolve_session_location_display(db, None, cohort)
    template = (await db.execute(
        select(DocumentTemplate).where(DocumentTemplate.key == "student_completion")
    )).scalars().first()

    template_body = template.body_text if template else "For successfully completing<br/>{program_name}<br/>{dates}"
    body_text = template_body \
        .replace("{program_name}", escape(program.name)) \
        .replace("{dates}", escape(dates)) \
        .replace("{location}", escape(location.get("name") or ""))

    sent_count = 0
    skipped_count = 0
    recipient_names = []
    errors = []

    for reg_id in target_ids:
        reg = reg_by_id.get(reg_id)
        if not reg:
            continue
        contact = contacts.get(reg.contact_id)
        if not contact:
            continue

        existing = existing_certs.get(reg.id)
        if existing is not None and skip_already_issued:
            skipped_count += 1
            continue

        try:
            cert_bytes = await asyncio.to_thread(
                generate_completion_certificate_pdf, contact.full_name, body_text, theme=theme,
            )

            if existing is None:
                certificate = Certificate(
                    id=uuid.uuid4(),
                    contact_id=contact.id,
                    registration_id=reg.id,
                    type=CertificateType.student_completion,
                    workshop_name=program.name,
                    workshop_date=dates,
                    location=location.get("name"),
                    generated_by=actor_user_id,
                )
                db.add(certificate)
            else:
                existing.generated_at = datetime.now(timezone.utc)
                existing.generated_by = actor_user_id

            reg.status = "completed"
            await db.flush()

            # Email the cert as a PDF attachment
            if contact.email:
                filename = f"SpacePoint_Certificate_{program.name.replace(' ', '_')}.pdf"
                await try_send_email(
                    contact.email,
                    f"Your SpacePoint certificate — {program.name}",
                    _cert_email_body(contact.full_name, program.name, dates),
                    html=True,
                    attachments=[(filename, cert_bytes, "pdf")],
                )

            sent_count += 1
            recipient_names.append(contact.full_name)
        except Exception as exc:
            errors.append(f"{contact.full_name}: {exc}")

    await db.commit()

    return {
        "sent_count": sent_count,
        "skipped_count": skipped_count,
        "total_targeted": len(target_ids),
        "recipient_names": recipient_names,
        "errors": errors,
    }


async def render_cohort_certificates_pdf(
    db: AsyncSession,
    *,
    cohort_id: uuid.UUID,
    filter_type: str = "at_least_one",
    theme: str = "dark",
    registration_ids: list[uuid.UUID] | None = None,
) -> tuple[bytes, str]:
    """Generates a merged PDF containing completion certificates for students
    matching the filter or specified registration IDs.
    """
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    program = await db.get(Program, cohort.program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program not found")

    data = await get_cohort_certificate_recipients(db, cohort_id=cohort_id, filter_type=filter_type)
    recipients = data["recipients"]
    if registration_ids:
        target_ids = set(registration_ids)
        recipients = [r for r in recipients if r["registration_id"] in target_ids]

    if not recipients:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No matching students found to generate certificates")

    dates = format_cohort_dates(cohort)
    location = await resolve_session_location_display(db, None, cohort)
    template = (await db.execute(
        select(DocumentTemplate).where(DocumentTemplate.key == "student_completion")
    )).scalars().first()

    template_body = template.body_text if template else "For successfully completing<br/>{program_name}<br/>{dates}"
    body_text = template_body \
        .replace("{program_name}", escape(program.name)) \
        .replace("{dates}", escape(dates)) \
        .replace("{location}", escape(location.get("name") or ""))

    def _render(name: str, body: str) -> bytes:
        return generate_completion_certificate_pdf(name, body, theme=theme)

    pages = [
        await asyncio.to_thread(_render, r["student_name"], body_text)
        for r in recipients
    ]
    merged = await asyncio.to_thread(merge_certificate_pdfs, pages)
    safe_name = "".join(c for c in cohort.name if c.isalnum() or c in " -_").strip().replace(" ", "_")
    filename = f"certificates_{filter_type}_{safe_name or cohort_id}_{theme}.pdf"
    return merged, filename


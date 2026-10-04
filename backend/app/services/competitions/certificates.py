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
import logging
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.models.certificate import Certificate
from app.models.document_template import DocumentTemplate
from app.models.enums import CertificateType
from app.models.lms.program import (
    LmsProgramAssignment, LmsProgramItem, LmsProgramItemProgress, LmsProgramTeamItemProgress,
)
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.program_certificate_template import ProgramCertificateTemplate
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.models.team import Team, TeamMember
from app.models.user import User
from app.services import storage
from app.services.documents.certificate import (
    format_certificate_program_title, generate_completion_certificate_pdf, merge_certificate_pdfs,
)
from app.services.email import try_send_email
from app.services.lms.program import effective_cohort_program_items
from app.services.sessions.registration import ACTIVE_REGISTRATION_STATUSES, format_cohort_dates
from app.services.sessions.staffing import resolve_session_location_display


def render_certificate_email(
    *,
    student_name: str,
    program_name: str,
    cohort_name: str = "",
    dates: str = "",
    team_name: str | None = None,
    certificate_type: str = "completion",  # "completion" | "participation"
    custom_subject: str | None = None,
    custom_body: str | None = None,
) -> tuple[str, str]:
    """Renders (subject, body_html) substituting available tokens:
    {student_name}, {program_name}, {cohort_name}, {dates}, {team_name}, {certificate_type}
    """
    type_label = "Participation" if certificate_type == "participation" else "Completion"
    full_program_title = format_certificate_program_title(program_name, cohort_name)
    team_display = team_name or ""
    team_snippet = f" with team <strong>{escape(team_name)}</strong>" if team_name else ""

    # Subject
    if custom_subject and custom_subject.strip():
        subject = (
            custom_subject
            .replace("{student_name}", student_name)
            .replace("{program_name}", full_program_title)
            .replace("{cohort_name}", cohort_name)
            .replace("{cohort}", cohort_name)
            .replace("{dates}", dates)
            .replace("{team_name}", team_display)
            .replace("{certificate_type}", type_label)
        )
    else:
        if certificate_type == "participation":
            subject = f"Your Certificate of Participation — {full_program_title}"
        else:
            subject = f"Your SpacePoint certificate — {full_program_title}"

    # Body
    if custom_body and custom_body.strip():
        # Replace tokens in custom body
        body_html = (
            custom_body
            .replace("{student_name}", escape(student_name))
            .replace("{program_name}", escape(full_program_title))
            .replace("{cohort_name}", escape(cohort_name))
            .replace("{cohort}", escape(cohort_name))
            .replace("{dates}", escape(dates))
            .replace("{team_name}", escape(team_display))
            .replace("{certificate_type}", type_label)
        )
        if "<p" not in body_html.lower() and "<br" not in body_html.lower() and "<div" not in body_html.lower():
            body_html = "<br/>".join(body_html.split("\n"))
    else:
        if certificate_type == "participation":
            body_html = (
                f"<p>Hi {escape(student_name)},</p>"
                f"<p>Thank you for participating in <strong>{escape(full_program_title)}</strong>{team_snippet} ({escape(dates)})!</p>"
                "<p>Your certificate of participation is attached to this email as a PDF.</p>"
                "<p>— SpacePoint</p>"
            )
        else:
            body_html = (
                f"<p>Hi {escape(student_name)},</p>"
                f"<p>Congratulations on completing <strong>{escape(full_program_title)}</strong> ({escape(dates)})!</p>"
                "<p>Your certificate of completion is attached to this email as a PDF.</p>"
                "<p>— SpacePoint</p>"
            )

    return subject, body_html


def _cert_email_body(student_name: str, program_name: str, dates: str) -> str:
    _, body = render_certificate_email(student_name=student_name, program_name=program_name, dates=dates)
    return body


async def get_cohort_certificate_recipients(
    db: AsyncSession, *, cohort_id: uuid.UUID, filter_type: str = "all",
) -> dict:
    """Computes submission stats for every active registrant in this cohort,
    evaluating whether they completed at least one submission, locked only,
    or all required submissions.
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
    optional_item_ids = submission_item_ids - required_item_ids
    total_required = len(required_item_ids)
    total_optional = len(optional_item_ids)

    # 2. Active registrations
    registrations = (await db.execute(
        select(Registration).where(
            Registration.cohort_id == cohort_id,
            Registration.status.in_(ACTIVE_REGISTRATION_STATUSES),
        )
    )).scalars().all()

    # Load templates for this cohort's program
    program = await db.get(Program, cohort.program_id)
    default_tid = str(program.default_certificate_template_id) if program and program.default_certificate_template_id else None
    templates_rows = (await db.execute(
        select(ProgramCertificateTemplate)
        .where(ProgramCertificateTemplate.program_id == cohort.program_id)
        .order_by(ProgramCertificateTemplate.created_at.asc())
    )).scalars().all()

    available_templates = [
        {
            "id": "dark",
            "name": "Dark Default",
            "is_default": default_tid is None,
            "background_type": "dark",
            "email_subject": None,
            "email_body": None,
        },
        {
            "id": "light",
            "name": "Light Default",
            "is_default": False,
            "background_type": "light",
            "email_subject": None,
            "email_body": None,
        },
    ]
    for t in templates_rows:
        is_def = t.is_default or (default_tid == str(t.id))
        available_templates.append({
            "id": str(t.id),
            "name": t.name,
            "is_default": is_def,
            "background_type": t.background_type,
            "email_subject": t.email_subject,
            "email_body": t.email_body,
        })

    cohort_dates = format_cohort_dates(cohort)

    if not registrations:
        return {
            "program_name": program.name if program else None,
            "cohort_name": cohort.name if cohort else None,
            "dates": cohort_dates,
            "total_registered": 0,
            "submission_items_total": len(submission_items),
            "required_submissions_total": total_required,
            "at_least_one_count": 0,
            "all_completed_count": 0,
            "recipients": [],
            "templates": available_templates,
            "default_template_id": default_tid,
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
    # Observer mode (2026-10): observer test teams never count toward
    # certificates — drop them before mapping members to teams.
    teams = [t for t in teams if not getattr(t, "is_observer", False)]
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
    locked_only_count = 0
    participation_count = 0
    at_least_one_count = 0
    all_completed_count = 0

    # Observer mode (2026-10): assignments with mode='observer' are
    # suppressed from certificate pipelines entirely — never counted in
    # stats, never listed as recipients.
    observer_user_ids: set[uuid.UUID] = set()
    if user_ids:
        observer_user_ids = set((await db.execute(
            select(LmsProgramAssignment.user_id).where(
                LmsProgramAssignment.cohort_id == cohort_id,
                LmsProgramAssignment.user_id.in_(user_ids),
                LmsProgramAssignment.mode == "observer",
            )
        )).scalars().all())

    for reg in registrations:
        contact = contacts.get(reg.contact_id)
        if contact is None:
            continue
        user = users_by_contact.get(contact.id)
        if user is not None and user.id in observer_user_ids:
            continue
        team = user_team_map.get(user.id) if user else None

        # Calculate completed submission items, split into required vs
        # optional. Optionals never count toward participation/completion —
        # they are bonus only. (Previously a single `submissions_done` total
        # mixed both, so an optional submission masked a missing required
        # one as e.g. "6/6".)
        submitted_item_ids = set()
        if team:
            submitted_item_ids.update(team_submitted_items.get(team.id, set()))
        if user:
            submitted_item_ids.update(individual_submitted_items.get(user.id, set()))

        submissions_done = len(submitted_item_ids)
        required_submissions_done = len(submitted_item_ids & required_item_ids)
        optional_submissions_done = len(submitted_item_ids & optional_item_ids)
        # Participation is earned by required work only — an optional-only
        # submission does not qualify.
        meets_at_least_one = required_submissions_done >= 1

        team_locked = bool(team and team.final_locked_at is not None)
        has_all_required = total_required > 0 and required_item_ids.issubset(submitted_item_ids)
        meets_all_completed = has_all_required or team_locked
        meets_locked_only = team_locked
        meets_participation = meets_at_least_one and not team_locked

        if meets_locked_only:
            locked_only_count += 1
        if meets_participation:
            participation_count += 1
        if meets_at_least_one:
            at_least_one_count += 1
        if meets_all_completed:
            all_completed_count += 1

        cert = existing_certs.get(reg.id)

        # Check filter condition
        if filter_type == "locked_only" and not meets_locked_only:
            continue
        if filter_type == "participation" and not meets_participation:
            continue
        if filter_type == "at_least_one" and not meets_at_least_one:
            continue
        if filter_type == "all_completed" and not meets_all_completed:
            continue

        certificate_type_earned = (
            "completion" if (team_locked or meets_all_completed)
            else ("participation" if meets_at_least_one else None)
        )

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
            "required_submissions_done": required_submissions_done,
            "optional_submissions_done": optional_submissions_done,
            "optional_submissions_total": total_optional,
            "team_locked": team_locked,
            "meets_locked_only": meets_locked_only,
            "meets_participation": meets_participation,
            "meets_at_least_one": meets_at_least_one,
            "meets_all_completed": meets_all_completed,
            "certificate_type_earned": certificate_type_earned,
            "certificate_issued": cert is not None,
            "certificate_id": cert.id if cert else None,
            "certificate_generated_at": cert.generated_at if cert else None,
        })

    # Sort recipients by student_name
    recipients.sort(key=lambda r: r["student_name"] or "")

    return {
        "program_name": program.name if program else None,
        "cohort_name": cohort.name if cohort else None,
        "dates": cohort_dates,
        "total_registered": len(registrations),
        "submission_items_total": len(submission_items),
        "required_submissions_total": total_required,
        "locked_only_count": locked_only_count,
        "participation_count": participation_count,
        "at_least_one_count": at_least_one_count,
        "all_completed_count": all_completed_count,
        "recipients": recipients,
        "templates": available_templates,
        "default_template_id": default_tid,
    }


async def _resolve_certificate_template(
    db: AsyncSession,
    *,
    program: Program,
    template_id: str | uuid.UUID | None = None,
    theme: str = "dark",
) -> dict:
    """Resolves template configuration (background bytes, font sizes, colors, coordinates,
    signature settings). Falls back to stock theme if no custom template is chosen.
    """
    selected_template: ProgramCertificateTemplate | None = None

    # 1. If explicit template_id is provided as UUID
    if template_id and template_id not in ("dark", "light", "default"):
        try:
            tid = uuid.UUID(str(template_id))
            selected_template = await db.get(ProgramCertificateTemplate, tid)
        except (ValueError, TypeError):
            selected_template = None

    # 2. If template_id is None or 'default', check program default
    if selected_template is None and (template_id is None or template_id == "default"):
        if program.default_certificate_template_id:
            selected_template = await db.get(ProgramCertificateTemplate, program.default_certificate_template_id)
        if selected_template is None:
            selected_template = (await db.execute(
                select(ProgramCertificateTemplate).where(
                    ProgramCertificateTemplate.program_id == program.id,
                    ProgramCertificateTemplate.is_default.is_(True),
                )
            )).scalars().first()

    # 3. Stock theme fallback
    effective_theme = theme
    if template_id in ("dark", "light"):
        effective_theme = template_id

    from app.services.settings import get_portal_setting
    from app.core.config import settings as app_settings
    sig_name = await get_portal_setting(db, "admin_signatory_name", app_settings.DEFAULT_SIGNATORY_NAME)
    sig_title = await get_portal_setting(db, "admin_signatory_title", app_settings.DEFAULT_SIGNATORY_TITLE)

    if selected_template is not None:
        bg_bytes = None
        if selected_template.background_type == "custom" and selected_template.background_file_path:
            try:
                bg_bytes = await storage.download_file("documents", selected_template.background_file_path)
            except Exception:
                bg_bytes = None

        sig_bytes = None
        if selected_template.show_signature:
            if selected_template.signature_image_path:
                try:
                    sig_bytes = await storage.download_file("documents", selected_template.signature_image_path)
                except Exception:
                    sig_bytes = None
            if not sig_bytes:
                try:
                    sig_bytes = await storage.download_file("instructor-documents", "settings/admin_signature.png")
                except Exception:
                    sig_bytes = None

        return {
            "template_obj": selected_template,
            "is_custom": True,
            "theme": selected_template.background_type if selected_template.background_type in ("dark", "light") else "dark",
            "background_bytes": bg_bytes,
            "body_text_template": selected_template.body_text,
            "name_font_size": selected_template.name_font_size,
            "name_y": float(selected_template.name_y),
            "name_color": selected_template.name_color,
            "body_font_size": selected_template.body_font_size,
            "body_y": float(selected_template.body_y),
            "body_color": selected_template.body_color,
            "body_max_width": float(selected_template.body_max_width),
            "body_alignment": selected_template.body_alignment,
            "show_signature": selected_template.show_signature,
            "signature_bytes": sig_bytes,
            "signature_x": float(selected_template.signature_x) if selected_template.signature_x is not None else None,
            "signature_y": float(selected_template.signature_y),
            "signature_width": float(selected_template.signature_width),
            "signature_height": float(selected_template.signature_height),
            "signatory_name": sig_name,
            "signatory_title": sig_title,
            "email_subject": selected_template.email_subject,
            "email_body": selected_template.email_body,
        }

    return {
        "template_obj": None,
        "is_custom": False,
        "theme": effective_theme,
        "background_bytes": None,
        "body_text_template": None,
        "name_font_size": 34,
        "name_y": 298.0,
        "name_color": None,
        "body_font_size": 20,
        "body_y": 260.0,
        "body_color": None,
        "body_max_width": 600.0,
        "body_alignment": "center",
        "show_signature": False,
        "signature_bytes": None,
        "signature_x": None,
        "signature_y": 90.0,
        "signature_width": 140.0,
        "signature_height": 50.0,
        "signatory_name": sig_name,
        "signatory_title": sig_title,
        "email_subject": None,
        "email_body": None,
    }


async def send_cohort_certificates(
    db: AsyncSession,
    *,
    cohort_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    filter_type: str = "at_least_one",
    registration_ids: list[uuid.UUID] | None = None,
    theme: str = "dark",
    template_id: str | None = None,
    skip_already_issued: bool = True,
    custom_email_subject: str | None = None,
    custom_email_body: str | None = None,
    save_email_to_template: bool = False,
    force_certificate_type: str | None = None,
) -> dict:
    """Issues and emails completion or participation certificates to the qualifying
    or selected students in the cohort. Updates registration status to 'completed'.

    `force_certificate_type` overrides the per-recipient earned type for every
    targeted student — ops' call when the system's own eligibility doesn't
    match reality (e.g. send the whole cohort completion certificates).
    """
    if force_certificate_type not in (None, "completion", "participation"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="force_certificate_type must be 'completion' or 'participation'")
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
        target_id_set = set()
        for item in registration_ids:
            try:
                target_id_set.add(uuid.UUID(str(item)))
            except (ValueError, TypeError):
                pass
        target_ids = [rid for rid in all_recipients if rid in target_id_set]
    elif filter_type == "locked_only":
        target_ids = [rid for rid, r in all_recipients.items() if r["meets_locked_only"]]
    elif filter_type == "participation":
        target_ids = [rid for rid, r in all_recipients.items() if r["meets_participation"]]
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
    layout = await _resolve_certificate_template(db, program=program, template_id=template_id, theme=theme)

    # Persist custom email template to template if requested
    if save_email_to_template and layout.get("template_obj"):
        tmpl: ProgramCertificateTemplate = layout["template_obj"]
        if custom_email_subject is not None:
            tmpl.email_subject = custom_email_subject.strip() or None
        if custom_email_body is not None:
            tmpl.email_body = custom_email_body.strip() or None
        await db.flush()

    template = (await db.execute(
        select(DocumentTemplate).where(DocumentTemplate.key == "student_completion")
    )).scalars().first()

    cohort_title = cohort.name if cohort and cohort.name else ""

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

        rec_info = all_recipients.get(reg_id, {})
        cert_type = force_certificate_type or rec_info.get("certificate_type_earned") or (
            "completion" if rec_info.get("team_locked") else "participation"
        )
        type_title = "Participation" if cert_type == "participation" else "Completion"

        if layout.get("body_text_template"):
            raw_body_template = layout["body_text_template"]
        else:
            if cert_type == "participation":
                raw_body_template = "For active participation in<br/>{program_name}<br/>{dates}"
            else:
                raw_body_template = template.body_text if template else "For successfully completing<br/>{program_name}<br/>{dates}"

        student_body_text = (
            raw_body_template
            .replace("{program_name}", escape(program.name))
            .replace("{cohort_name}", escape(cohort_title))
            .replace("{cohort}", escape(cohort_title))
            .replace("{dates}", escape(dates))
            .replace("{location}", escape(location.get("name") or ""))
            .replace("{certificate_type}", type_title)
            .replace("{type}", type_title)
        )

        try:
            async with db.begin_nested():
                cert_bytes = await asyncio.to_thread(
                    generate_completion_certificate_pdf,
                    recipient_name=contact.full_name,
                    body_text_template=student_body_text,
                    background_bytes=layout["background_bytes"],
                    theme=layout["theme"],
                    name_font_size=layout["name_font_size"],
                    name_y=layout["name_y"],
                    name_color=layout["name_color"],
                    body_font_size=layout["body_font_size"],
                    body_y=layout["body_y"],
                    body_color=layout["body_color"],
                    body_max_width=layout["body_max_width"],
                    body_alignment=layout["body_alignment"],
                    show_signature=layout["show_signature"],
                    signature_bytes=layout["signature_bytes"],
                    signature_x=layout["signature_x"],
                    signature_y=layout["signature_y"],
                    signature_width=layout["signature_width"],
                    signature_height=layout["signature_height"],
                    signatory_name=layout.get("signatory_name"),
                    signatory_title=layout.get("signatory_title"),
                )

                cert_storage_path = f"cohort_{cohort.id}/{contact.id}_{reg.id}.pdf"
                try:
                    await storage.upload_to_path("certificates", cert_storage_path, cert_bytes, "application/pdf")
                    cert_bucket = "certificates"
                except Exception as upload_err:
                    logger.warning("Failed to upload cert PDF to storage: %s", upload_err)
                    cert_bucket = None
                    cert_storage_path = None

                if existing is None:
                    certificate = Certificate(
                        id=uuid.uuid4(),
                        contact_id=contact.id,
                        registration_id=reg.id,
                        type=CertificateType.student_completion,
                        workshop_name=program.name,
                        workshop_date=dates,
                        location=location.get("name"),
                        bucket=cert_bucket,
                        file_path=cert_storage_path,
                        generated_by=actor_user_id,
                    )
                    db.add(certificate)
                else:
                    existing.generated_at = datetime.now(timezone.utc)
                    existing.generated_by = actor_user_id
                    if cert_bucket and cert_storage_path:
                        existing.bucket = cert_bucket
                        existing.file_path = cert_storage_path

                reg.status = "completed"
                await db.flush()

                # Email the cert as a PDF attachment
                if contact.email:
                    email_subj, email_body = render_certificate_email(
                        student_name=contact.full_name,
                        program_name=program.name,
                        cohort_name=cohort_title,
                        dates=dates,
                        team_name=rec_info.get("team_name"),
                        certificate_type=cert_type,
                        custom_subject=custom_email_subject or layout.get("email_subject"),
                        custom_body=custom_email_body or layout.get("email_body"),
                    )
                    safe_pname = "".join(c for c in program.name if c.isalnum() or c in " -_").strip().replace(" ", "_")
                    filename = f"SpacePoint_{type_title}_Certificate_{safe_pname or 'Program'}.pdf"
                    await try_send_email(
                        contact.email,
                        email_subj,
                        email_body,
                        html=True,
                        attachments=[(filename, cert_bytes, "pdf")],
                    )

                sent_count += 1
                recipient_names.append(contact.full_name)
                await db.commit()
                await asyncio.sleep(0.1)
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
    filter_type: Literal["locked_only", "participation", "at_least_one", "all_completed", "all"] = "at_least_one",
    theme: str = "dark",
    template_id: str | None = None,
    registration_ids: list[uuid.UUID] | None = None,
    force_certificate_type: str | None = None,
) -> tuple[bytes, str]:
    """Renders a single combined PDF with one landscape A4 certificate per eligible recipient."""
    if force_certificate_type not in (None, "completion", "participation"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="force_certificate_type must be 'completion' or 'participation'")
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")

    program = await db.get(Program, cohort.program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program not found")

    effective_filter = "all" if registration_ids else filter_type
    data = await get_cohort_certificate_recipients(db, cohort_id=cohort_id, filter_type=effective_filter)
    recipients = data["recipients"]
    if registration_ids:
        target_ids = set()
        for item in registration_ids:
            try:
                target_ids.add(uuid.UUID(str(item)))
            except (ValueError, TypeError):
                pass
        recipients = [r for r in recipients if r["registration_id"] in target_ids]

    if not recipients:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No matching students found for the selected filter")

    dates = format_cohort_dates(cohort)
    location = await resolve_session_location_display(db, None, cohort)
    layout = await _resolve_certificate_template(db, program=program, template_id=template_id, theme=theme)

    template = (await db.execute(
        select(DocumentTemplate).where(DocumentTemplate.key == "student_completion")
    )).scalars().first()

    cohort_title = cohort.name if cohort and cohort.name else ""

    def _render(name: str, body: str) -> bytes:
        return generate_completion_certificate_pdf(
            recipient_name=name,
            body_text_template=body,
            background_bytes=layout["background_bytes"],
            theme=layout["theme"],
            name_font_size=layout["name_font_size"],
            name_y=layout["name_y"],
            name_color=layout["name_color"],
            body_font_size=layout["body_font_size"],
            body_y=layout["body_y"],
            body_color=layout["body_color"],
            body_max_width=layout["body_max_width"],
            body_alignment=layout["body_alignment"],
            show_signature=layout["show_signature"],
            signature_bytes=layout["signature_bytes"],
            signature_x=layout["signature_x"],
            signature_y=layout["signature_y"],
            signature_width=layout["signature_width"],
            signature_height=layout["signature_height"],
            signatory_name=layout.get("signatory_name"),
            signatory_title=layout.get("signatory_title"),
        )

    pages = []
    for r in recipients:
        rec_info = r
        cert_type = force_certificate_type or rec_info.get("certificate_type_earned") or (
            "completion" if rec_info.get("team_locked") else "participation"
        )
        type_title = "Participation" if cert_type == "participation" else "Completion"

        if layout.get("body_text_template"):
            raw_body_template = layout["body_text_template"]
        else:
            if cert_type == "participation":
                raw_body_template = "For active participation in<br/>{program_name}<br/>{dates}"
            else:
                raw_body_template = template.body_text if template else "For successfully completing<br/>{program_name}<br/>{dates}"

        student_body = (
            raw_body_template
            .replace("{program_name}", escape(program.name))
            .replace("{cohort_name}", escape(cohort_title))
            .replace("{cohort}", escape(cohort_title))
            .replace("{dates}", escape(dates))
            .replace("{location}", escape(location.get("name") or ""))
            .replace("{certificate_type}", type_title)
            .replace("{type}", type_title)
        )
        pages.append(await asyncio.to_thread(_render, r["student_name"], student_body))

    merged = await asyncio.to_thread(merge_certificate_pdfs, pages)
    safe_name = "".join(c for c in cohort.name if c.isalnum() or c in " -_").strip().replace(" ", "_")
    theme_suffix = layout["theme"] if not layout.get("is_custom") else "custom"
    filename = f"certificates_{filter_type}_{safe_name or cohort_id}_{theme_suffix}.pdf"
    return merged, filename


async def send_test_certificate_email(
    db: AsyncSession,
    *,
    cohort_id: uuid.UUID,
    to_email: str,
    recipient_name: str | None = None,
    theme: str = "dark",
    template_id: str | None = None,
    certificate_type: str = "completion",
    custom_email_subject: str | None = None,
    custom_email_body: str | None = None,
) -> dict:
    """Renders a sample certificate with the given config and sends a test email
    to `to_email`. Does NOT record any Certificate row or modify any registration.
    """
    if certificate_type not in ("completion", "participation"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="certificate_type must be 'completion' or 'participation'")

    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    program = await db.get(Program, cohort.program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program not found")

    dates = format_cohort_dates(cohort)
    location = await resolve_session_location_display(db, None, cohort)
    layout = await _resolve_certificate_template(db, program=program, template_id=template_id, theme=theme)

    template = (await db.execute(
        select(DocumentTemplate).where(DocumentTemplate.key == "student_completion")
    )).scalars().first()

    type_title = "Participation" if certificate_type == "participation" else "Completion"
    cohort_title = cohort.name or ""

    if layout.get("body_text_template"):
        raw_body_template = layout["body_text_template"]
    else:
        if certificate_type == "participation":
            raw_body_template = "For active participation in<br/>{program_name}<br/>{dates}"
        else:
            raw_body_template = template.body_text if template else "For successfully completing<br/>{program_name}<br/>{dates}"

    student_body_text = (
        raw_body_template
        .replace("{program_name}", escape(program.name))
        .replace("{cohort_name}", escape(cohort_title))
        .replace("{cohort}", escape(cohort_title))
        .replace("{dates}", escape(dates))
        .replace("{location}", escape(location.get("name") or ""))
        .replace("{certificate_type}", type_title)
        .replace("{type}", type_title)
    )

    effective_name = recipient_name.strip() if recipient_name and recipient_name.strip() else "Test Recipient"

    cert_bytes = await asyncio.to_thread(
        generate_completion_certificate_pdf,
        recipient_name=effective_name,
        body_text_template=student_body_text,
        background_bytes=layout["background_bytes"],
        theme=layout["theme"],
        name_font_size=layout["name_font_size"],
        name_y=layout["name_y"],
        name_color=layout["name_color"],
        body_font_size=layout["body_font_size"],
        body_y=layout["body_y"],
        body_color=layout["body_color"],
        body_max_width=layout["body_max_width"],
        body_alignment=layout["body_alignment"],
        show_signature=layout["show_signature"],
        signature_bytes=layout["signature_bytes"],
        signature_x=layout["signature_x"],
        signature_y=layout["signature_y"],
        signature_width=layout["signature_width"],
        signature_height=layout["signature_height"],
        signatory_name=layout.get("signatory_name"),
        signatory_title=layout.get("signatory_title"),
    )

    email_subj, email_body_html = render_certificate_email(
        student_name=effective_name,
        program_name=program.name,
        cohort_name=cohort_title,
        dates=dates,
        team_name=None,
        certificate_type=certificate_type,
        custom_subject=custom_email_subject or layout.get("email_subject"),
        custom_body=custom_email_body or layout.get("email_body"),
    )

    # Prepend a test banner to clearly mark this as a preview email
    test_banner = (
        "<div style=\"background:#f59e0b;color:#1c1917;padding:8px 14px;"
        "border-radius:6px;font-size:12px;font-weight:600;margin-bottom:14px;\">"
        "⚠️ TEST EMAIL — This is a preview of the certificate email. No records were created.</div>"
    )
    email_body_html = test_banner + email_body_html

    safe_pname = "".join(c for c in program.name if c.isalnum() or c in " -_").strip().replace(" ", "_")
    filename = f"SpacePoint_{type_title}_Certificate_{safe_pname or 'Program'}.pdf"

    await try_send_email(
        to_email,
        f"[TEST] {email_subj}",
        email_body_html,
        html=True,
        attachments=[(filename, cert_bytes, "pdf")],
    )

    return {"sent": True, "to": to_email, "subject": f"[TEST] {email_subj}"}



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

from app.core.config import settings
from app.models.certificate import Certificate
from app.models.document_template import DocumentTemplate
from app.models.enums import CertificateType
from app.models.lms.program import (
    LmsProgramAssignment, LmsProgramItem, LmsProgramItemProgress, LmsProgramTeamItemProgress,
)
from app.models.sessions.certificate_email_template import CertificateEmailTemplate
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.program_certificate_template import ProgramCertificateTemplate
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.models.team import Team, TeamMember
from app.models.user import User
from app.services import storage
from app.services.documents.certificate import (
    STUDENT_COMPLETION_FALLBACK_BODY, STUDENT_PARTICIPATION_FALLBACK_BODY,
    expand_certificate_body_template, format_certificate_program_title, format_rank_ordinal,
    generate_completion_certificate_pdf, merge_certificate_pdfs,
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
    team_rank: int | None = None,
    certificate_type: str = "completion",  # "completion" | "participation" | "team"
    custom_subject: str | None = None,
    custom_body: str | None = None,
    certificate_list: str = "Certificate",
    profile_link: str = "",
) -> tuple[str, str]:
    """Renders (subject, body_html) substituting available tokens:
    {student_name}, {program_name}, {cohort_name}, {dates}, {team_name}, {rank},
    {certificate_type}, {certificate_list}, {profile_link}
    """
    type_label = (
        "Team Certificate" if certificate_type == "team"
        else ("Participation" if certificate_type == "participation" else "Completion")
    )
    full_program_title = format_certificate_program_title(program_name, cohort_name)
    team_display = team_name or ""
    rank_display = format_rank_ordinal(team_rank)
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
            .replace("{rank}", rank_display)
            .replace("{certificate_type}", type_label)
            .replace("{certificate_list}", certificate_list)
        )
    else:
        if certificate_type == "participation":
            subject = f"Your Certificate of Participation — {full_program_title}"
        elif certificate_type == "team":
            subject = f"Your Team Certificate — {full_program_title}"
        else:
            subject = f"Your SpacePoint certificate — {full_program_title}"

    # Body
    if custom_body and custom_body.strip():
        body_html = (
            custom_body
            .replace("{student_name}", escape(student_name))
            .replace("{program_name}", escape(full_program_title))
            .replace("{cohort_name}", escape(cohort_name))
            .replace("{cohort}", escape(cohort_name))
            .replace("{dates}", escape(dates))
            .replace("{team_name}", escape(team_display))
            .replace("{rank}", escape(rank_display))
            .replace("{certificate_type}", type_label)
            .replace("{certificate_list}", escape(certificate_list))
            .replace("{profile_link}", escape(profile_link))
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
    checkpoint_items = sorted(
        [i for i in items if i.item_type == "checkpoint"],
        key=lambda i: i.position,
    )
    checkpoint_list = [
        {"item_id": cp.id, "title": cp.title, "position": cp.position}
        for cp in checkpoint_items
    ]

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

    # Team rows only measure team-scoped submissions when any exist (individual-scoped
    # items belong per-member, not on a single team row — matching team_final_submit_readiness).
    team_scoped_sub_ids = {i.id for i in submission_items if i.scope == "team"}
    if team_scoped_sub_ids:
        team_required_item_ids = required_item_ids & team_scoped_sub_ids
        team_optional_item_ids = optional_item_ids & team_scoped_sub_ids
    else:
        team_required_item_ids = required_item_ids
        team_optional_item_ids = optional_item_ids
    team_total_required = len(team_required_item_ids)
    team_total_optional = len(team_optional_item_ids)

    # 2. Active registrations
    registrations = (await db.execute(
        select(Registration).where(
            Registration.cohort_id == cohort_id,
            Registration.status.in_(ACTIVE_REGISTRATION_STATUSES),
        )
    )).scalars().all()

    # Load templates for this cohort's program (resolving defaults via cohort -> variation -> program)
    program = await db.get(Program, cohort.program_id)
    variation = None
    if getattr(cohort, "variation_id", None) is not None:
        from app.models.sessions.program_variation import ProgramVariation
        variation = await db.get(ProgramVariation, cohort.variation_id)

    def _eff_cert_tid(attr: str) -> str | None:
        val = (
            getattr(cohort, attr, None)
            or (getattr(variation, attr, None) if variation else None)
            or (getattr(program, attr, None) if program else None)
        )
        return str(val) if val else None

    default_tid = _eff_cert_tid("default_certificate_template_id")
    default_team_tid = _eff_cert_tid("default_team_certificate_template_id")
    templates_rows = (await db.execute(
        select(ProgramCertificateTemplate)
        .where(ProgramCertificateTemplate.program_id == cohort.program_id)
        .order_by(ProgramCertificateTemplate.created_at.asc())
    )).scalars().all()

    available_templates = [
        {
            "id": "dark",
            "name": "Dark Default",
            "kind": "both",
            "is_default": default_tid is None,
            "background_type": "dark",
            "email_subject": None,
            "email_body": None,
        },
        {
            "id": "light",
            "name": "Light Default",
            "kind": "both",
            "is_default": False,
            "background_type": "light",
            "email_subject": None,
            "email_body": None,
        },
    ]
    for t in templates_rows:
        t_kind = getattr(t, "kind", "individual") or "individual"
        is_def = t.is_default or (default_tid == str(t.id) if t_kind == "individual" else default_team_tid == str(t.id))
        available_templates.append({
            "id": str(t.id),
            "name": t.name,
            "kind": "both",
            "is_default": is_def,
            "background_type": t.background_type,
            "email_subject": t.email_subject,
            "email_body": t.email_body,
        })

    email_template_rows = (await db.execute(
        select(CertificateEmailTemplate).order_by(
            CertificateEmailTemplate.is_default.desc(),
            CertificateEmailTemplate.created_at.asc(),
        )
    )).scalars().all()
    available_email_templates = [
        {
            "id": str(et.id),
            "name": et.name,
            "kind": et.kind,
            "subject": et.subject,
            "body_html": et.body_html,
            "is_default": et.is_default,
        }
        for et in email_template_rows
    ]

    cohort_dates = format_cohort_dates(cohort)

    if not registrations:
        return {
            "program_name": program.name if program else None,
            "cohort_name": cohort.name if cohort else None,
            "dates": cohort_dates,
            "total_registered": 0,
            "submission_items_total": len(submission_items),
            "required_submissions_total": total_required,
            "optional_submissions_total": total_optional,
            "at_least_one_count": 0,
            "all_completed_count": 0,
            "checkpoints": checkpoint_list,
            "recipients": [],
            "teams": [],
            "templates": available_templates,
            "email_templates": available_email_templates,
            "default_template_id": default_tid,
            "default_team_template_id": default_team_tid,
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

    # Team ranks from the judging leaderboard (scored teams only).
    from app.services.competitions.judging import leaderboard as _leaderboard
    team_rank: dict[uuid.UUID, int] = {}
    if team_by_id:
        try:
            for row in await _leaderboard(db, cohort_id=cohort_id, mode="participant"):
                if row.get("score") is not None and row.get("team_id") is not None:
                    team_rank[row["team_id"]] = row["rank"]
        except Exception:
            logger.warning("Could not compute team ranks for cohort %s", cohort_id, exc_info=True)

    # 4. Check existing certificates — strictly keyed by (registration_id, type)
    # so student_completion and team_completion never leak into each other.
    reg_ids = [r.id for r in registrations]
    existing_certs: dict[tuple[uuid.UUID, CertificateType], Certificate] = {}
    for c in (await db.execute(
        select(Certificate).where(
            Certificate.registration_id.in_(reg_ids),
            Certificate.type.in_([CertificateType.student_completion, CertificateType.team_completion]),
        )
    )).scalars().all():
        if c.registration_id is not None:
            existing_certs[(c.registration_id, c.type)] = c

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

    # 5b. Completed (locked) checkpoint gates per team
    team_completed_checkpoints: dict[uuid.UUID, list[uuid.UUID]] = {t.id: [] for t in teams}
    cp_item_ids = {cp.id for cp in checkpoint_items}
    if team_by_id and cp_item_ids:
        cp_done_rows = (await db.execute(
            select(LmsProgramTeamItemProgress.team_id, LmsProgramTeamItemProgress.item_id).where(
                LmsProgramTeamItemProgress.team_id.in_(team_by_id.keys()),
                LmsProgramTeamItemProgress.item_id.in_(cp_item_ids),
                LmsProgramTeamItemProgress.status == "done",
            )
        )).all()
        cp_done_by_team: dict[uuid.UUID, set[uuid.UUID]] = {}
        for tid, iid in cp_done_rows:
            cp_done_by_team.setdefault(tid, set()).add(iid)
        for tid in team_by_id:
            done_set = cp_done_by_team.get(tid, set())
            team_completed_checkpoints[tid] = [cp.id for cp in checkpoint_items if cp.id in done_set]

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

        student_cert = existing_certs.get((reg.id, CertificateType.student_completion))
        team_cert = existing_certs.get((reg.id, CertificateType.team_completion))

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
            "team_rank": team_rank.get(team.id) if team else None,
            "completed_checkpoint_ids": team_completed_checkpoints.get(team.id, []) if team else [],
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
            "certificate_issued": student_cert is not None,
            "certificate_id": student_cert.id if student_cert else None,
            "certificate_generated_at": student_cert.generated_at if student_cert else None,
            "student_cert_issued": student_cert is not None,
            "student_cert_id": student_cert.id if student_cert else None,
            "student_cert_generated_at": student_cert.generated_at if student_cert else None,
            "student_cert_delivery": getattr(student_cert, "delivery_mode", None) if student_cert else None,
            "team_cert_issued": team_cert is not None,
            "team_cert_id": team_cert.id if team_cert else None,
            "team_cert_generated_at": team_cert.generated_at if team_cert else None,
            "team_cert_delivery": getattr(team_cert, "delivery_mode", None) if team_cert else None,
        })

    # Sort recipients by student_name
    recipients.sort(key=lambda r: r["student_name"] or "")

    # Build team-level summary rows for Teams view
    teams_summary = []
    recs_by_team: dict[uuid.UUID, list[dict]] = {}
    for rec in recipients:
        if rec["team_id"] is not None:
            recs_by_team.setdefault(rec["team_id"], []).append(rec)

    for t in teams:
        t_recs = recs_by_team.get(t.id, [])
        t_sub_ids = team_submitted_items.get(t.id, set())
        t_req_done = len(t_sub_ids & team_required_item_ids)
        t_opt_done = len(t_sub_ids & team_optional_item_ids)
        if not team_scoped_sub_ids and not t_req_done and t_recs:
            t_req_done = max((r["required_submissions_done"] for r in t_recs), default=0)
            t_opt_done = max((r["optional_submissions_done"] for r in t_recs), default=0)

        team_certs = [r for r in t_recs if r["team_cert_issued"]]
        member_student_certs = sum(1 for r in t_recs if r["student_cert_issued"])
        t_cert_issued = len(t_recs) > 0 and len(team_certs) == len(t_recs)
        latest_team_cert_at = max(
            (r["team_cert_generated_at"] for r in team_certs if r["team_cert_generated_at"] is not None),
            default=None,
        )
        t_delivery = team_certs[0]["team_cert_delivery"] if team_certs else None
        teams_summary.append({
            "team_id": t.id,
            "team_name": t.name,
            "rank": team_rank.get(t.id),
            "member_count": len(t_recs),
            "required_submissions_done": t_req_done,
            "required_submissions_total": team_total_required,
            "optional_submissions_done": t_opt_done,
            "optional_submissions_total": team_total_optional,
            "team_locked": bool(t.final_locked_at is not None),
            "team_cert_issued": t_cert_issued,
            "team_cert_generated_at": latest_team_cert_at,
            "team_cert_delivery": t_delivery,
            "member_student_certs_issued": member_student_certs,
            "completed_checkpoint_ids": team_completed_checkpoints.get(t.id, []),
            "registration_ids": [r["registration_id"] for r in t_recs],
        })

    teams_summary.sort(key=lambda row: (row["rank"] is None, row["rank"] or 999999, row["team_name"] or ""))

    return {
        "program_name": program.name if program else None,
        "cohort_name": cohort.name if cohort else None,
        "dates": cohort_dates,
        "total_registered": len(registrations),
        "submission_items_total": len(submission_items),
        "required_submissions_total": total_required,
        "optional_submissions_total": total_optional,
        "locked_only_count": locked_only_count,
        "participation_count": participation_count,
        "at_least_one_count": at_least_one_count,
        "all_completed_count": all_completed_count,
        "checkpoints": checkpoint_list,
        "recipients": recipients,
        "teams": teams_summary,
        "templates": available_templates,
        "email_templates": available_email_templates,
        "default_template_id": default_tid,
        "default_team_template_id": default_team_tid,
    }


async def _resolve_certificate_template(
    db: AsyncSession,
    *,
    program: Program,
    cohort: Cohort | None = None,
    template_id: str | uuid.UUID | None = None,
    theme: str = "dark",
    kind: str = "individual",
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

    # 2. If template_id is None or 'default', check cohort -> variation -> program defaults
    if selected_template is None and (template_id is None or template_id == "default"):
        variation = None
        if cohort is not None and getattr(cohort, "variation_id", None) is not None:
            from app.models.sessions.program_variation import ProgramVariation
            variation = await db.get(ProgramVariation, cohort.variation_id)

        def _pick_tid(attr: str):
            return (
                (getattr(cohort, attr, None) if cohort is not None else None)
                or (getattr(variation, attr, None) if variation is not None else None)
                or getattr(program, attr, None)
            )

        default_field = (
            (_pick_tid("default_team_certificate_template_id") or _pick_tid("default_certificate_template_id"))
            if kind == "team"
            else _pick_tid("default_certificate_template_id")
        )
        if default_field:
            selected_template = await db.get(ProgramCertificateTemplate, default_field)
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


async def _resolve_email_template(
    db: AsyncSession,
    email_template_id: uuid.UUID | None,
    fallback_kind: str = "individual",
) -> CertificateEmailTemplate | None:
    if email_template_id is not None:
        tpl = await db.get(CertificateEmailTemplate, email_template_id)
        if tpl is not None:
            return tpl
    return (await db.execute(
        select(CertificateEmailTemplate)
        .where(CertificateEmailTemplate.kind == fallback_kind)
        .order_by(CertificateEmailTemplate.is_default.desc(), CertificateEmailTemplate.created_at.asc())
    )).scalars().first()


def _safe_pdf_filename(program_name: str, kind: str) -> str:
    safe_pname = "".join(c for c in program_name if c.isalnum() or c in " -_").strip() or "Program"
    label = "Team Certificate" if kind == "team" else "Certificate"
    return f"{safe_pname} - {label}.pdf"


async def send_cohort_certificates(
    db: AsyncSession,
    *,
    cohort_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    filter_type: str = "at_least_one",
    registration_ids: list[uuid.UUID] | None = None,
    team_ids: list[uuid.UUID] | None = None,
    theme: str = "dark",
    template_id: str | None = None,
    primary_kind: str = "individual",
    primary_template_id: str | None = None,
    primary_email_template_id: uuid.UUID | None = None,
    also_send_other: bool = False,
    secondary_template_id: str | None = None,
    secondary_email_template_id: uuid.UUID | None = None,
    delivery_mode: str = "email",
    notify_by_email: bool = True,
    skip_already_issued: bool = True,
    custom_email_subject: str | None = None,
    custom_email_body: str | None = None,
    save_email_to_template: bool = False,
    force_certificate_type: str | None = None,
) -> dict:
    """Issues and emails (or publishes to profile) individual and/or team certificates."""
    if force_certificate_type not in (None, "completion", "participation"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="force_certificate_type must be 'completion' or 'participation'")
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    program = await db.get(Program, cohort.program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program not found")

    all_data = await get_cohort_certificate_recipients(db, cohort_id=cohort_id, filter_type="all")
    all_recipients = {r["registration_id"]: r for r in all_data["recipients"]}

    # Resolve target registrations from registration_ids, team_ids, or filter_type
    if registration_ids is not None and len(registration_ids) > 0:
        target_id_set = set()
        for item in registration_ids:
            try:
                target_id_set.add(uuid.UUID(str(item)))
            except (ValueError, TypeError):
                pass
        target_ids = [rid for rid in all_recipients if rid in target_id_set]
    elif team_ids is not None and len(team_ids) > 0:
        team_id_set = set()
        for tid in team_ids:
            try:
                team_id_set.add(uuid.UUID(str(tid)))
            except (ValueError, TypeError):
                pass
        target_ids = [rid for rid, r in all_recipients.items() if r.get("team_id") in team_id_set]
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

    # Which kinds are we sending?
    send_individual = (primary_kind == "individual") or also_send_other
    send_team = (primary_kind == "team") or also_send_other

    eff_primary_tpl = primary_template_id if primary_template_id is not None else template_id
    ind_tpl_id = eff_primary_tpl if primary_kind == "individual" else secondary_template_id
    team_tpl_id = eff_primary_tpl if primary_kind == "team" else secondary_template_id

    ind_email_tpl_id = primary_email_template_id if primary_kind == "individual" else secondary_email_template_id
    team_email_tpl_id = primary_email_template_id if primary_kind == "team" else secondary_email_template_id

    registrations = (await db.execute(
        select(Registration).where(Registration.id.in_(target_ids))
    )).scalars().all()
    reg_by_id = {r.id: r for r in registrations}

    contact_ids = [r.contact_id for r in registrations]
    contacts = {
        c.id: c for c in (await db.execute(select(Contact).where(Contact.id.in_(contact_ids)))).scalars().all()
    }

    # Strictly keyed by (registration_id, type) — zero leak between student_completion and team_completion
    existing_certs: dict[tuple[uuid.UUID, CertificateType], Certificate] = {}
    for c in (await db.execute(
        select(Certificate).where(
            Certificate.registration_id.in_(target_ids),
            Certificate.type.in_([CertificateType.student_completion, CertificateType.team_completion]),
        )
    )).scalars().all():
        if c.registration_id is not None:
            existing_certs[(c.registration_id, c.type)] = c

    dates = format_cohort_dates(cohort)
    location = await resolve_session_location_display(db, None, cohort)

    ind_layout = (
        await _resolve_certificate_template(db, program=program, cohort=cohort, template_id=ind_tpl_id, theme=theme, kind="individual")
        if send_individual else None
    )
    team_layout = (
        await _resolve_certificate_template(db, program=program, cohort=cohort, template_id=team_tpl_id, theme=theme, kind="team")
        if send_team else None
    )

    fallback_mail_kind = "profile" if delivery_mode == "publish" else None
    ind_email_tpl = (
        await _resolve_email_template(db, ind_email_tpl_id, fallback_mail_kind or "individual")
        if send_individual else None
    )
    team_email_tpl = (
        await _resolve_email_template(db, team_email_tpl_id, fallback_mail_kind or "team")
        if send_team else None
    )
    combine_email = (
        send_individual
        and send_team
        and ind_email_tpl_id is not None
        and ind_email_tpl_id == team_email_tpl_id
    )

    template = (await db.execute(
        select(DocumentTemplate).where(DocumentTemplate.key == "student_completion")
    )).scalars().first()

    cohort_title = cohort.name if cohort and cohort.name else ""
    profile_link = f"{settings.FRONTEND_URL.rstrip('/')}/learn/profile"
    now = datetime.now(timezone.utc)

    sent_count = 0
    skipped_count = 0
    recipient_names = []
    errors = []

    def _build_pdf(rec_name: str, layout: dict, rec_info: dict, cert_type_str: str) -> bytes:
        type_title = "Participation" if cert_type_str == "participation" else "Completion"
        if layout.get("is_custom"):
            raw_body = layout.get("body_text_template") or ""
        elif layout.get("body_text_template"):
            raw_body = layout["body_text_template"]
        elif cert_type_str == "participation":
            raw_body = STUDENT_PARTICIPATION_FALLBACK_BODY
        else:
            raw_body = template.body_text if template else STUDENT_COMPLETION_FALLBACK_BODY

        expanded = expand_certificate_body_template(
            raw_body,
            program_name=program.name,
            cohort_name=cohort_title,
            dates=dates,
            starts_on=cohort.starts_on,
            ends_on=cohort.ends_on,
            location=location.get("name"),
            certificate_type_label=type_title,
            team_name=rec_info.get("team_name"),
            rank=rec_info.get("team_rank"),
        )
        return generate_completion_certificate_pdf(
            recipient_name=rec_name,
            body_text_template=expanded,
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

    for reg_id in target_ids:
        reg = reg_by_id.get(reg_id)
        if not reg:
            continue
        contact = contacts.get(reg.contact_id)
        if not contact:
            continue

        rec_info = all_recipients.get(reg_id, {})
        cert_type_str = force_certificate_type or rec_info.get("certificate_type_earned") or (
            "completion" if rec_info.get("team_locked") else "participation"
        )

        # Decide which of (individual, team) to issue for this student
        issue_ind = send_individual
        issue_team = send_team and (rec_info.get("team_id") is not None)

        if issue_ind and skip_already_issued and (reg.id, CertificateType.student_completion) in existing_certs:
            issue_ind = False
        if issue_team and skip_already_issued and (reg.id, CertificateType.team_completion) in existing_certs:
            issue_team = False

        if not issue_ind and not issue_team:
            skipped_count += 1
            continue

        try:
            async with db.begin_nested():
                generated_pdfs: list[tuple[str, bytes, str]] = []  # (kind, bytes, filename)

                for kind_key, do_issue, cert_enum, layout in (
                    ("individual", issue_ind, CertificateType.student_completion, ind_layout),
                    ("team", issue_team, CertificateType.team_completion, team_layout),
                ):
                    if not do_issue or layout is None:
                        continue
                    # The name on the certificate follows the kind: team
                    # certificates carry the team's name, individual ones the
                    # student's (2026-11 — team certs used to print the student
                    # name because contact.full_name was hardcoded for both
                    # kinds). A missing team name falls back to the student
                    # name rather than printing a blank line.
                    rec_name = contact.full_name
                    if kind_key == "team":
                        rec_name = (rec_info.get("team_name") or "").strip() or contact.full_name
                    pdf_bytes = await asyncio.to_thread(_build_pdf, rec_name, layout, rec_info, cert_type_str)
                    prefix = "team" if kind_key == "team" else "student"
                    storage_path = f"cohort_{cohort.id}/{prefix}_{contact.id}_{reg.id}.pdf"
                    try:
                        await storage.upload_to_path("certificates", storage_path, pdf_bytes, "application/pdf")
                        cert_bucket = "certificates"
                    except Exception as upload_err:
                        logger.warning("Failed to upload cert PDF to storage: %s", upload_err)
                        cert_bucket = None
                        storage_path = None

                    tpl_obj = layout.get("template_obj")
                    existing = existing_certs.get((reg.id, cert_enum))
                    if existing is None:
                        cert_row = Certificate(
                            id=uuid.uuid4(),
                            contact_id=contact.id,
                            registration_id=reg.id,
                            type=cert_enum,
                            workshop_name=program.name,
                            workshop_date=dates,
                            location=location.get("name"),
                            bucket=cert_bucket,
                            file_path=storage_path,
                            generated_by=actor_user_id,
                            team_id=rec_info.get("team_id") if kind_key == "team" else None,
                            delivery_mode=delivery_mode,
                            published_at=now,
                            template_id=tpl_obj.id if tpl_obj else None,
                        )
                        db.add(cert_row)
                    else:
                        existing.generated_at = now
                        existing.generated_by = actor_user_id
                        existing.delivery_mode = delivery_mode
                        existing.published_at = now
                        if kind_key == "team":
                            existing.team_id = rec_info.get("team_id")
                        if tpl_obj:
                            existing.template_id = tpl_obj.id
                        if cert_bucket and storage_path:
                            existing.bucket = cert_bucket
                            existing.file_path = storage_path

                    generated_pdfs.append((kind_key, pdf_bytes, _safe_pdf_filename(program.name, kind_key)))

                reg.status = "completed"
                await db.flush()

                if contact.email and generated_pdfs and (delivery_mode != "publish" or notify_by_email):
                    if combine_email and len(generated_pdfs) == 2:
                        email_tpl = ind_email_tpl
                        subj_tpl = custom_email_subject or (email_tpl.subject if email_tpl else None)
                        body_tpl = custom_email_body or (email_tpl.body_html if email_tpl else None)
                        email_subj, email_body = render_certificate_email(
                            student_name=contact.full_name,
                            program_name=program.name,
                            cohort_name=cohort_title,
                            dates=dates,
                            team_name=rec_info.get("team_name"),
                            team_rank=rec_info.get("team_rank"),
                            certificate_type=cert_type_str,
                            custom_subject=subj_tpl,
                            custom_body=body_tpl,
                            certificate_list="Student Certificate and Team Certificate",
                            profile_link=profile_link,
                        )
                        attachments = (
                            [(fname, b, "pdf") for _, b, fname in generated_pdfs]
                            if delivery_mode != "publish" else None
                        )
                        await try_send_email(contact.email, email_subj, email_body, html=True, attachments=attachments)
                    else:
                        for kind_key, pdf_bytes, fname in generated_pdfs:
                            email_tpl = team_email_tpl if kind_key == "team" else ind_email_tpl
                            subj_tpl = custom_email_subject or (email_tpl.subject if email_tpl else None)
                            body_tpl = custom_email_body or (email_tpl.body_html if email_tpl else None)
                            cert_label = "Team Certificate" if kind_key == "team" else "Student Certificate"
                            email_subj, email_body = render_certificate_email(
                                student_name=contact.full_name,
                                program_name=program.name,
                                cohort_name=cohort_title,
                                dates=dates,
                                team_name=rec_info.get("team_name"),
                                team_rank=rec_info.get("team_rank"),
                                certificate_type="team" if kind_key == "team" else cert_type_str,
                                custom_subject=subj_tpl,
                                custom_body=body_tpl,
                                certificate_list=cert_label,
                                profile_link=profile_link,
                            )
                            attachments = [(fname, pdf_bytes, "pdf")] if delivery_mode != "publish" else None
                            await try_send_email(contact.email, email_subj, email_body, html=True, attachments=attachments)

                sent_count += 1
                recipient_names.append(contact.full_name)
                await db.commit()
                await asyncio.sleep(0.05)
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
    kind: str = "individual",
    registration_ids: list[uuid.UUID] | None = None,
    team_ids: list[uuid.UUID] | None = None,
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

    effective_filter = "all" if (registration_ids or team_ids) else filter_type
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
    elif team_ids:
        target_tids = set()
        for item in team_ids:
            try:
                target_tids.add(uuid.UUID(str(item)))
            except (ValueError, TypeError):
                pass
        recipients = [r for r in recipients if r.get("team_id") in target_tids]

    if kind == "team":
        recipients = [r for r in recipients if r.get("team_id") is not None]

    if not recipients:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No matching students found for the selected filter")

    dates = format_cohort_dates(cohort)
    location = await resolve_session_location_display(db, None, cohort)
    layout = await _resolve_certificate_template(db, program=program, cohort=cohort, template_id=template_id, theme=theme, kind=kind)

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

        if layout.get("is_custom"):
            raw_body_template = layout.get("body_text_template") or ""
        elif layout.get("body_text_template"):
            raw_body_template = layout["body_text_template"]
        else:
            if cert_type == "participation":
                raw_body_template = STUDENT_PARTICIPATION_FALLBACK_BODY
            else:
                raw_body_template = template.body_text if template else STUDENT_COMPLETION_FALLBACK_BODY

        student_body = expand_certificate_body_template(
            raw_body_template,
            program_name=program.name,
            cohort_name=cohort_title,
            dates=dates,
            starts_on=cohort.starts_on,
            ends_on=cohort.ends_on,
            location=location.get("name"),
            certificate_type_label=type_title,
            team_name=rec_info.get("team_name"),
            rank=rec_info.get("team_rank"),
        )
        # Same kind-driven name rule as send_cohort_certificates: the bulk/
        # preview PDF must match what will actually be emailed — team kind
        # carries the team's name, individual the student's.
        rec_name = r["student_name"]
        if kind == "team":
            rec_name = (r.get("team_name") or "").strip() or r["student_name"]
        pages.append(await asyncio.to_thread(_render, rec_name, student_body))

    merged = await asyncio.to_thread(merge_certificate_pdfs, pages)
    filename = _safe_pdf_filename(program.name, kind)
    return merged, filename


async def send_test_certificate_email(
    db: AsyncSession,
    *,
    cohort_id: uuid.UUID,
    to_email: str,
    recipient_name: str | None = None,
    theme: str = "dark",
    template_id: str | None = None,
    kind: str = "individual",
    email_template_id: uuid.UUID | None = None,
    delivery_mode: str = "email",
    notify_by_email: bool = True,
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
    layout = await _resolve_certificate_template(db, program=program, cohort=cohort, template_id=template_id, theme=theme, kind=kind)
    email_tpl = await _resolve_email_template(
        db,
        email_template_id,
        "profile" if delivery_mode == "publish" else ("team" if kind == "team" else "individual"),
    )

    template = (await db.execute(
        select(DocumentTemplate).where(DocumentTemplate.key == "student_completion")
    )).scalars().first()

    type_title = "Participation" if certificate_type == "participation" else "Completion"
    cohort_title = cohort.name or ""

    if layout.get("is_custom"):
        raw_body_template = layout.get("body_text_template") or ""
    elif layout.get("body_text_template"):
        raw_body_template = layout["body_text_template"]
    else:
        if certificate_type == "participation":
            raw_body_template = STUDENT_PARTICIPATION_FALLBACK_BODY
        else:
            raw_body_template = template.body_text if template else STUDENT_COMPLETION_FALLBACK_BODY

    student_body_text = expand_certificate_body_template(
        raw_body_template,
        program_name=program.name,
        cohort_name=cohort_title,
        dates=dates,
        starts_on=cohort.starts_on,
        ends_on=cohort.ends_on,
        location=location.get("name"),
        certificate_type_label=type_title,
        team_name="Sample Team",
        rank=1,
    )

    effective_name = recipient_name.strip() if recipient_name and recipient_name.strip() else (
        "Sample Team" if kind == "team" else "Test Recipient"
    )

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

    profile_link = f"{settings.FRONTEND_URL.rstrip('/')}/learn/profile"
    cert_label = "Team Certificate" if kind == "team" else "Student Certificate"

    email_subj, email_body_html = render_certificate_email(
        student_name=effective_name,
        program_name=program.name,
        cohort_name=cohort_title,
        dates=dates,
        team_name="Sample Team",
        team_rank=1,
        certificate_type="team" if kind == "team" else certificate_type,
        custom_subject=custom_email_subject or (email_tpl.subject if email_tpl else layout.get("email_subject")),
        custom_body=custom_email_body or (email_tpl.body_html if email_tpl else layout.get("email_body")),
        certificate_list=cert_label,
        profile_link=profile_link,
    )

    test_banner = (
        "<div style=\"background:#6D28D9;color:#ffffff;padding:8px 14px;"
        "border-radius:10px;font-size:12px;font-weight:600;margin-bottom:14px;\">"
        "TEST EMAIL — Preview of the certificate email. No records were created.</div>"
    )
    email_body_html = test_banner + email_body_html

    filename = _safe_pdf_filename(program.name, kind)
    attachments = [(filename, cert_bytes, "pdf")] if delivery_mode != "publish" else None

    await try_send_email(
        to_email,
        f"[TEST] {email_subj}",
        email_body_html,
        html=True,
        attachments=attachments,
    )

    return {"sent": True, "to": to_email, "subject": f"[TEST] {email_subj}"}



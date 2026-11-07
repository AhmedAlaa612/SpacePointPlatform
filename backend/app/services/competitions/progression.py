"""Competition progression (2026-08-24) — moving teams from one stage
(cohort) to the next. Never automatic off a score threshold: exporting the
Top 20 for external NSA review and deciding the real Top 10 happens off
platform; `advance_teams()` is the one explicit ops action that actually
moves anyone, called once ops has that final list.

Advancing a team means the same thing advancing an individual student
between cohorts already means elsewhere in this codebase (`register()` +
`assign_lms_program()`, the exact pair `sync_registration_lms` calls) — a
Registration in the target cohort, a checklist assignment — plus a
same-named `Team` in the target cohort's own scope, since `Team.cohort_id`
is fixed at creation and a Qualifier team can't just be reused for
Finalists.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sessions.cohort import Cohort
from app.models.sessions.registration import Registration
from app.models.team import Team
from app.models.user import User
from app.services.email import try_send_email
from app.services.lms.ops_integration import send_registration_onboarding_email
from app.services.lms.program import assign_lms_program
from app.services.sessions.registration import register
from app.services.teams import create_team, join_team, team_member_ids

CONGRATS_SUBJECT = "You're through to the next stage!"


@dataclass
class TeamAdvanceResult:
    team_id: uuid.UUID
    team_name: str
    to_team_id: uuid.UUID
    members_advanced: int
    # Registrations genuinely created in the target cohort by this call — not
    # ones that already existed there (idempotent re-run). The router uses
    # this to enqueue one ticket job per newly-registered member, same
    # "only ever new-registration rows get a ticket job" rule the bulk
    # import confirm endpoint already follows.
    new_registration_ids: list[uuid.UUID]


async def _congrats_email(
    user: User, *, team_name: str, to_cohort_name: str,
    attachments: list[tuple[str, bytes, str]] | None = None,
) -> None:
    body = (
        f"<p>Hi {user.full_name},</p>"
        f"<p>Congratulations — <b>{team_name}</b> has advanced to <b>{to_cohort_name}</b>! "
        "Log in to see what's next on your checklist.</p>"
    )
    if attachments:
        body += "<p>Your official University Excuse & Formal Invitation Letter is attached to this email.</p>"
    body += "<p>— SpacePoint</p>"
    await try_send_email(
        user.email, CONGRATS_SUBJECT,
        body,
        html=True,
        attachments=attachments,
    )


DEFAULT_INVITATION_TEXT = (
    "We are pleased to formally invite {student_name} {institution} to represent their team "
    "({team_name}) as finalists in the {event_name}, organized by {organizer}. "
    "This prestigious competition will culminate in a live showcase at {location_text}."
)

DEFAULT_SIGNOFF_ENTITIES = [
    {
        "name": "Abdullah AlSalmani",
        "contacts": "a.alsalmani@spacepoint.ae | +971562987005",
        "website": "www.spacepoint.ae",
    }
]

DEFAULT_DESCRIPTION = (
    "The student has been selected as part of the finalist teams representing top talent across "
    "the region. This hands-on experience includes presenting their prototype, engaging with "
    "industry experts, and attending key technical sessions, offering an unparalleled educational "
    "and professional development opportunity in aerospace engineering and innovation."
)


def resolve_excuse_letter_config(
    cohort: Cohort,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolves excuse letter fields from cohort defaults and optional overrides."""
    cfg = dict(cohort.excuse_letter_config or {})
    if overrides:
        for k, v in overrides.items():
            if v is not None and v != "":
                cfg[k] = v

    if cohort.starts_on and cohort.ends_on:
        days = (cohort.ends_on - cohort.starts_on).days + 1
        default_dates = f"{cohort.starts_on.strftime('%d %B %Y')} – {cohort.ends_on.strftime('%d %B %Y')} (all {days} days)"
    elif cohort.starts_on:
        default_dates = cohort.starts_on.strftime('%d %B %Y')
    else:
        default_dates = "Competition On-site Showcase Period"

    default_location = cohort.location or "Dubai, United Arab Emirates"

    raw_entities = cfg.get("signoff_entities")
    resolved_entities = None
    if raw_entities and isinstance(raw_entities, list) and len(raw_entities) > 0:
        cleaned = []
        for e in raw_entities:
            if isinstance(e, dict):
                cleaned.append({
                    "name": e.get("name") or "",
                    "contacts": e.get("contacts") or None,
                    "website": e.get("website") or None,
                })
        if cleaned:
            resolved_entities = cleaned

    if not resolved_entities:
        if cfg.get("committee_name"):
            c_name = cfg.get("committee_name") or "Abdullah AlSalmani"
            email = cfg.get("contact_email")
            phone = cfg.get("contact_phone")
            parts = [p for p in (email, phone) if p]
            resolved_entities = [
                {
                    "name": c_name,
                    "contacts": " | ".join(parts) if parts else "a.alsalmani@spacepoint.ae | +971562987005",
                    "website": cfg.get("contact_website") or "www.spacepoint.ae",
                }
            ]
        else:
            resolved_entities = list(DEFAULT_SIGNOFF_ENTITIES)

    return {
        "enabled": bool(cfg.get("enabled", False)),
        "invitation_text": cfg.get("invitation_text") or DEFAULT_INVITATION_TEXT,
        "event_name": cfg.get("event_name") or cohort.name,
        "organizer": cfg.get("organizer") or "SpacePoint",
        "dates_text": cfg.get("dates_text") or default_dates,
        "location_text": cfg.get("location_text") or default_location,
        "student_role": cfg.get("student_role") or "Finalist — Technical Demonstration & Presentation",
        "participation_mode": cfg.get("participation_mode") or "On-site Exhibition & Technical Demonstration",
        "description_text": cfg.get("description_text") or DEFAULT_DESCRIPTION,
        "signoff_entities": resolved_entities,
        "committee_name": resolved_entities[0]["name"] if resolved_entities else "Abdullah AlSalmani",
        "contact_email": cfg.get("contact_email") or "a.alsalmani@spacepoint.ae",
        "contact_phone": cfg.get("contact_phone") or "+971562987005",
        "contact_website": cfg.get("contact_website") or "www.spacepoint.ae",
    }


async def build_team_excuse_letter_pdf(
    db: AsyncSession,
    *,
    team: Team,
    target_cohort: Cohort,
    single_user_id: uuid.UUID | None = None,
    overrides: dict[str, Any] | None = None,
) -> bytes:
    from app.models.spine.contact import Contact
    from app.models.spine.organization import Organization
    from app.services.documents.excuse_letter import generate_excuse_letter_pdf

    member_ids = await team_member_ids(db, team_id=team.id)
    members_data = []
    institution_name = None
    single_student_data = None

    for uid in member_ids:
        user = await db.get(User, uid)
        if user is None:
            continue
        contact = await db.get(Contact, user.contact_id) if user.contact_id else None

        sid = user.student_id or (contact.student_id if contact else None) or ""

        if contact and contact.organization_id and not institution_name:
            org = await db.get(Organization, contact.organization_id)
            if org:
                institution_name = org.name_latin or org.name_arabic

        m_dict = {
            "name": user.full_name,
            "student_id": sid,
        }
        members_data.append(m_dict)
        if single_user_id and user.id == single_user_id:
            single_student_data = m_dict

    resolved = resolve_excuse_letter_config(target_cohort, overrides)

    # If location is an ID and not overridden, resolve location name
    location_text = resolved["location_text"]
    if target_cohort.location_id and (not overrides or not overrides.get("location_text")):
        from app.models.inventory.location import Location
        loc_obj = await db.get(Location, target_cohort.location_id)
        if loc_obj:
            location_text = f"{loc_obj.name}, {location_text}" if target_cohort.location else loc_obj.name

    return generate_excuse_letter_pdf(
        team_name=team.name,
        institution_name=institution_name,
        members=members_data,
        event_name=resolved["event_name"],
        organizer=resolved["organizer"],
        dates_text=resolved["dates_text"],
        location_text=location_text,
        student_role=resolved["student_role"],
        participation_mode=resolved["participation_mode"],
        description_text=resolved["description_text"],
        invitation_text=resolved.get("invitation_text"),
        signoff_entities=resolved.get("signoff_entities"),
        committee_name=resolved["committee_name"],
        contact_email=resolved["contact_email"],
        contact_phone=resolved["contact_phone"],
        contact_website=resolved["contact_website"],
        single_student=single_student_data,
    )


async def advance_teams(
    db: AsyncSession, *, team_ids: list[uuid.UUID], from_cohort_id: uuid.UUID, to_cohort_id: uuid.UUID,
    send_welcome_email: bool = True,
    attach_excuse_letter: bool = False,
    excuse_letter_mode: str = "team",
    excuse_letter_overrides: dict[str, Any] | None = None,
    save_letter_config_as_default: bool = False,
) -> list[TeamAdvanceResult]:
    """Idempotent per team: re-running with a team that's already advanced
    just re-resolves its existing target-cohort Team/Registrations rather
    than erroring or duplicating — same "a later call just confirms what's
    already true" posture `join_team`/`assign_lms_program` already have."""
    to_cohort = await db.get(Cohort, to_cohort_id)
    if to_cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Target cohort not found")

    if save_letter_config_as_default and excuse_letter_overrides:
        clean_overrides = {k: v for k, v in excuse_letter_overrides.items() if v is not None and v != ""}
        to_cohort.excuse_letter_config = {**(to_cohort.excuse_letter_config or {}), **clean_overrides}

    results = []
    for team_id in team_ids:
        team = await db.get(Team, team_id)
        if team is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Team {team_id} not found")
        if team.cohort_id != from_cohort_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Team '{team.name}' isn't in the source cohort — refusing to advance it",
            )

        # Case-insensitive like the lower(name) uniqueness index — an exact
        # match misses "Team Alpha" vs "team alpha" and the create_team below
        # then 409s, aborting the whole advance loop.
        to_team = (await db.execute(
            select(Team).where(Team.cohort_id == to_cohort_id, func.lower(Team.name) == team.name.lower())
        )).scalars().first()

        member_ids = await team_member_ids(db, team_id=team.id)
        advanced = 0
        new_registration_ids: list[uuid.UUID] = []

        clean_tname = "".join(c for c in team.name if c.isalnum() or c in (" ", "-", "_")).strip()
        team_letter_bytes = None
        if attach_excuse_letter and excuse_letter_mode in ("team", "both"):
            try:
                team_letter_bytes = await build_team_excuse_letter_pdf(
                    db, team=team, target_cohort=to_cohort, overrides=excuse_letter_overrides,
                )
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning("Could not build team excuse letter for team %s: %s", team.name, exc)

        for user_id in member_ids:
            user = await db.get(User, user_id)
            if user is None:
                continue

            if user.contact_id is not None:
                registration = await db.scalar(
                    select(Registration).where(
                        Registration.contact_id == user.contact_id, Registration.cohort_id == to_cohort_id,
                        Registration.status != "cancelled",
                    )
                )
                is_new_registration = registration is None
                if is_new_registration:
                    registration = await register(
                        db, contact_id=user.contact_id, cohort_id=to_cohort_id, registered_via="import",
                        payment_status="waived",
                    )
                    new_registration_ids.append(registration.id)
                # Same "only a genuinely new registration gets an onboarding
                # email" rule as the ticket toggle just above — an idempotent
                # re-run of an already-advanced team shouldn't re-mail anyone.
                if send_welcome_email and is_new_registration:
                    await send_registration_onboarding_email(
                        db, user=user, registration=registration, cohort=to_cohort,
                    )
            await assign_lms_program(db, user_id=user.id, cohort_id=to_cohort_id)

            if to_team is None:
                to_team = await create_team(db, name=team.name, created_by=user.id, cohort_id=to_cohort_id, member_ids=[user.id])
            elif user.id not in await team_member_ids(db, team_id=to_team.id):
                await join_team(db, team_id=to_team.id, user_id=user.id)

            user_attachments = []
            if attach_excuse_letter:
                if excuse_letter_mode in ("individual", "both"):
                    try:
                        indiv_bytes = await build_team_excuse_letter_pdf(
                            db, team=team, target_cohort=to_cohort, single_user_id=user.id, overrides=excuse_letter_overrides,
                        )
                        clean_uname = "".join(c for c in user.full_name if c.isalnum() or c in (" ", "-", "_")).strip()
                        user_attachments.append((f"{clean_uname}_Excuse_Letter.pdf", indiv_bytes, "pdf"))
                    except Exception as exc:
                        import logging
                        logging.getLogger(__name__).warning("Could not build individual excuse letter for %s: %s", user.full_name, exc)
                if excuse_letter_mode in ("team", "both") and team_letter_bytes:
                    user_attachments.append((f"{clean_tname}_Team_Excuse_Letter.pdf", team_letter_bytes, "pdf"))

            await _congrats_email(
                user, team_name=team.name, to_cohort_name=to_cohort.name,
                attachments=user_attachments if user_attachments else None,
            )
            advanced += 1

        if to_team is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Team '{team.name}' has no members to advance")
        from app.services.lms.program import sync_team_mission_runs
        await sync_team_mission_runs(db, team=to_team)
        results.append(TeamAdvanceResult(
            team_id=team.id, team_name=team.name, to_team_id=to_team.id, members_advanced=advanced,
            new_registration_ids=new_registration_ids,
        ))

    return results


def results_as_dicts(results: list[TeamAdvanceResult]) -> list[dict]:
    return [asdict(r) for r in results]

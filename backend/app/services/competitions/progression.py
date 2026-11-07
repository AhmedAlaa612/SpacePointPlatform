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


async def build_team_excuse_letter_pdf(
    db: AsyncSession,
    *,
    team: Team,
    target_cohort: Cohort,
    single_user_id: uuid.UUID | None = None,
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

        sid = user.student_id or (contact.student_id if contact else None)
        if not sid and user.card_number:
            sid = f"SP-ST-{user.card_number:04d}-UAE"

        if contact and contact.organization_id and not institution_name:
            org = await db.get(Organization, contact.organization_id)
            if org:
                institution_name = org.name

        m_dict = {
            "name": user.full_name,
            "student_id": sid or "—",
        }
        members_data.append(m_dict)
        if single_user_id and user.id == single_user_id:
            single_student_data = m_dict

    if target_cohort.starts_on and target_cohort.ends_on:
        days = (target_cohort.ends_on - target_cohort.starts_on).days + 1
        dates_text = f"{target_cohort.starts_on.strftime('%d %B %Y')} – {target_cohort.ends_on.strftime('%d %B %Y')} (all {days} days)"
    elif target_cohort.starts_on:
        dates_text = target_cohort.starts_on.strftime('%d %B %Y')
    else:
        dates_text = "Competition On-site Showcase Period"

    location_text = target_cohort.location or "Dubai, United Arab Emirates"
    if target_cohort.location_id:
        from app.models.inventory.location import Location
        loc_obj = await db.get(Location, target_cohort.location_id)
        if loc_obj:
            location_text = f"{loc_obj.name}, {location_text}" if target_cohort.location else loc_obj.name

    event_name = target_cohort.name

    return generate_excuse_letter_pdf(
        team_name=team.name,
        institution_name=institution_name,
        members=members_data,
        event_name=event_name,
        dates_text=dates_text,
        location_text=location_text,
        single_student=single_student_data,
    )


async def advance_teams(
    db: AsyncSession, *, team_ids: list[uuid.UUID], from_cohort_id: uuid.UUID, to_cohort_id: uuid.UUID,
    send_welcome_email: bool = True,
    attach_excuse_letter: bool = False,
) -> list[TeamAdvanceResult]:
    """Idempotent per team: re-running with a team that's already advanced
    just re-resolves its existing target-cohort Team/Registrations rather
    than erroring or duplicating — same "a later call just confirms what's
    already true" posture `join_team`/`assign_lms_program` already have."""
    to_cohort = await db.get(Cohort, to_cohort_id)
    if to_cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Target cohort not found")

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

        excuse_attachments = None
        if attach_excuse_letter:
            try:
                letter_bytes = await build_team_excuse_letter_pdf(db, team=team, target_cohort=to_cohort)
                clean_tname = "".join(c for c in team.name if c.isalnum() or c in (" ", "-", "_")).strip()
                excuse_attachments = [(f"{clean_tname}_University_Excuse_Letter.pdf", letter_bytes, "pdf")]
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning("Could not build excuse letter for team %s: %s", team.name, exc)

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

            await _congrats_email(
                user, team_name=team.name, to_cohort_name=to_cohort.name, attachments=excuse_attachments,
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

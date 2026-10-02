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


async def _congrats_email(user: User, *, team_name: str, to_cohort_name: str) -> None:
    await try_send_email(
        user.email, CONGRATS_SUBJECT,
        (
            f"<p>Hi {user.full_name},</p>"
            f"<p>Congratulations — <b>{team_name}</b> has advanced to <b>{to_cohort_name}</b>! "
            "Log in to see what's next on your checklist.</p>"
            "<p>— SpacePoint</p>"
        ),
        html=True,
    )


async def advance_teams(
    db: AsyncSession, *, team_ids: list[uuid.UUID], from_cohort_id: uuid.UUID, to_cohort_id: uuid.UUID,
    send_welcome_email: bool = True,
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

            await _congrats_email(user, team_name=team.name, to_cohort_name=to_cohort.name)
            advanced += 1

        if to_team is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Team '{team.name}' has no members to advance")
        results.append(TeamAdvanceResult(
            team_id=team.id, team_name=team.name, to_team_id=to_team.id, members_advanced=advanced,
            new_registration_ids=new_registration_ids,
        ))

    return results


def results_as_dicts(results: list[TeamAdvanceResult]) -> list[dict]:
    return [asdict(r) for r in results]

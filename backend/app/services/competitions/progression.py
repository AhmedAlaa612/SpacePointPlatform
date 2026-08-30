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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_template import EmailTemplate
from app.models.sessions.cohort import Cohort
from app.models.sessions.registration import Registration
from app.models.team import Team
from app.models.user import User
from app.services.email_templates import fetch_template, render_and_send
from app.services.lms.program import assign_lms_program
from app.services.sessions.registration import register
from app.services.teams import create_team, join_team, team_member_ids


@dataclass
class TeamAdvanceResult:
    team_id: uuid.UUID
    team_name: str
    to_team_id: uuid.UUID
    members_advanced: int


async def _congrats_email(
    db: AsyncSession, user: User, *, team_name: str, to_cohort_name: str, template: EmailTemplate | None,
) -> None:
    await render_and_send(
        db, key="competition_team_advanced", to=user.email,
        placeholders={"name": user.full_name, "team_name": team_name, "to_cohort_name": to_cohort_name},
        template=template,
    )


async def advance_teams(
    db: AsyncSession, *, team_ids: list[uuid.UUID], from_cohort_id: uuid.UUID, to_cohort_id: uuid.UUID,
) -> list[TeamAdvanceResult]:
    """Idempotent per team: re-running with a team that's already advanced
    just re-resolves its existing target-cohort Team/Registrations rather
    than erroring or duplicating — same "a later call just confirms what's
    already true" posture `join_team`/`assign_lms_program` already have."""
    to_cohort = await db.get(Cohort, to_cohort_id)
    if to_cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Target cohort not found")

    congrats_template = await fetch_template(db, "competition_team_advanced")
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

        to_team = (await db.execute(
            select(Team).where(Team.cohort_id == to_cohort_id, Team.name == team.name)
        )).scalars().first()

        member_ids = await team_member_ids(db, team_id=team.id)
        advanced = 0
        for user_id in member_ids:
            user = await db.get(User, user_id)
            if user is None:
                continue

            if user.contact_id is not None:
                already_registered = await db.scalar(
                    select(Registration.id).where(
                        Registration.contact_id == user.contact_id, Registration.cohort_id == to_cohort_id,
                        Registration.status != "cancelled",
                    )
                )
                if not already_registered:
                    await register(
                        db, contact_id=user.contact_id, cohort_id=to_cohort_id, registered_via="import",
                        payment_status="waived",
                    )
            await assign_lms_program(db, user_id=user.id, cohort_id=to_cohort_id)

            if to_team is None:
                to_team = await create_team(db, name=team.name, created_by=user.id, cohort_id=to_cohort_id, member_ids=[user.id])
            elif user.id not in await team_member_ids(db, team_id=to_team.id):
                await join_team(db, team_id=to_team.id, user_id=user.id)

            await _congrats_email(db, user, team_name=team.name, to_cohort_name=to_cohort.name, template=congrats_template)
            advanced += 1

        if to_team is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Team '{team.name}' has no members to advance")
        results.append(TeamAdvanceResult(team_id=team.id, team_name=team.name, to_team_id=to_team.id, members_advanced=advanced))

    return results


def results_as_dicts(results: list[TeamAdvanceResult]) -> list[dict]:
    return [asdict(r) for r in results]

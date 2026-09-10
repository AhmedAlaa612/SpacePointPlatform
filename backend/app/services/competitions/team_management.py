"""Manual team management for ops (2026-08-26) — a hands-on complement to
the Roster import, not a replacement for it. Roster import is for the bulk
case (a whole tracker sheet at once); this is for the one-off corrections
that always come up afterward — a late signup, a team that needs splitting,
someone who switched teams — without re-uploading a whole sheet to change
one row.

Reuses the exact same identity/registration primitives Roster import uses
per row (`resolve_or_create_contact` -> `register` -> `sync_registration_lms`)
for "register a brand-new person and add them to a team" in one action, and
`services/teams.py`'s `join_team`/`leave_team` for plain membership changes.
Adds only what neither already had: rename, a guarded delete, and a
member-listing view with names/emails resolved.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.competitions.judging import CompetitionScore
from app.models.lms.program import LmsProgramTeamItemProgress
from app.models.sessions.cohort import Cohort
from app.models.sessions.registration import Registration
from app.models.team import Team
from app.models.user import User
from app.services.lms.ops_integration import sync_registration_lms
from app.services.sessions.registration import register
from app.services.spine.identity import resolve_or_create_contact
from app.services.teams import join_team, leave_team, team_member_ids, teams_for_cohort


async def create_empty_team(db: AsyncSession, *, cohort_id: uuid.UUID, name: str, created_by: uuid.UUID) -> Team:
    """Not `services/teams.py::create_team` — that always adds `created_by`
    as a member too, correct for a student self-forming a team but wrong
    here: an ops account creating a team shell for students to be added to
    afterward is not itself a competitor. `created_by` is still recorded
    for audit, just never turned into membership."""
    team = Team(id=uuid.uuid4(), name=name, cohort_id=cohort_id, created_by=created_by)
    db.add(team)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        raise HTTPException(409, detail="A team with this name already exists in this cohort")
    return team


async def list_teams_with_members(db: AsyncSession, *, cohort_id: uuid.UUID) -> list[dict]:
    teams = await teams_for_cohort(db, cohort_id=cohort_id)
    out = []
    for team in teams:
        member_ids = await team_member_ids(db, team_id=team.id)
        members = (
            (await db.execute(select(User).where(User.id.in_(member_ids)))).scalars().all()
            if member_ids else []
        )
        out.append({
            "id": team.id, "name": team.name, "cohort_id": team.cohort_id,
            "member_ids": [m.id for m in members],
            "member_names": [m.full_name for m in members],
            "member_emails": [m.email for m in members],
        })
    return out


async def rename_team(db: AsyncSession, *, team_id: uuid.UUID, name: str) -> Team:
    team = await db.get(Team, team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Team not found")
    team.name = name
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        raise HTTPException(409, detail="A team with this name already exists in this cohort")
    return team


async def delete_team(db: AsyncSession, *, team_id: uuid.UUID) -> None:
    """Refuses once the team has a judged score or any submitted checklist
    progress — both `competition_scores.team_id` and
    `lms_program_team_item_progress.team_id` CASCADE on delete, so deleting
    a team with either would silently erase evaluations or submissions
    rather than just the team grouping. Same reasoning as the judge-delete
    guard in `services/user.py::delete_user`."""
    team = await db.get(Team, team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Team not found")

    score_count = (await db.execute(
        select(func.count()).select_from(CompetitionScore).where(CompetitionScore.team_id == team_id)
    )).scalar_one()
    progress_count = (await db.execute(
        select(func.count()).select_from(LmsProgramTeamItemProgress)
        .where(LmsProgramTeamItemProgress.team_id == team_id)
    )).scalar_one()
    if score_count > 0 or progress_count > 0:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete a team that has already been scored or has submitted checklist "
                   "progress — remove its members instead, or leave it as a historical record.",
        )

    await db.delete(team)
    await db.flush()


async def add_existing_member(db: AsyncSession, *, team_id: uuid.UUID, user_id: uuid.UUID) -> None:
    if await db.get(Team, team_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Team not found")
    if await db.get(User, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
    await join_team(db, team_id=team_id, user_id=user_id)


async def register_and_add_member(
    db: AsyncSession, *, team_id: uuid.UUID, full_name: str, email: str,
    phone: str | None = None, school: str | None = None, send_welcome_email: bool = True,
) -> tuple[User, uuid.UUID]:
    """The single-row equivalent of Roster import's per-row logic — same
    find-or-create-contact -> register -> sync_registration_lms chain, so a
    person added this way is indistinguishable from one who came through
    the bulk sheet. Returns the registration id alongside the user so the
    caller can enqueue the ticket email the same way the roster import does.

    The account itself always gets created (`join_team` needs a real
    `user_id`) — `send_welcome_email=False` only suppresses the "Your
    SpacePoint learning account" notification, not the account."""
    team = await db.get(Team, team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Team not found")
    cohort = await db.get(Cohort, team.cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="This team has no cohort")

    contact, _ = await resolve_or_create_contact(
        db, full_name=full_name, phone=phone, email=email, contact_roles=["student"],
        role_event_source="desk", organization_name=school,
    )
    existing = (await db.execute(
        select(Registration).where(Registration.contact_id == contact.id, Registration.cohort_id == cohort.id)
    )).scalars().first()
    registration = existing or await register(
        db, contact_id=contact.id, cohort_id=cohort.id, registered_via="desk", payment_status="waived",
    )

    user = await sync_registration_lms(
        db, registration=registration, cohort=cohort, create_account=True,
        send_welcome_email=send_welcome_email,
    )
    if user is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Registered, but couldn't create a student account (email may already belong to a different account)",
        )
    await join_team(db, team_id=team_id, user_id=user.id)
    return user, registration.id


async def remove_member(db: AsyncSession, *, team_id: uuid.UUID, user_id: uuid.UUID) -> None:
    await leave_team(db, team_id=team_id, user_id=user_id)

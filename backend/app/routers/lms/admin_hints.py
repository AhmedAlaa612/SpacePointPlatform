"""Admin and Ops authoring endpoints for Interactive Card Hint Station."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.competitions.hint_station import (
    CohortHintCard,
    CohortHintChallenge,
)
from app.models.sessions.cohort import Cohort
from app.models.user import User
from app.schemas.hint_station import (
    CohortHintCardCreateIn,
    CohortHintCardOut,
    CohortHintCardUpdateIn,
    CohortHintChallengeCreateIn,
    CohortHintChallengeOut,
    CohortHintChallengeUpdateIn,
    CohortHintImportIn,
)
from app.services.competitions.hint_station import (
    fork_cohort_challenges,
    get_effective_cohort_challenges,
    get_program_challenges,
    import_cohort_challenges,
)
from app.services.missions.cohort_access import is_cohort_lms_editor

router = APIRouter(prefix="/lms/admin/hints", tags=["lms-hints-admin"])


def _require_ops_or_admin(user: User):
    # User is multi-role (see models/user.py role_values) — there is no single
    # `.role` attribute to compare against.
    if not any(r in user.role_values for r in ("admin", "operations")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Ops or admin privileges required")


async def _require_cohort_hint_access(db: AsyncSession, cohort_id: uuid.UUID, user: User) -> None:
    if any(r in user.role_values for r in ("admin", "operations")):
        return
    if await is_cohort_lms_editor(db, cohort_id=cohort_id, user=user):
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Ops, admin, or cohort LMS editor privileges required")


@router.get("/program/{program_id}", response_model=list[CohortHintChallengeOut])
async def list_program_challenges_admin(
    program_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """Lists authoring challenges on a program template."""
    # Includes full revealed_content of every hint — ops/admin only.
    _require_ops_or_admin(current)
    return await get_program_challenges(db, program_id=program_id)


@router.get("/cohort/{cohort_id}", response_model=list[CohortHintChallengeOut])
async def list_cohort_challenges_admin(
    cohort_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """Lists authoring challenges for a cohort (resolved from override or inherited baseline)."""
    await _require_cohort_hint_access(db, cohort_id, current)
    return await get_effective_cohort_challenges(
        db,
        cohort_id=cohort_id,
        user=None,
        team_id=None,
        is_authoring=True,
    )


@router.post("/cohort/{cohort_id}/fork", response_model=list[CohortHintChallengeOut])
async def fork_cohort_challenges_admin(
    cohort_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """Explicitly forks the parent program template into the cohort's own override rows."""
    await _require_cohort_hint_access(db, cohort_id, current)
    await fork_cohort_challenges(db, cohort_id=cohort_id)
    return await get_effective_cohort_challenges(
        db,
        cohort_id=cohort_id,
        user=None,
        team_id=None,
        is_authoring=True,
    )


@router.post("/challenges", response_model=CohortHintChallengeOut)
async def create_challenge(
    body: CohortHintChallengeCreateIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """Creates a new challenge under a program or cohort."""
    if body.owner_type == "cohort":
        await _require_cohort_hint_access(db, body.owner_id, current)
    else:
        _require_ops_or_admin(current)

    # If authoring on a cohort that currently inherits, fork first so the cohort gets its own rows
    if body.owner_type == "cohort":
        existing = (
            await db.execute(
                select(CohortHintChallenge).where(
                    CohortHintChallenge.owner_type == "cohort",
                    CohortHintChallenge.owner_id == body.owner_id,
                )
            )
        ).scalars().all()
        if not existing:
            await fork_cohort_challenges(db, cohort_id=body.owner_id)

    challenge = CohortHintChallenge(
        id=uuid.uuid4(),
        owner_type=body.owner_type,
        owner_id=body.owner_id,
        title=body.title,
        challenge_code=body.challenge_code,
        topic=body.topic,
        description=body.description,
        mission_statement=body.mission_statement,
        max_points=body.max_points,
        position=body.position,
        is_active=body.is_active,
    )
    db.add(challenge)
    await db.commit()
    await db.refresh(challenge)

    return CohortHintChallengeOut(
        id=challenge.id,
        owner_type=challenge.owner_type,
        owner_id=challenge.owner_id,
        title=challenge.title,
        challenge_code=challenge.challenge_code,
        topic=challenge.topic,
        description=challenge.description,
        mission_statement=challenge.mission_statement,
        max_points=challenge.max_points,
        position=challenge.position,
        is_active=challenge.is_active,
        created_at=challenge.created_at,
        cards=[],
        points_deducted=0,
        max_remaining_points=challenge.max_points,
    )


@router.put("/challenges/{challenge_id}", response_model=CohortHintChallengeOut)
async def update_challenge(
    challenge_id: uuid.UUID,
    body: CohortHintChallengeUpdateIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """Updates an existing challenge."""
    ch = await db.get(CohortHintChallenge, challenge_id)
    if ch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Challenge not found")
    if ch.owner_type == "cohort":
        await _require_cohort_hint_access(db, ch.owner_id, current)
    else:
        _require_ops_or_admin(current)

    if body.title is not None:
        ch.title = body.title
    if body.challenge_code is not None:
        ch.challenge_code = body.challenge_code
    if body.topic is not None:
        ch.topic = body.topic
    if body.description is not None:
        ch.description = body.description
    if body.mission_statement is not None:
        ch.mission_statement = body.mission_statement
    if body.max_points is not None:
        ch.max_points = body.max_points
    if body.position is not None:
        ch.position = body.position
    if body.is_active is not None:
        ch.is_active = body.is_active

    await db.commit()
    await db.refresh(ch)

    cards = (
        await db.execute(
            select(CohortHintCard)
            .where(CohortHintCard.challenge_id == ch.id)
            .order_by(CohortHintCard.unlock_order, CohortHintCard.position)
        )
    ).scalars().all()

    card_dtos = [
        CohortHintCardOut(
            id=c.id,
            challenge_id=c.challenge_id,
            level=c.level,
            level_label=c.level_label,
            badge_label=c.badge_label,
            title=c.title,
            teaser=c.teaser,
            revealed_content=c.revealed_content,
            point_deduction=c.point_deduction,
            unlock_order=c.unlock_order,
            position=c.position,
            created_at=c.created_at,
            is_revealed=False,
            is_locked=False,
        )
        for c in cards
    ]

    return CohortHintChallengeOut(
        id=ch.id,
        owner_type=ch.owner_type,
        owner_id=ch.owner_id,
        title=ch.title,
        challenge_code=ch.challenge_code,
        topic=ch.topic,
        description=ch.description,
        mission_statement=ch.mission_statement,
        max_points=ch.max_points,
        position=ch.position,
        is_active=ch.is_active,
        created_at=ch.created_at,
        cards=card_dtos,
        points_deducted=0,
        max_remaining_points=ch.max_points,
    )


@router.delete("/challenges/{challenge_id}")
async def delete_challenge(
    challenge_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """Deletes a challenge and its associated hint cards."""
    ch = await db.get(CohortHintChallenge, challenge_id)
    if ch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Challenge not found")
    if ch.owner_type == "cohort":
        await _require_cohort_hint_access(db, ch.owner_id, current)
    else:
        _require_ops_or_admin(current)

    await db.delete(ch)
    await db.commit()
    return {"id": str(challenge_id), "deleted": True}


@router.post("/challenges/{challenge_id}/cards", response_model=CohortHintCardOut)
async def create_hint_card(
    challenge_id: uuid.UUID,
    body: CohortHintCardCreateIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """Adds a hint card (Level 1, 2, or custom) to a challenge."""
    ch = await db.get(CohortHintChallenge, challenge_id)
    if ch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Challenge not found")
    if ch.owner_type == "cohort":
        await _require_cohort_hint_access(db, ch.owner_id, current)
    else:
        _require_ops_or_admin(current)

    card = CohortHintCard(
        id=uuid.uuid4(),
        challenge_id=challenge_id,
        level=body.level,
        level_label=body.level_label,
        badge_label=body.badge_label,
        title=body.title,
        teaser=body.teaser,
        revealed_content=body.revealed_content,
        point_deduction=body.point_deduction,
        unlock_order=body.unlock_order,
        position=body.position,
    )
    db.add(card)
    await db.commit()
    await db.refresh(card)

    return CohortHintCardOut(
        id=card.id,
        challenge_id=card.challenge_id,
        level=card.level,
        level_label=card.level_label,
        badge_label=card.badge_label,
        title=card.title,
        teaser=card.teaser,
        revealed_content=card.revealed_content,
        point_deduction=card.point_deduction,
        unlock_order=card.unlock_order,
        position=card.position,
        created_at=card.created_at,
        is_revealed=False,
        is_locked=False,
    )


@router.put("/cards/{card_id}", response_model=CohortHintCardOut)
async def update_hint_card(
    card_id: uuid.UUID,
    body: CohortHintCardUpdateIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """Updates a hint card."""
    card = await db.get(CohortHintCard, card_id)
    if card is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Hint card not found")
    ch = await db.get(CohortHintChallenge, card.challenge_id)
    if ch and ch.owner_type == "cohort":
        await _require_cohort_hint_access(db, ch.owner_id, current)
    else:
        _require_ops_or_admin(current)

    if body.level is not None:
        card.level = body.level
    if body.level_label is not None:
        card.level_label = body.level_label
    if body.badge_label is not None:
        card.badge_label = body.badge_label
    if body.title is not None:
        card.title = body.title
    if body.teaser is not None:
        card.teaser = body.teaser
    if body.revealed_content is not None:
        card.revealed_content = body.revealed_content
    if body.point_deduction is not None:
        card.point_deduction = body.point_deduction
    if body.unlock_order is not None:
        card.unlock_order = body.unlock_order
    if body.position is not None:
        card.position = body.position

    await db.commit()
    await db.refresh(card)

    return CohortHintCardOut(
        id=card.id,
        challenge_id=card.challenge_id,
        level=card.level,
        level_label=card.level_label,
        badge_label=card.badge_label,
        title=card.title,
        teaser=card.teaser,
        revealed_content=card.revealed_content,
        point_deduction=card.point_deduction,
        unlock_order=card.unlock_order,
        position=card.position,
        created_at=card.created_at,
        is_revealed=False,
        is_locked=False,
    )


@router.delete("/cards/{card_id}")
async def delete_hint_card(
    card_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """Deletes a hint card."""
    card = await db.get(CohortHintCard, card_id)
    if card is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Hint card not found")
    ch = await db.get(CohortHintChallenge, card.challenge_id)
    if ch and ch.owner_type == "cohort":
        await _require_cohort_hint_access(db, ch.owner_id, current)
    else:
        _require_ops_or_admin(current)

    await db.delete(card)
    await db.commit()
    return {"id": str(card_id), "deleted": True}


@router.post("/cohort/{cohort_id}/import")
async def import_cohort_hints_admin(
    cohort_id: uuid.UUID,
    body: CohortHintImportIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """Clones challenges and cards from another program or cohort with append or replace."""
    await _require_cohort_hint_access(db, cohort_id, current)
    cloned = await import_cohort_challenges(
        db,
        target_owner_type="cohort",
        target_owner_id=cohort_id,
        source_type=body.source_type,
        source_id=body.source_id,
        challenge_ids=body.challenge_ids,
        replace_existing=body.replace_existing,
    )
    return {"cloned_count": cloned}


@router.post("/program/{program_id}/import")
async def import_program_hints_admin(
    program_id: uuid.UUID,
    body: CohortHintImportIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """Clones challenges and cards into a program template."""
    _require_ops_or_admin(current)
    cloned = await import_cohort_challenges(
        db,
        target_owner_type="program",
        target_owner_id=program_id,
        source_type=body.source_type,
        source_id=body.source_id,
        challenge_ids=body.challenge_ids,
        replace_existing=body.replace_existing,
    )
    return {"cloned_count": cloned}

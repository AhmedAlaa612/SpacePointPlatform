"""Interactive Card Hint Station service layer.
Handles resolution, inheritance, progressive reveal validation, and cloning.
"""

from datetime import datetime, timezone
from typing import Sequence
import uuid

from fastapi import HTTPException, status
from sqlalchemy import delete, exc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.competitions.hint_station import (
    CohortHintCard,
    CohortHintChallenge,
    CohortTeamHintReveal,
)
from app.models.lms.program import LmsProgramAssignment
from app.models.sessions.cohort import Cohort
from app.models.team import Team, TeamMember
from app.models.user import User
from app.schemas.hint_station import (
    CohortHintCardCreateIn,
    CohortHintCardOut,
    CohortHintCardUpdateIn,
    CohortHintChallengeCreateIn,
    CohortHintChallengeOut,
    CohortHintChallengeUpdateIn,
    CohortHintJudgingSummaryOut,
    HintRevealAuditOut,
    IndividualHintJudgingSummaryOut,
    StudentHintStationOut,
    TeamHintJudgingSummaryOut,
)


# ── Challenge & Card Queries ────────────────────────────────────────────────

async def get_effective_cohort_challenges(
    db: AsyncSession,
    *,
    cohort_id: uuid.UUID,
    user: User | None = None,
    team_id: uuid.UUID | None = None,
    is_authoring: bool = False,
) -> list[CohortHintChallengeOut]:
    """Resolves challenges for a cohort. Checks cohort override first, falls back to program."""
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        return []

    # 1. Query cohort-specific challenges
    challenges = (
        await db.execute(
            select(CohortHintChallenge)
            .where(
                CohortHintChallenge.owner_type == "cohort",
                CohortHintChallenge.owner_id == cohort_id,
            )
            .order_by(CohortHintChallenge.position, CohortHintChallenge.created_at)
        )
    ).scalars().all()

    # 2. Fall back to program baseline template if no cohort-level challenges exist
    if not challenges and cohort.program_id:
        challenges = (
            await db.execute(
                select(CohortHintChallenge)
                .where(
                    CohortHintChallenge.owner_type == "program",
                    CohortHintChallenge.owner_id == cohort.program_id,
                )
                .order_by(CohortHintChallenge.position, CohortHintChallenge.created_at)
            )
        ).scalars().all()

    if not challenges:
        return []

    challenge_ids = [c.id for c in challenges]

    # 3. Load all cards for these challenges
    cards_res = (
        await db.execute(
            select(CohortHintCard)
            .where(CohortHintCard.challenge_id.in_(challenge_ids))
            .order_by(CohortHintCard.unlock_order, CohortHintCard.position)
        )
    ).scalars().all()

    cards_by_challenge: dict[uuid.UUID, list[CohortHintCard]] = {}
    for c in cards_res:
        cards_by_challenge.setdefault(c.challenge_id, []).append(c)

    # 4. Load reveal logs if user or team is given
    reveals_by_card: dict[uuid.UUID, CohortTeamHintReveal] = {}
    revealer_names: dict[uuid.UUID, str] = {}

    if team_id is not None or user is not None:
        reveal_query = select(CohortTeamHintReveal).where(
            CohortTeamHintReveal.cohort_id == cohort_id,
            CohortTeamHintReveal.challenge_id.in_(challenge_ids),
        )
        if team_id is not None:
            reveal_query = reveal_query.where(CohortTeamHintReveal.team_id == team_id)
        elif user is not None:
            reveal_query = reveal_query.where(
                CohortTeamHintReveal.team_id.is_(None),
                CohortTeamHintReveal.user_id == user.id,
            )

        reveals = (await db.execute(reveal_query)).scalars().all()
        revealer_ids = {r.revealed_by_user_id for r in reveals if r.revealed_by_user_id}
        if revealer_ids:
            users_res = (
                await db.execute(select(User).where(User.id.in_(revealer_ids)))
            ).scalars().all()
            for u in users_res:
                name = u.full_name or u.email
                revealer_names[u.id] = name

        for r in reveals:
            reveals_by_card[r.hint_card_id] = r

    # 5. Build DTOs with progressive lock state calculation
    result: list[CohortHintChallengeOut] = []
    for ch in challenges:
        ch_cards = cards_by_challenge.get(ch.id, [])
        card_dtos: list[CohortHintCardOut] = []
        ch_deduction = 0

        prev_revealed = True  # Level 1 (lowest unlock_order) is initially unlocked
        for card in ch_cards:
            reveal = reveals_by_card.get(card.id)
            is_rev = reveal is not None
            # Locked if prior level card was not revealed yet
            is_locked = not prev_revealed if not is_rev else False

            if is_rev and reveal is not None:
                ch_deduction += reveal.points_deducted

            revealed_by_name = None
            if reveal and reveal.revealed_by_user_id:
                revealed_by_name = revealer_names.get(reveal.revealed_by_user_id)

            card_dtos.append(
                CohortHintCardOut(
                    id=card.id,
                    challenge_id=card.challenge_id,
                    level=card.level,
                    level_label=card.level_label,
                    badge_label=card.badge_label,
                    title=card.title,
                    teaser=card.teaser,
                    # Conceal revealed content from student until unlocked
                    revealed_content=card.revealed_content if (is_rev or is_authoring) else None,
                    point_deduction=card.point_deduction,
                    unlock_order=card.unlock_order,
                    position=card.position,
                    created_at=card.created_at,
                    is_revealed=is_rev,
                    is_locked=is_locked,
                    revealed_at=reveal.revealed_at if reveal else None,
                    revealed_by_name=revealed_by_name,
                )
            )
            prev_revealed = is_rev

        remaining_pts = max(0, ch.max_points - ch_deduction)
        result.append(
            CohortHintChallengeOut(
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
                points_deducted=ch_deduction,
                max_remaining_points=remaining_pts,
            )
        )

    return result


async def get_program_challenges(
    db: AsyncSession,
    *,
    program_id: uuid.UUID,
) -> list[CohortHintChallengeOut]:
    """Returns challenges configured directly on the program baseline template."""
    challenges = (
        await db.execute(
            select(CohortHintChallenge)
            .where(
                CohortHintChallenge.owner_type == "program",
                CohortHintChallenge.owner_id == program_id,
            )
            .order_by(CohortHintChallenge.position, CohortHintChallenge.created_at)
        )
    ).scalars().all()

    if not challenges:
        return []

    challenge_ids = [c.id for c in challenges]
    cards = (
        await db.execute(
            select(CohortHintCard)
            .where(CohortHintCard.challenge_id.in_(challenge_ids))
            .order_by(CohortHintCard.unlock_order, CohortHintCard.position)
        )
    ).scalars().all()

    cards_by_challenge: dict[uuid.UUID, list[CohortHintCard]] = {}
    for c in cards:
        cards_by_challenge.setdefault(c.challenge_id, []).append(c)

    result: list[CohortHintChallengeOut] = []
    for ch in challenges:
        ch_cards = cards_by_challenge.get(ch.id, [])
        card_dtos = [
            CohortHintCardOut(
                id=c.id,
                challenge_id=c.challenge_id,
                level=c.level,
                level_label=c.level_label,
                badge_label=c.badge_label,
                title=c.title,
                teaser=c.teaser,
                revealed_content=c.revealed_content,  # Authoring always sees full content
                point_deduction=c.point_deduction,
                unlock_order=c.unlock_order,
                position=c.position,
                created_at=c.created_at,
                is_revealed=False,
                is_locked=False,
            )
            for c in ch_cards
        ]
        result.append(
            CohortHintChallengeOut(
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
        )
    return result


# ── Fork-on-Write ───────────────────────────────────────────────────────────

async def fork_cohort_challenges(
    db: AsyncSession,
    *,
    cohort_id: uuid.UUID,
) -> list[CohortHintChallenge]:
    """If cohort does not have custom challenges, deep copies parent program challenges into cohort."""
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")

    existing = (
        await db.execute(
            select(CohortHintChallenge).where(
                CohortHintChallenge.owner_type == "cohort",
                CohortHintChallenge.owner_id == cohort_id,
            )
        )
    ).scalars().all()

    if existing:
        return list(existing)

    if not cohort.program_id:
        return []

    program_challenges = (
        await db.execute(
            select(CohortHintChallenge).where(
                CohortHintChallenge.owner_type == "program",
                CohortHintChallenge.owner_id == cohort.program_id,
            )
        )
    ).scalars().all()

    if not program_challenges:
        return []

    forked: list[CohortHintChallenge] = []
    for pch in program_challenges:
        new_ch_id = uuid.uuid4()
        ch_copy = CohortHintChallenge(
            id=new_ch_id,
            owner_type="cohort",
            owner_id=cohort_id,
            title=pch.title,
            challenge_code=pch.challenge_code,
            topic=pch.topic,
            description=pch.description,
            mission_statement=pch.mission_statement,
            max_points=pch.max_points,
            position=pch.position,
            is_active=pch.is_active,
        )
        db.add(ch_copy)

        cards = (
            await db.execute(
                select(CohortHintCard).where(CohortHintCard.challenge_id == pch.id)
            )
        ).scalars().all()

        for card in cards:
            card_copy = CohortHintCard(
                id=uuid.uuid4(),
                challenge_id=new_ch_id,
                level=card.level,
                level_label=card.level_label,
                badge_label=card.badge_label,
                title=card.title,
                teaser=card.teaser,
                revealed_content=card.revealed_content,
                point_deduction=card.point_deduction,
                unlock_order=card.unlock_order,
                position=card.position,
            )
            db.add(card_copy)

        forked.append(ch_copy)

    await db.commit()
    return forked


# ── Reveal Operations ───────────────────────────────────────────────────────

async def reveal_hint_card(
    db: AsyncSession,
    *,
    cohort_id: uuid.UUID,
    card_id: uuid.UUID,
    user: User,
    team_id: uuid.UUID | None = None,
) -> CohortHintCardOut:
    """Enforces prerequisite unlock order and records team deduction."""
    card = await db.get(CohortHintCard, card_id)
    if card is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Hint card not found")

    challenge = await db.get(CohortHintChallenge, card.challenge_id)
    if challenge is None or not challenge.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Challenge is inactive or unavailable")

    # Check if already revealed
    existing_query = select(CohortTeamHintReveal).where(
        CohortTeamHintReveal.cohort_id == cohort_id,
        CohortTeamHintReveal.hint_card_id == card_id,
    )
    if team_id is not None:
        existing_query = existing_query.where(CohortTeamHintReveal.team_id == team_id)
    else:
        existing_query = existing_query.where(
            CohortTeamHintReveal.team_id.is_(None),
            CohortTeamHintReveal.user_id == user.id,
        )

    existing = await db.scalar(existing_query)
    if existing is not None:
        revealer_name = user.full_name or user.email
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
            is_revealed=True,
            is_locked=False,
            revealed_at=existing.revealed_at,
            revealed_by_name=revealer_name,
        )

    # Prerequisite verification: must have revealed lower unlock_order in this challenge
    if card.unlock_order > 1:
        prev_card = await db.scalar(
            select(CohortHintCard).where(
                CohortHintCard.challenge_id == card.challenge_id,
                CohortHintCard.unlock_order == card.unlock_order - 1,
            )
        )
        if prev_card is not None:
            prev_rev_query = select(CohortTeamHintReveal).where(
                CohortTeamHintReveal.cohort_id == cohort_id,
                CohortTeamHintReveal.hint_card_id == prev_card.id,
            )
            if team_id is not None:
                prev_rev_query = prev_rev_query.where(CohortTeamHintReveal.team_id == team_id)
            else:
                prev_rev_query = prev_rev_query.where(
                    CohortTeamHintReveal.team_id.is_(None),
                    CohortTeamHintReveal.user_id == user.id,
                )
            prev_rev = await db.scalar(prev_rev_query)
            if prev_rev is None:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f"Unlock {prev_card.level_label} first before revealing this hint.",
                )

    # Atomically create the reveal record. A teammate racing this request
    # (both pass the "already revealed?" check above) hits the partial
    # unique indexes added in the 7ce8193a4b13 migration — treat the loser
    # as idempotent: its card is already revealed, return the same payload
    # the winner returns, and only one deduction lands.
    now = datetime.now(timezone.utc)
    reveal = CohortTeamHintReveal(
        id=uuid.uuid4(),
        cohort_id=cohort_id,
        team_id=team_id,
        user_id=user.id if team_id is None else None,
        challenge_id=card.challenge_id,
        hint_card_id=card.id,
        revealed_by_user_id=user.id,
        points_deducted=card.point_deduction,
        revealed_at=now,
    )
    db.add(reveal)
    try:
        await db.commit()
    except exc.IntegrityError:
        await db.rollback()
        existing = await db.scalar(existing_query)
        if existing is not None:
            now = existing.revealed_at or now

    revealer_name = user.full_name or user.email
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
        is_revealed=True,
        is_locked=False,
        revealed_at=now,
        revealed_by_name=revealer_name,
    )


# ── Import & Clone Operations ───────────────────────────────────────────────

async def import_cohort_challenges(
    db: AsyncSession,
    *,
    target_owner_type: str,  # "program" | "cohort"
    target_owner_id: uuid.UUID,
    source_type: str,        # "program" | "cohort"
    source_id: uuid.UUID,
    challenge_ids: list[uuid.UUID] | None = None,
    replace_existing: bool = False,
) -> int:
    """Clones challenges and cards from a source program or cohort into target."""
    src_query = select(CohortHintChallenge).where(
        CohortHintChallenge.owner_type == source_type,
        CohortHintChallenge.owner_id == source_id,
    ).order_by(CohortHintChallenge.position)

    if challenge_ids:
        src_query = src_query.where(CohortHintChallenge.id.in_(challenge_ids))

    src_challenges = (await db.execute(src_query)).scalars().all()
    if not src_challenges:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No source challenges found to import")

    if replace_existing:
        # Delete existing target challenges and their cascading cards
        old_challenges = (
            await db.execute(
                select(CohortHintChallenge).where(
                    CohortHintChallenge.owner_type == target_owner_type,
                    CohortHintChallenge.owner_id == target_owner_id,
                )
            )
        ).scalars().all()
        for oc in old_challenges:
            await db.delete(oc)
        await db.flush()
        start_pos = 0
    else:
        max_pos = await db.scalar(
            select(func.coalesce(func.max(CohortHintChallenge.position), -1)).where(
                CohortHintChallenge.owner_type == target_owner_type,
                CohortHintChallenge.owner_id == target_owner_id,
            )
        )
        start_pos = (max_pos or 0) + 1

    cloned_count = 0
    for idx, sc in enumerate(src_challenges):
        new_ch_id = uuid.uuid4()
        ch_copy = CohortHintChallenge(
            id=new_ch_id,
            owner_type=target_owner_type,
            owner_id=target_owner_id,
            title=sc.title,
            challenge_code=sc.challenge_code,
            topic=sc.topic,
            description=sc.description,
            mission_statement=sc.mission_statement,
            max_points=sc.max_points,
            position=start_pos + idx,
            is_active=sc.is_active,
        )
        db.add(ch_copy)

        cards = (
            await db.execute(
                select(CohortHintCard).where(CohortHintCard.challenge_id == sc.id)
            )
        ).scalars().all()

        for card in cards:
            card_copy = CohortHintCard(
                id=uuid.uuid4(),
                challenge_id=new_ch_id,
                level=card.level,
                level_label=card.level_label,
                badge_label=card.badge_label,
                title=card.title,
                teaser=card.teaser,
                revealed_content=card.revealed_content,
                point_deduction=card.point_deduction,
                unlock_order=card.unlock_order,
                position=card.position,
            )
            db.add(card_copy)

        cloned_count += 1

    await db.commit()
    return cloned_count


# ── Judging Summary & Rehearsal Reset ───────────────────────────────────────

async def get_cohort_hint_judging_summary(
    db: AsyncSession,
    *,
    cohort_id: uuid.UUID,
) -> CohortHintJudgingSummaryOut:
    """Returns team-by-team and individual-by-individual hint usage summary and chronological reveal log."""
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")

    teams = (
        await db.execute(
            select(Team).where(Team.cohort_id == cohort_id).order_by(Team.name)
        )
    ).scalars().all()

    reveals = (
        await db.execute(
            select(CohortTeamHintReveal)
            .where(CohortTeamHintReveal.cohort_id == cohort_id)
            .order_by(CohortTeamHintReveal.revealed_at.desc())
        )
    ).scalars().all()

    # Load assigned students in this cohort so individual participants are listed even before revealing hints
    assigned_user_ids = set(
        (
            await db.execute(
                select(LmsProgramAssignment.user_id).where(LmsProgramAssignment.cohort_id == cohort_id)
            )
        ).scalars().all()
    )
    # Find which users are already on a team in this cohort
    team_ids = [t.id for t in teams]
    teamed_user_ids: set[uuid.UUID] = set()
    if team_ids:
        teamed_user_ids = set(
            (
                await db.execute(
                    select(TeamMember.user_id).where(TeamMember.team_id.in_(team_ids))
                )
            ).scalars().all()
        )

    # Preload challenges, cards, and user names
    challenge_ids = {r.challenge_id for r in reveals}
    challenges = {}
    if challenge_ids:
        ch_res = (
            await db.execute(
                select(CohortHintChallenge).where(CohortHintChallenge.id.in_(challenge_ids))
            )
        ).scalars().all()
        challenges = {c.id: c.title for c in ch_res}

    card_ids = {r.hint_card_id for r in reveals}
    cards = {}
    if card_ids:
        card_res = (
            await db.execute(
                select(CohortHintCard).where(CohortHintCard.id.in_(card_ids))
            )
        ).scalars().all()
        cards = {c.id: c for c in card_res}

    individual_reveal_user_ids = {r.user_id for r in reveals if r.team_id is None and r.user_id}
    solo_assigned_user_ids = assigned_user_ids - teamed_user_ids
    all_relevant_user_ids = (
        {r.revealed_by_user_id for r in reveals if r.revealed_by_user_id}
        | individual_reveal_user_ids
        | solo_assigned_user_ids
    )
    users_by_id: dict[uuid.UUID, User] = {}
    user_names: dict[uuid.UUID, str] = {}
    if all_relevant_user_ids:
        u_res = (
            await db.execute(select(User).where(User.id.in_(all_relevant_user_ids)))
        ).scalars().all()
        for u in u_res:
            users_by_id[u.id] = u
            user_names[u.id] = u.full_name or u.email

    team_reveals_map: dict[uuid.UUID, list[HintRevealAuditOut]] = {}
    user_reveals_map: dict[uuid.UUID, list[HintRevealAuditOut]] = {}
    for r in reveals:
        c = cards.get(r.hint_card_id)
        audit_entry = HintRevealAuditOut(
            id=r.id,
            challenge_id=r.challenge_id,
            challenge_title=challenges.get(r.challenge_id, "Challenge"),
            hint_card_id=r.hint_card_id,
            level=c.level if c else 1,
            level_label=c.level_label if c else "Hint",
            card_title=c.title if c else "Hint",
            points_deducted=r.points_deducted,
            revealed_at=r.revealed_at,
            revealed_by_name=user_names.get(r.revealed_by_user_id) if r.revealed_by_user_id else None,
        )
        if r.team_id:
            team_reveals_map.setdefault(r.team_id, []).append(audit_entry)
        elif r.user_id:
            user_reveals_map.setdefault(r.user_id, []).append(audit_entry)

    team_summaries: list[TeamHintJudgingSummaryOut] = []
    total_cohort_hints = 0
    total_cohort_deductions = 0

    for t in teams:
        t_revs = team_reveals_map.get(t.id, [])
        t_deduction = sum(r.points_deducted for r in t_revs)
        total_cohort_hints += len(t_revs)
        total_cohort_deductions += t_deduction
        team_summaries.append(
            TeamHintJudgingSummaryOut(
                team_id=t.id,
                team_name=t.name,
                team_code=t.join_code,
                hints_used=len(t_revs),
                total_points_deducted=t_deduction,
                reveals=t_revs,
            )
        )

    individual_uids = sorted(
        individual_reveal_user_ids | solo_assigned_user_ids,
        key=lambda uid: (user_names.get(uid, "") or "").lower(),
    )
    individual_summaries: list[IndividualHintJudgingSummaryOut] = []
    for uid in individual_uids:
        u = users_by_id.get(uid)
        u_revs = user_reveals_map.get(uid, [])
        u_deduction = sum(r.points_deducted for r in u_revs)
        total_cohort_hints += len(u_revs)
        total_cohort_deductions += u_deduction
        individual_summaries.append(
            IndividualHintJudgingSummaryOut(
                user_id=uid,
                user_name=user_names.get(uid, "Student"),
                user_email=u.email if u else None,
                hints_used=len(u_revs),
                total_points_deducted=u_deduction,
                reveals=u_revs,
            )
        )

    return CohortHintJudgingSummaryOut(
        cohort_id=cohort.id,
        cohort_name=cohort.name,
        total_hints_revealed=total_cohort_hints,
        total_points_deducted=total_cohort_deductions,
        teams=team_summaries,
        individuals=individual_summaries,
    )


async def reset_team_hint_reveals(
    db: AsyncSession,
    *,
    cohort_id: uuid.UUID,
    team_id: uuid.UUID,
) -> int:
    """Resets reveals for a team for testing/dry-run rehearsal."""
    res = await db.execute(
        delete(CohortTeamHintReveal).where(
            CohortTeamHintReveal.cohort_id == cohort_id,
            CohortTeamHintReveal.team_id == team_id,
        )
    )
    await db.commit()
    return res.rowcount or 0


async def reset_user_hint_reveals(
    db: AsyncSession,
    *,
    cohort_id: uuid.UUID,
    user_id: uuid.UUID,
) -> int:
    """Resets individual (team-less) reveals for a user for testing/dry-run rehearsal."""
    res = await db.execute(
        delete(CohortTeamHintReveal).where(
            CohortTeamHintReveal.cohort_id == cohort_id,
            CohortTeamHintReveal.team_id.is_(None),
            CohortTeamHintReveal.user_id == user_id,
        )
    )
    await db.commit()
    return res.rowcount or 0

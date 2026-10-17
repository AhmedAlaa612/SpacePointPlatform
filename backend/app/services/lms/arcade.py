from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lms.arcade_game import ArcadeGame, ArcadeGameAttempt
from app.models.lms.program import LmsProgramAssignment, LmsProgramItem, LmsProgramItemProgress
from app.schemas.lms_arcade import (
    ArcadeAttemptOut, ArcadeAttemptSubmitIn, ArcadeGameCatalogOut, ArcadeModeBestOut,
)
from app.services.lms.arcade_data import ARCADE_GAMES
from app.services.lms.points import award_points

ARCADE_POINTS_SOURCE = "arcade"


async def ensure_arcade_games_seeded(db: AsyncSession, *, force: bool = False) -> int:
    """Ensure all 51 SpacePoint Mission Arcade games exist in the database."""
    count = await db.scalar(select(func.count(ArcadeGame.id)))
    if count and count >= len(ARCADE_GAMES) and not force:
        return 0

    seeded = 0
    for spec in ARCADE_GAMES:
        existing = await db.scalar(select(ArcadeGame).where(ArcadeGame.game_key == spec["game_key"]))
        if existing is None:
            db.add(ArcadeGame(id=uuid.uuid4(), is_active=True, **spec))
            seeded += 1
        elif force:
            for k, v in spec.items():
                setattr(existing, k, v)
            seeded += 1

    if seeded > 0:
        await db.commit()
    return seeded


async def list_games_for_user(db: AsyncSession, *, user_id: uuid.UUID) -> list[ArcadeGameCatalogOut]:
    games = (await db.execute(
        select(ArcadeGame).where(ArcadeGame.is_active.is_(True)).order_by(ArcadeGame.position, ArcadeGame.title)
    )).scalars().all()
    if not games:
        await ensure_arcade_games_seeded(db)
        games = (await db.execute(
            select(ArcadeGame).where(ArcadeGame.is_active.is_(True)).order_by(ArcadeGame.position, ArcadeGame.title)
        )).scalars().all()
    if not games:
        return []

    # Aggregate best score, pass status, and attempt count per (game_id, mode) for this user
    stats_rows = (await db.execute(
        select(
            ArcadeGameAttempt.game_id,
            ArcadeGameAttempt.mode,
            func.max(ArcadeGameAttempt.score).label("best_score"),
            func.bool_or(ArcadeGameAttempt.passed).label("ever_passed"),
            func.count(ArcadeGameAttempt.id).label("attempts_count"),
        )
        .where(ArcadeGameAttempt.user_id == user_id)
        .group_by(ArcadeGameAttempt.game_id, ArcadeGameAttempt.mode)
    )).all()

    stats_map: dict[tuple[uuid.UUID, str], ArcadeModeBestOut] = {}
    for row in stats_rows:
        stats_map[(row.game_id, row.mode)] = ArcadeModeBestOut(
            best_score=int(row.best_score or 0),
            passed=bool(row.ever_passed),
            attempts_count=int(row.attempts_count or 0),
        )

    out: list[ArcadeGameCatalogOut] = []
    for g in games:
        item = ArcadeGameCatalogOut.model_validate(g)
        item.explorer = stats_map.get((g.id, "explorer"), ArcadeModeBestOut())
        item.engineer = stats_map.get((g.id, "engineer"), ArcadeModeBestOut())
        out.append(item)
    return out


async def record_arcade_attempt(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    game_key: str,
    body: ArcadeAttemptSubmitIn,
) -> ArcadeAttemptOut:
    game = await db.scalar(
        select(ArcadeGame).where(ArcadeGame.game_key == game_key, ArcadeGame.is_active.is_(True))
    )
    if game is None:
        await ensure_arcade_games_seeded(db)
        game = await db.scalar(
            select(ArcadeGame).where(ArcadeGame.game_key == game_key, ArcadeGame.is_active.is_(True))
        )
    if game is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Arcade game not found")

    cohort_id: uuid.UUID | None = None
    if body.assignment_id is not None:
        assignment = await db.get(LmsProgramAssignment, body.assignment_id)
        if assignment is not None and assignment.user_id == user_id:
            cohort_id = assignment.cohort_id

    max_no = await db.scalar(
        select(func.max(ArcadeGameAttempt.attempt_no)).where(
            ArcadeGameAttempt.user_id == user_id,
            ArcadeGameAttempt.game_id == game.id,
            ArcadeGameAttempt.mode == body.mode,
        )
    )
    # Enforce server-side pass rule matching the arcade formula (accuracy >= 70% and game passed flag)
    passed = bool(body.passed and body.accuracy >= 70)

    attempt = ArcadeGameAttempt(
        id=uuid.uuid4(),
        game_id=game.id,
        user_id=user_id,
        program_item_id=body.program_item_id,
        cohort_id=cohort_id,
        mode=body.mode,
        score=body.score,
        accuracy=body.accuracy,
        passed=passed,
        elapsed_seconds=body.elapsed_seconds,
        attempt_no=(max_no or 0) + 1,
        notes=[n.model_dump() for n in body.notes],
        completed_at=datetime.now(timezone.utc),
    )
    db.add(attempt)
    await db.flush()

    points_awarded = 0
    if passed:
        pts = game.points_engineer if body.mode == "engineer" else game.points_explorer
        event = await award_points(
            db,
            user_id=user_id,
            source=ARCADE_POINTS_SOURCE,
            points=pts,
            idempotency_key=f"arcade:{game.id}:{body.mode}",
            ref={"game_id": str(game.id), "game_key": game.game_key, "mode": body.mode, "attempt_id": str(attempt.id)},
        )
        if event is not None:
            points_awarded = pts

    # If the student has any LMS Program checklist items referencing this game,
    # eagerly refresh their progress rows so they flip to 'done' immediately.
    if passed:
        from app.services.lms.program import refresh_item_progress
        matching_rows = (await db.execute(
            select(LmsProgramItemProgress, LmsProgramItem)
            .join(LmsProgramAssignment, LmsProgramAssignment.id == LmsProgramItemProgress.assignment_id)
            .join(LmsProgramItem, LmsProgramItem.id == LmsProgramItemProgress.item_id)
            .where(
                LmsProgramAssignment.user_id == user_id,
                LmsProgramItem.item_type == "arcade_game",
                LmsProgramItem.arcade_game_id == game.id,
            )
        )).all()
        for prog_row, prog_item in matching_rows:
            await refresh_item_progress(db, progress=prog_row, item=prog_item, user_id=user_id)

    await db.commit()
    await db.refresh(attempt)
    return ArcadeAttemptOut(
        id=attempt.id,
        game_id=game.id,
        game_key=game.game_key,
        game_title=game.title,
        mode=attempt.mode,
        score=attempt.score,
        accuracy=attempt.accuracy,
        passed=attempt.passed,
        elapsed_seconds=attempt.elapsed_seconds,
        attempt_no=attempt.attempt_no,
        points_awarded=points_awarded,
        notes=body.notes,
        completed_at=attempt.completed_at,
    )


async def get_best_attempt_for_user(
    db: AsyncSession, *, user_id: uuid.UUID, game_id: uuid.UUID, mode: str | None = None,
) -> ArcadeAttemptOut | None:
    game = await db.get(ArcadeGame, game_id)
    if game is None:
        return None
    stmt = select(ArcadeGameAttempt).where(
        ArcadeGameAttempt.user_id == user_id,
        ArcadeGameAttempt.game_id == game_id,
    )
    if mode and mode in ("explorer", "engineer"):
        stmt = stmt.where(ArcadeGameAttempt.mode == mode)
    stmt = stmt.order_by(ArcadeGameAttempt.passed.desc(), ArcadeGameAttempt.score.desc(), ArcadeGameAttempt.completed_at.desc()).limit(1)
    attempt = await db.scalar(stmt)
    if attempt is None:
        return None
    return ArcadeAttemptOut(
        id=attempt.id,
        game_id=game.id,
        game_key=game.game_key,
        game_title=game.title,
        mode=attempt.mode,
        score=attempt.score,
        accuracy=attempt.accuracy,
        passed=attempt.passed,
        elapsed_seconds=attempt.elapsed_seconds,
        attempt_no=attempt.attempt_no,
        points_awarded=0,
        notes=attempt.notes or [],
        completed_at=attempt.completed_at,
    )

"""Live games — run/participant/answer business logic (Live Games Phase
2C, 8-6; D8, D14, D15, D18).

Pure service layer, no HTTP/WS wiring here — 8-7 (instructor console)
and 8-8 (student flow) call these functions from their own routers and
broadcast the results over the WS layer 8-5 built. This file's own job
stops at "the database is correct and the ledger is correct."

Points integration goes through `services.lms.points.award_points` —
the same single choke point missions/quizzes already use (`source="game"`,
reserved for this exact purpose since the points-ledger model was
built). `idempotency_key` is `f"{run.id}:{question.id}"`, not just the
question id — a restart is a **new** `GameRun` row (D15), so the same
question answered again in the new run must be able to earn points
again; scoping the key by run is what makes that safe rather than
silently no-op'ing against the old run's already-used key.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.games.run import GameAnswer, GameParticipant, GameRun
from app.models.games.session_assignment import GameSessionAssignment, GameSessionQuestion
from app.models.user import User
from app.services.games.points import max_points_for
from app.services.games.scoring import score_answer
from app.services.lms.points import award_points

GAME_POINTS_SOURCE = "game"


async def create_run(db: AsyncSession, *, assignment: GameSessionAssignment, actor_id: uuid.UUID) -> GameRun:
    max_run_no = await db.scalar(
        select(func.max(GameRun.run_no)).where(GameRun.assignment_id == assignment.id)
    )
    run = GameRun(id=uuid.uuid4(), assignment_id=assignment.id, run_no=(max_run_no or 0) + 1, created_by=actor_id)
    db.add(run)
    await db.flush()
    return run


async def join_run(db: AsyncSession, *, run: GameRun, user: User, avatar: str | None = None) -> GameParticipant:
    existing = await db.scalar(
        select(GameParticipant).where(GameParticipant.run_id == run.id, GameParticipant.user_id == user.id)
    )
    if existing is not None:
        return existing
    participant = GameParticipant(
        id=uuid.uuid4(), run_id=run.id, user_id=user.id,
        nickname_snapshot=user.nickname or user.full_name, avatar=avatar,
    )
    db.add(participant)
    await db.flush()
    return participant


async def start_run(db: AsyncSession, *, run: GameRun) -> GameRun:
    if run.status != "lobby":
        raise ValueError(f"run {run.id} is not in lobby (status={run.status})")
    run.status = "live"
    run.current_question_position = 1
    run.started_at = datetime.now(timezone.utc)
    await db.flush()
    return run


async def get_current_question(db: AsyncSession, run: GameRun) -> GameSessionQuestion | None:
    if run.current_question_position is None:
        return None
    return await db.scalar(
        select(GameSessionQuestion).where(
            GameSessionQuestion.assignment_id == run.assignment_id,
            GameSessionQuestion.position == run.current_question_position,
        )
    )


async def advance_run(db: AsyncSession, *, run: GameRun) -> GameRun:
    """Moves to the next question by position, or ends the run once past
    the last one. D18's late-join / no-catch-up falls out of this for
    free — a student who joins mid-run simply has no GameAnswer rows for
    whatever positions already passed."""
    total = await db.scalar(
        select(func.count()).select_from(GameSessionQuestion).where(GameSessionQuestion.assignment_id == run.assignment_id)
    )
    next_position = (run.current_question_position or 0) + 1
    if next_position > (total or 0):
        run.status = "ended"
        run.current_question_position = None
        run.ended_at = datetime.now(timezone.utc)
    else:
        run.current_question_position = next_position
    await db.flush()
    return run


async def submit_answer(
    db: AsyncSession, *, run: GameRun, participant: GameParticipant, question: GameSessionQuestion,
    selected_option_index: int | None, elapsed_seconds: float,
) -> GameAnswer:
    """Idempotent — a participant answering the same question twice (a
    retried request, a double-click) returns the first recorded answer
    rather than re-grading or re-awarding."""
    existing = await db.scalar(
        select(GameAnswer).where(GameAnswer.participant_id == participant.id, GameAnswer.question_id == question.id)
    )
    if existing is not None:
        return existing

    is_correct = (
        selected_option_index is not None
        and 0 <= selected_option_index < len(question.options)
        and bool(question.options[selected_option_index].get("is_correct"))
    )
    assignment = await db.get(GameSessionAssignment, run.assignment_id)
    time_limit = question.time_limit_seconds or assignment.time_limit_seconds
    points = score_answer(
        is_correct=is_correct, max_points=max_points_for(question.points_mode),
        floor_pct=assignment.floor_pct, elapsed_seconds=elapsed_seconds, time_limit_seconds=time_limit,
    )

    answer = GameAnswer(
        id=uuid.uuid4(), participant_id=participant.id, question_id=question.id,
        selected_option_index=selected_option_index, is_correct=is_correct,
        elapsed_seconds=elapsed_seconds, points_awarded=points,
    )
    db.add(answer)
    await db.flush()

    if points > 0:
        await award_points(
            db, user_id=participant.user_id, source=GAME_POINTS_SOURCE, points=points,
            idempotency_key=f"{run.id}:{question.id}",
            ref={"run_id": str(run.id), "question_id": str(question.id), "points_mode": question.points_mode},
        )
    return answer


async def run_leaderboard(db: AsyncSession, run_id: uuid.UUID) -> list[dict]:
    """Nickname + avatar + score only — never the real name (D9); the
    real-name mapping is a separate staff-only lookup 8-7 builds. Scored
    off `SUM(points_awarded) WHERE reversed_at IS NULL` — never a cached
    total, so 8-9's reversal shows up here with nothing else to update."""
    score_col = func.coalesce(
        func.sum(GameAnswer.points_awarded).filter(GameAnswer.reversed_at.is_(None)), 0
    ).label("score")
    stmt = (
        select(GameParticipant.id, GameParticipant.nickname_snapshot, GameParticipant.avatar, score_col)
        .outerjoin(GameAnswer, GameAnswer.participant_id == GameParticipant.id)
        .where(GameParticipant.run_id == run_id)
        .group_by(GameParticipant.id)
        .order_by(score_col.desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        {"participant_id": r.id, "nickname": r.nickname_snapshot, "avatar": r.avatar, "score": int(r.score)}
        for r in rows
    ]

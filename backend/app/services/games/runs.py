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
from app.services.lms.points import award_points, reverse_points

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


async def count_questions(db: AsyncSession, assignment_id: uuid.UUID) -> int:
    return (
        await db.scalar(
            select(func.count()).select_from(GameSessionQuestion).where(GameSessionQuestion.assignment_id == assignment_id)
        )
    ) or 0


def is_blackout_active(*, current_question_position: int | None, total_questions: int, blackout_count: int) -> bool:
    """D10: the last N questions (blackout_count, default 3) hide the
    leaderboard from students — they still see their own score, just not
    rank or others'. The instructor sees everything regardless."""
    if current_question_position is None or blackout_count <= 0:
        return False
    return (total_questions - current_question_position) < blackout_count


async def advance_run(db: AsyncSession, *, run: GameRun) -> GameRun:
    """Moves to the next question by position, or ends the run once past
    the last one. D18's late-join / no-catch-up falls out of this for
    free — a student who joins mid-run simply has no GameAnswer rows for
    whatever positions already passed."""
    total = await count_questions(db, run.assignment_id)
    next_position = (run.current_question_position or 0) + 1
    if next_position > total:
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


async def end_run(db: AsyncSession, *, run: GameRun) -> GameRun:
    """Instructor's explicit End button (D19) — distinct from `advance_run`'s
    natural transition once the last question is passed."""
    run.status = "ended"
    run.current_question_position = None
    run.ended_at = datetime.now(timezone.utc)
    await db.flush()
    return run


async def _reverse_answers(db: AsyncSession, *, run_id: uuid.UUID, answers: list[GameAnswer]) -> None:
    now = datetime.now(timezone.utc)
    for answer in answers:
        participant = await db.get(GameParticipant, answer.participant_id)
        await reverse_points(
            db, user_id=participant.user_id, source=GAME_POINTS_SOURCE, points=answer.points_awarded,
            idempotency_key=f"{run_id}:{answer.question_id}:reversal",
            ref={"run_id": str(run_id), "question_id": str(answer.question_id) if answer.question_id else None},
        )
        answer.reversed_at = now
    await db.flush()


async def reverse_run_points(db: AsyncSession, *, run: GameRun) -> int:
    """D15/D17: reverses every not-yet-reversed positive-points answer in
    this run, for every participant, all-or-nothing (never split by which
    students are replaying) — new offsetting `point_events` rows, the
    original award rows untouched. Returns the count of answers reversed."""
    answers = (
        await db.execute(
            select(GameAnswer)
            .join(GameParticipant, GameAnswer.participant_id == GameParticipant.id)
            .where(
                GameParticipant.run_id == run.id,
                GameAnswer.points_awarded > 0,
                GameAnswer.reversed_at.is_(None),
            )
        )
    ).scalars().all()
    await _reverse_answers(db, run_id=run.id, answers=answers)
    return len(answers)


async def reverse_question_points(db: AsyncSession, *, run: GameRun, question_id: uuid.UUID) -> int:
    """D16/D17: reverses only the answers tied to one specific question
    within one specific run — the mid-game "delete an already-answered
    question" path. Every other question's points in the same run are
    untouched. Callers run this *before* actually deleting the question
    row. Returns the count of answers reversed."""
    answers = (
        await db.execute(
            select(GameAnswer)
            .join(GameParticipant, GameAnswer.participant_id == GameParticipant.id)
            .where(
                GameParticipant.run_id == run.id,
                GameAnswer.question_id == question_id,
                GameAnswer.points_awarded > 0,
                GameAnswer.reversed_at.is_(None),
            )
        )
    ).scalars().all()
    await _reverse_answers(db, run_id=run.id, answers=answers)
    return len(answers)


async def restart_run(db: AsyncSession, *, run: GameRun, actor_id: uuid.UUID) -> GameRun:
    """The single Restart action (D15) — always reverses every point this
    run has awarded so far, then starts a brand-new run (fresh run_no)
    against the assignment's current (possibly just-edited) question set.
    The old run's rows are never touched beyond `reversed_at`/`ended_at` —
    a full history of what was actually played survives, same "never
    destroy history" posture as everywhere else in this codebase."""
    await reverse_run_points(db, run=run)
    if run.status != "ended":
        run.status = "ended"
        run.current_question_position = None
        run.ended_at = datetime.now(timezone.utc)
        await db.flush()
    assignment = await db.get(GameSessionAssignment, run.assignment_id)
    return await create_run(db, assignment=assignment, actor_id=actor_id)


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


async def run_roster(db: AsyncSession, *, run: GameRun) -> list[dict]:
    """Instructor's live roster grid — nickname/avatar plus whether each
    participant has answered the currently-live question yet (2a's
    answered-count ring/grid)."""
    participants = (
        await db.execute(select(GameParticipant).where(GameParticipant.run_id == run.id).order_by(GameParticipant.joined_at))
    ).scalars().all()
    answered_ids: set[uuid.UUID] = set()
    question = await get_current_question(db, run)
    if question is not None and participants:
        answered_ids = set((
            await db.execute(
                select(GameAnswer.participant_id).where(
                    GameAnswer.question_id == question.id,
                    GameAnswer.participant_id.in_([p.id for p in participants]),
                )
            )
        ).scalars().all())
    return [
        {
            "participant_id": p.id, "nickname": p.nickname_snapshot, "avatar": p.avatar,
            "has_answered_current": p.id in answered_ids,
        }
        for p in participants
    ]


async def question_results(db: AsyncSession, *, run: GameRun, question: GameSessionQuestion) -> list[dict]:
    """Per-option counts + percentages for the between-questions results
    screen (2b) — how many participants (in this run) picked each option."""
    counts_by_index = dict((
        await db.execute(
            select(GameAnswer.selected_option_index, func.count())
            .join(GameParticipant, GameAnswer.participant_id == GameParticipant.id)
            .where(GameParticipant.run_id == run.id, GameAnswer.question_id == question.id)
            .group_by(GameAnswer.selected_option_index)
        )
    ).all())
    total = sum(counts_by_index.values())
    return [
        {
            "index": i, "text": opt["text"], "is_correct": opt["is_correct"],
            "count": counts_by_index.get(i, 0),
            "pct": round(counts_by_index.get(i, 0) / total * 100) if total else 0,
        }
        for i, opt in enumerate(question.options)
    ]

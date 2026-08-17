"""Live games — run/participant/answer business logic (Live Games Phase
2C, 8-6; D8, D14, D15, D18).

Pure service layer, no HTTP/WS wiring here — 8-7 (instructor console)
and 8-8 (student flow) call these functions from their own routers and
broadcast the results over the WS layer 8-5 built. This file's own job
stops at "the database is correct and the ledger is correct."

Points integration goes through `services.lms.points.award_points` —
the same single choke point missions/quizzes already use (`source="game"`,
reserved for this exact purpose since the points-ledger model was
built). `idempotency_key` is `f"{run.id}:{run.restart_no}:{question.id}"`,
not just the question id — a restart replays the same questions in the
same run (D15, revised), so the replay must be able to earn points again
after the first attempt's were reversed. Scoping the key by run *and*
restart count is what makes that safe rather than silently no-op'ing
against the already-used key from before the restart.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, update
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


async def get_or_create_open_run(db: AsyncSession, *, assignment: GameSessionAssignment, actor_id: uuid.UUID) -> GameRun:
    """Resumable-run fix — `open_run` used to call `create_run` unconditionally,
    so navigating away and clicking "Run" again orphaned the first lobby
    (students stuck on it, instructor can't find it). Reuses an existing
    `lobby`/`live` run for this assignment if one exists; self-heals by
    ending any *other* stale `lobby` rows for the same assignment, since an
    unstarted lobby has no participants-with-answers to lose."""
    existing = await db.scalar(
        select(GameRun)
        .where(GameRun.assignment_id == assignment.id, GameRun.status.in_(["lobby", "live"]))
        .order_by(GameRun.run_no.desc())
        .limit(1)
    )
    if existing is not None:
        await db.execute(
            update(GameRun)
            .where(GameRun.assignment_id == assignment.id, GameRun.status == "lobby", GameRun.id != existing.id)
            .values(status="ended", ended_at=datetime.now(timezone.utc))
        )
        await db.flush()
        return existing
    return await create_run(db, assignment=assignment, actor_id=actor_id)


async def join_run(db: AsyncSession, *, run: GameRun, user: User, avatar: str | None = None) -> GameParticipant:
    existing = await db.scalar(
        select(GameParticipant).where(GameParticipant.run_id == run.id, GameParticipant.user_id == user.id)
    )
    if existing is not None:
        return existing
    participant = GameParticipant(
        id=uuid.uuid4(), run_id=run.id, user_id=user.id,
        # Falls back to the account's own avatar so a student who set one
        # (or had one set for them) doesn't start every game faceless.
        nickname_snapshot=user.nickname or user.full_name, avatar=avatar or user.avatar,
    )
    db.add(participant)
    await db.flush()
    return participant


async def update_participant_profile(
    db: AsyncSession, *, participant: GameParticipant, nickname: str, avatar: str | None,
) -> GameParticipant:
    """Lobby-only per-game nickname/avatar override (D18) — a separate,
    uncapped mechanism from the profile-level nickname reroll (D2); callers
    enforce the lobby-only window (`run.status == "lobby"`), not this
    function, matching join_run's own "just write the row" scope."""
    participant.nickname_snapshot = nickname
    participant.avatar = avatar
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
        select(GameAnswer).where(
            GameAnswer.participant_id == participant.id,
            GameAnswer.question_id == question.id,
            # Only a *live* answer counts as already-answered. After a
            # restart the previous attempt's row is still there with
            # `reversed_at` set, and treating that as "already answered"
            # would leave every returning student unable to play.
            GameAnswer.reversed_at.is_(None),
        )
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
            idempotency_key=f"{run.id}:{run.restart_no}:{question.id}",
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


async def close_open_runs_for_session(db: AsyncSession, *, session_id: uuid.UUID) -> list[uuid.UUID]:
    """End any game still sitting in a lobby or mid-question when its session
    is marked done.

    An instructor who finishes a class rarely goes back to press End on a
    quiz they abandoned two activities ago, so those runs stayed `live`
    forever — showing up in students' joinable lists, and keeping a lobby
    alive for a class that has gone home. Completing the session is the
    unambiguous signal that none of them are still being played.

    Points are deliberately *not* reversed. Whatever students scored before
    the game was abandoned they genuinely earned; this only closes the door.

    Returns the ids of the runs that were closed, so the caller can tell the
    rooms still connected to them.
    """
    runs = (
        await db.execute(
            select(GameRun)
            .join(GameSessionAssignment, GameRun.assignment_id == GameSessionAssignment.id)
            .where(
                GameSessionAssignment.session_id == session_id,
                GameRun.status.in_(["lobby", "live"]),
            )
        )
    ).scalars().all()
    now = datetime.now(timezone.utc)
    for run in runs:
        run.status = "ended"
        run.current_question_position = None
        run.ended_at = now
    if runs:
        await db.flush()
    return [run.id for run in runs]


async def _reverse_answers(
    db: AsyncSession, *, run_id: uuid.UUID, restart_no: int, answers: list[GameAnswer],
) -> None:
    now = datetime.now(timezone.utc)
    for answer in answers:
        participant = await db.get(GameParticipant, answer.participant_id)
        await reverse_points(
            db, user_id=participant.user_id, source=GAME_POINTS_SOURCE, points=answer.points_awarded,
            idempotency_key=f"{run_id}:{restart_no}:{answer.question_id}:reversal",
            ref={"run_id": str(run_id), "question_id": str(answer.question_id) if answer.question_id else None},
        )
        answer.reversed_at = now
    await db.flush()


async def reverse_run_points(db: AsyncSession, *, run: GameRun) -> int:
    """D15/D17: closes out every not-yet-reversed answer in this run, for
    every participant, all-or-nothing (never split by which students are
    replaying) — new offsetting `point_events` rows for the ones that
    actually scored, the original award rows untouched. Returns the count
    of answers reversed.

    Zero-point (wrong/timed-out) answers are included too, not just
    positive-scoring ones: `submit_answer`'s idempotency check treats any
    row with `reversed_at IS NULL` as "already answered", so a wrong
    answer left unreversed would silently block that student from ever
    re-answering the question after a restart."""
    answers = (
        await db.execute(
            select(GameAnswer)
            .join(GameParticipant, GameAnswer.participant_id == GameParticipant.id)
            .where(
                GameParticipant.run_id == run.id,
                GameAnswer.reversed_at.is_(None),
            )
        )
    ).scalars().all()
    await _reverse_answers(db, run_id=run.id, restart_no=int(run.restart_no or 0), answers=answers)
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
    await _reverse_answers(db, run_id=run.id, restart_no=int(run.restart_no or 0), answers=answers)
    return len(answers)


async def restart_run(db: AsyncSession, *, run: GameRun, actor_id: uuid.UUID) -> GameRun:
    """The single Restart action (D15) — reverses every point this run has
    awarded so far and takes the **same run** back to its lobby.

    D15 originally made a restart a brand-new `GameRun`, which was wrong in
    practice: the join code changed, every student was ejected to the code
    screen, and what the instructor experienced as "run that again" became a
    room evacuation. A restart is a do-over of the same game with the same
    people, so it is the same row — same id, same code, same participants,
    `run_no` unchanged.

    The points reversal stays. Replaying a question a student already scored
    on and letting both totals stand would make the leaderboard a function of
    how many times the instructor pressed the button.

    Nothing is deleted. The previous attempt's answers keep their rows with
    `reversed_at` set — history of what was actually played survives, same
    posture as everywhere else in this codebase — and `restart_no` advances
    so the replay's ledger keys don't collide with the reversed ones.
    """
    await reverse_run_points(db, run=run)
    run.restart_no = int(run.restart_no or 0) + 1
    run.status = "lobby"
    run.current_question_position = None
    run.started_at = None
    run.ended_at = None
    await db.flush()
    return run


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


async def participant_score(db: AsyncSession, *, participant_id: uuid.UUID) -> int:
    total = await db.scalar(
        select(func.coalesce(func.sum(GameAnswer.points_awarded), 0)).where(
            GameAnswer.participant_id == participant_id, GameAnswer.reversed_at.is_(None),
        )
    )
    return int(total or 0)


async def participant_streak(db: AsyncSession, *, participant_id: uuid.UUID) -> int:
    """Consecutive correct answers ending at the most recently answered
    question, in question order (not submission order) — 8-8's streak
    counter."""
    rows = (
        await db.execute(
            select(GameAnswer.is_correct)
            .join(GameSessionQuestion, GameAnswer.question_id == GameSessionQuestion.id)
            .where(
                GameAnswer.participant_id == participant_id,
                GameAnswer.reversed_at.is_(None),
            )
            .order_by(GameSessionQuestion.position.desc())
        )
    ).scalars().all()
    streak = 0
    for is_correct in rows:
        if not is_correct:
            break
        streak += 1
    return streak


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

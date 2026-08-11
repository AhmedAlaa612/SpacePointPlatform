"""Live games — instructor live-play routes (Live Games Phase 2C, 8-7):
`/games/live/*`, gated by `require_session_delivery` (instructor +
facilitator + operations; admin passes automatically) — running a game
is a delivery action, the same population that marks attendance and
manages session materials, not the narrower authoring-only
`require_lms_content` the template/assignment routers use.

Every mutating endpoint here does two things: change the database, then
broadcast over the run's Redis channel (`services/games/realtime.py`) so
every connected WS client — instructor and every student, 8-5 — updates
without polling. **Broadcasts are always the redacted/public shape**
(`schemas/games_live.py::PublicQuestionOut`, no `is_correct`; a
blackout-aware leaderboard) — the run channel is shared by students, so
nothing sent there can carry the answer key or (during the blackout
round, D10) anyone else's score. Anything richer (the answer key, the
full leaderboard, a real-name reveal) is a separate staff-gated HTTP GET,
never broadcast.

Two close-in-meaning actions on purpose: `/reveal` closes the answering
window and shows results for the *current* question without moving
position; `/next` is the separate action that actually advances (or
ends the run past the last question). This matches the console's own
two states (Frame 02a live, 02b between-questions) — `/reveal` is what
transitions 2a → 2b, `/next` is what transitions 2b → the next 2a (or
the end).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_session_delivery
from app.db.session import get_db
from app.models.games.run import GameParticipant, GameRun
from app.models.games.session_assignment import GameSessionAssignment, GameSessionQuestion
from app.models.user import User
from app.schemas.games_live import (
    GameRunOut,
    LeaderboardEntryOut,
    LiveQuestionOptionOut,
    LiveQuestionOut,
    PublicQuestionOptionOut,
    PublicQuestionOut,
    QuestionResultOut,
    RevealNameOut,
    RosterEntryOut,
)
import redis.asyncio as redis

from app.services.games.points import max_points_for
from app.services.games.realtime import get_realtime_redis_dep, safe_publish_to_run
from app.services.games.runs import (
    advance_run,
    count_questions,
    create_run,
    end_run,
    get_current_question,
    is_blackout_active,
    question_results,
    restart_run,
    run_leaderboard,
    run_roster,
    start_run,
)

router = APIRouter(prefix="/games/live", tags=["games-live"], dependencies=[Depends(require_session_delivery)])


async def _run_or_404(db: AsyncSession, run_id: uuid.UUID) -> GameRun:
    run = await db.get(GameRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


def _public_question(question: GameSessionQuestion, assignment: GameSessionAssignment) -> PublicQuestionOut:
    return PublicQuestionOut(
        id=question.id, position=question.position, prompt=question.prompt,
        options=[PublicQuestionOptionOut(text=o["text"]) for o in question.options],
        time_limit_seconds=question.time_limit_seconds or assignment.time_limit_seconds,
        max_points=max_points_for(question.points_mode),
    )


def _live_question(question: GameSessionQuestion, assignment: GameSessionAssignment) -> LiveQuestionOut:
    return LiveQuestionOut(
        id=question.id, position=question.position, prompt=question.prompt,
        options=[LiveQuestionOptionOut(text=o["text"], is_correct=o["is_correct"]) for o in question.options],
        time_limit_seconds=question.time_limit_seconds or assignment.time_limit_seconds,
        max_points=max_points_for(question.points_mode),
    )


async def _run_out(db: AsyncSession, run: GameRun) -> GameRunOut:
    total = await count_questions(db, run.assignment_id)
    assignment = await db.get(GameSessionAssignment, run.assignment_id)
    return GameRunOut(
        id=run.id, assignment_id=run.assignment_id, run_no=run.run_no, status=run.status,
        current_question_position=run.current_question_position, total_questions=total,
        blackout_active=is_blackout_active(
            current_question_position=run.current_question_position, total_questions=total,
            blackout_count=assignment.blackout_count,
        ),
        started_at=run.started_at, ended_at=run.ended_at,
    )


# ── lifecycle ────────────────────────────────────────────────────────────

@router.post("/assignments/{assignment_id}/runs", response_model=GameRunOut, status_code=status.HTTP_201_CREATED)
async def open_run(assignment_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(require_session_delivery)):
    assignment = await db.get(GameSessionAssignment, assignment_id)
    if assignment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    run = await create_run(db, assignment=assignment, actor_id=current.id)
    await db.commit()
    return await _run_out(db, run)


@router.get("/runs/{run_id}", response_model=GameRunOut)
async def get_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    run = await _run_or_404(db, run_id)
    return await _run_out(db, run)


@router.get("/runs/{run_id}/question", response_model=LiveQuestionOut)
async def get_current_question_full(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    run = await _run_or_404(db, run_id)
    question = await get_current_question(db, run)
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No question is live")
    assignment = await db.get(GameSessionAssignment, run.assignment_id)
    return _live_question(question, assignment)


@router.post("/runs/{run_id}/start", response_model=GameRunOut)
async def start(run_id: uuid.UUID, db: AsyncSession = Depends(get_db), rt: redis.Redis | None = Depends(get_realtime_redis_dep)):
    run = await _run_or_404(db, run_id)
    await start_run(db, run=run)
    await db.commit()
    question = await get_current_question(db, run)
    assignment = await db.get(GameSessionAssignment, run.assignment_id)
    await safe_publish_to_run(rt, str(run_id), "question_started", _public_question(question, assignment).model_dump(mode="json"))
    return await _run_out(db, run)


@router.post("/runs/{run_id}/reveal", response_model=list[QuestionResultOut])
async def reveal(run_id: uuid.UUID, db: AsyncSession = Depends(get_db), rt: redis.Redis | None = Depends(get_realtime_redis_dep)):
    """Closes the answering window for the current question without
    advancing position — broadcasts the leaderboard (redacted during
    blackout, D10) so every connected client moves to the between-
    questions view. Returns the full per-option results for the
    instructor's own screen."""
    run = await _run_or_404(db, run_id)
    question = await get_current_question(db, run)
    if question is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No question is live")
    assignment = await db.get(GameSessionAssignment, run.assignment_id)
    total = await count_questions(db, run.assignment_id)
    blackout = is_blackout_active(
        current_question_position=run.current_question_position, total_questions=total,
        blackout_count=assignment.blackout_count,
    )
    if blackout:
        await safe_publish_to_run(rt, str(run_id), "leaderboard_update", {"blackout": True})
    else:
        board = await run_leaderboard(db, run_id)
        await safe_publish_to_run(rt, str(run_id), "leaderboard_update", {"blackout": False, "leaderboard": [
            {"participant_id": str(r["participant_id"]), "nickname": r["nickname"], "avatar": r["avatar"], "score": r["score"]}
            for r in board
        ]})
    return await question_results(db, run=run, question=question)


@router.post("/runs/{run_id}/next", response_model=GameRunOut)
async def next_question(run_id: uuid.UUID, db: AsyncSession = Depends(get_db), rt: redis.Redis | None = Depends(get_realtime_redis_dep)):
    run = await _run_or_404(db, run_id)
    await advance_run(db, run=run)
    await db.commit()
    if run.status == "ended":
        await safe_publish_to_run(rt, str(run_id), "game_ended", {})
    else:
        question = await get_current_question(db, run)
        assignment = await db.get(GameSessionAssignment, run.assignment_id)
        await safe_publish_to_run(rt, str(run_id), "question_started", _public_question(question, assignment).model_dump(mode="json"))
    return await _run_out(db, run)


@router.post("/runs/{run_id}/restart", response_model=GameRunOut)
async def restart(
    run_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(require_session_delivery),
    rt: redis.Redis | None = Depends(get_realtime_redis_dep),
):
    run = await _run_or_404(db, run_id)
    new_run = await restart_run(db, run=run, actor_id=current.id)
    await db.commit()
    await safe_publish_to_run(rt, str(run_id), "game_restarted", {"new_run_id": str(new_run.id)})
    return await _run_out(db, new_run)


@router.post("/runs/{run_id}/end", response_model=GameRunOut)
async def end(run_id: uuid.UUID, db: AsyncSession = Depends(get_db), rt: redis.Redis | None = Depends(get_realtime_redis_dep)):
    run = await _run_or_404(db, run_id)
    await end_run(db, run=run)
    await db.commit()
    await safe_publish_to_run(rt, str(run_id), "game_ended", {})
    return await _run_out(db, run)


# ── staff-only reads (never broadcast) ──────────────────────────────────

@router.get("/runs/{run_id}/roster", response_model=list[RosterEntryOut])
async def roster(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    run = await _run_or_404(db, run_id)
    return await run_roster(db, run=run)


@router.get("/runs/{run_id}/leaderboard", response_model=list[LeaderboardEntryOut])
async def leaderboard(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Instructor's own view — full leaderboard regardless of blackout
    (D10: staff always sees everything); students never call this."""
    await _run_or_404(db, run_id)
    return await run_leaderboard(db, run_id)


@router.get("/runs/{run_id}/participants/{participant_id}/reveal", response_model=RevealNameOut)
async def reveal_name(run_id: uuid.UUID, participant_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """D9's per-row staff popover — the real-name mapping, never sent to
    students, never broadcast."""
    participant = await db.get(GameParticipant, participant_id)
    if participant is None or participant.run_id != run_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Participant not found")
    user = await db.get(User, participant.user_id)
    return RevealNameOut(participant_id=participant.id, real_name=user.full_name if user else "(unknown)")

"""Live games — student play routes (Live Games Phase 2C, 8-8):
`/games/play/*`. Any authenticated active user may join a run they can
see (no dedicated role gate — mirrors how quizzes/missions are reachable
by anyone signed in, not just accounts tagged "student"); nickname/avatar
just falls back to the account's real name for a non-student the same
way the platform leaderboard already does (`services/lms/leaderboard.py
::_display_name`).

Every response here is the redacted/public shape — no `is_correct` on a
question, no other participant's real name, and the leaderboard is
blackout-aware (D10: a student sees only their own score, never anyone
else's rank, during the last N questions — the instructor's own
always-full view lives on the staff-gated `/games/live/*` router).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.games.game import Game
from app.models.games.run import GameParticipant, GameRun
from app.models.games.session_assignment import GameSessionAssignment
from app.models.sessions.registration import Registration
from app.models.sessions.session import Session
from app.models.user import User
from app.schemas.games_live import GameRunOut, PublicQuestionOptionOut, PublicQuestionOut, RosterEntryOut
from app.schemas.games_play import (
    AnswerAckOut,
    JoinableRunOut,
    JoinRunIn,
    MyScoreOut,
    ParticipantOut,
    StudentLeaderboardEntryOut,
    SubmitAnswerIn,
    UpdateParticipantProfileIn,
)
from app.services.games.points import max_points_for
from app.services.games.realtime import get_realtime_redis_dep, publish_to_participant, safe_publish_to_run
from app.services.games.runs import (
    count_questions,
    get_current_question,
    is_blackout_active,
    join_run,
    participant_score,
    participant_streak,
    run_leaderboard,
    run_roster,
    submit_answer,
    update_participant_profile,
)
from app.services.sessions.registration import ACTIVE_REGISTRATION_STATUSES

router = APIRouter(prefix="/games/play", tags=["games-play"])


async def _run_or_404(db: AsyncSession, run_id: uuid.UUID) -> GameRun:
    run = await db.get(GameRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Game not found")
    return run


async def _my_participant(db: AsyncSession, run_id: uuid.UUID, user_id: uuid.UUID) -> GameParticipant:
    participant = await db.scalar(
        select(GameParticipant).where(GameParticipant.run_id == run_id, GameParticipant.user_id == user_id)
    )
    if participant is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Join this game before playing it")
    return participant


@router.get("/joinable", response_model=list[JoinableRunOut])
async def joinable_runs(db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user)):
    if current.contact_id is None:
        return []
    rows = (
        await db.execute(
            select(GameRun, Game.title, Session.title, Session.meeting_date)
            .join(GameSessionAssignment, GameRun.assignment_id == GameSessionAssignment.id)
            .join(Game, GameSessionAssignment.game_id == Game.id)
            .join(Session, GameSessionAssignment.session_id == Session.id)
            .join(Registration, Registration.cohort_id == Session.cohort_id)
            .where(
                Registration.contact_id == current.contact_id,
                Registration.status.in_(ACTIVE_REGISTRATION_STATUSES),
                GameRun.status.in_(["lobby", "live"]),
            )
            .order_by(GameRun.created_at.desc())
        )
    ).all()
    # Defense-in-depth against stale duplicate lobby rows an assignment may
    # already have from before get_or_create_open_run existed — rows are
    # already ordered newest-first, so keeping the first occurrence per
    # assignment_id keeps the most recent run and drops any orphaned ones.
    seen_assignments: set[uuid.UUID] = set()
    out = []
    for run, game_title, session_title, meeting_date in rows:
        if run.assignment_id in seen_assignments:
            continue
        seen_assignments.add(run.assignment_id)
        out.append(JoinableRunOut(
            run_id=run.id, assignment_id=run.assignment_id, game_title=game_title, status=run.status,
            session_title=session_title, session_date=meeting_date.isoformat(),
        ))
    return out


@router.post("/runs/{run_id}/join", response_model=ParticipantOut, status_code=status.HTTP_201_CREATED)
async def join(
    run_id: uuid.UUID, body: JoinRunIn, db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user), rt=Depends(get_realtime_redis_dep),
):
    run = await _run_or_404(db, run_id)
    if run.status == "ended":
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This game has ended")
    participant = await join_run(db, run=run, user=current, avatar=body.avatar)
    await db.commit()
    await safe_publish_to_run(rt, str(run_id), "participant_joined", {
        "participant_id": str(participant.id), "nickname": participant.nickname_snapshot,
        "avatar": participant.avatar, "joined_at": participant.joined_at.isoformat() if participant.joined_at else None,
    })
    return ParticipantOut(
        id=participant.id, run_id=participant.run_id, nickname=participant.nickname_snapshot,
        avatar=participant.avatar, joined_at=participant.joined_at,
    )


@router.patch("/runs/{run_id}/me", response_model=ParticipantOut)
async def update_my_profile(
    run_id: uuid.UUID, body: UpdateParticipantProfileIn, db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user), rt=Depends(get_realtime_redis_dep),
):
    """Lobby-only per-game nickname/avatar override (D18) — locked once the
    run leaves 'lobby' so identity never shifts mid-leaderboard."""
    run = await _run_or_404(db, run_id)
    if run.status != "lobby":
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Can't change your profile once the game has started")
    participant = await _my_participant(db, run_id, current.id)
    participant = await update_participant_profile(db, participant=participant, nickname=body.nickname, avatar=body.avatar)
    await db.commit()
    await safe_publish_to_run(rt, str(run_id), "participant_updated", {
        "participant_id": str(participant.id), "nickname": participant.nickname_snapshot, "avatar": participant.avatar,
    })
    return ParticipantOut(
        id=participant.id, run_id=participant.run_id, nickname=participant.nickname_snapshot,
        avatar=participant.avatar, joined_at=participant.joined_at,
    )


@router.get("/runs/{run_id}/roster", response_model=list[RosterEntryOut])
async def student_roster(run_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user)):
    """Same redacted shape the staff console uses — nickname/avatar only,
    never a real name. Powers the student's own lobby "who's here" view."""
    run = await _run_or_404(db, run_id)
    await _my_participant(db, run_id, current.id)
    roster = await run_roster(db, run=run)
    return [RosterEntryOut(**r) for r in roster]


@router.get("/runs/{run_id}", response_model=GameRunOut)
async def run_status(run_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_active_user)):
    """No join required — the lobby screen needs this before the student
    has clicked "join"."""
    run = await _run_or_404(db, run_id)
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


@router.get("/runs/{run_id}/question", response_model=PublicQuestionOut)
async def current_question(run_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user)):
    run = await _run_or_404(db, run_id)
    await _my_participant(db, run_id, current.id)
    question = await get_current_question(db, run)
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No question is live")
    assignment = await db.get(GameSessionAssignment, run.assignment_id)
    return PublicQuestionOut(
        id=question.id, position=question.position, prompt=question.prompt,
        options=[PublicQuestionOptionOut(text=o["text"]) for o in question.options],
        time_limit_seconds=question.time_limit_seconds or assignment.time_limit_seconds,
        max_points=max_points_for(question.points_mode),
    )


@router.post("/runs/{run_id}/answer", response_model=AnswerAckOut)
async def answer(
    run_id: uuid.UUID, body: SubmitAnswerIn, db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user), rt=Depends(get_realtime_redis_dep),
):
    run = await _run_or_404(db, run_id)
    participant = await _my_participant(db, run_id, current.id)
    question = await get_current_question(db, run)
    if question is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No question is live")
    assignment = await db.get(GameSessionAssignment, run.assignment_id)

    result = await submit_answer(
        db, run=run, participant=participant, question=question,
        selected_option_index=body.selected_option_index, elapsed_seconds=body.elapsed_seconds,
    )
    streak = await participant_streak(db, participant_id=participant.id)
    await db.commit()

    max_points = max_points_for(question.points_mode)
    base_points = round(max_points * assignment.floor_pct / 100) if result.is_correct else 0
    speed_bonus = max(0, result.points_awarded - base_points)
    ack = AnswerAckOut(
        is_correct=result.is_correct, points_awarded=result.points_awarded,
        base_points=base_points, speed_bonus=speed_bonus, streak=streak,
    )
    if rt is not None:
        try:
            await publish_to_participant(rt, str(run_id), str(current.id), "answer_ack", ack.model_dump(mode="json"))
        except Exception:
            pass  # HTTP response already carries the same data — a dropped broadcast isn't fatal here
    # Shared-channel broadcast, deliberately NOT the private answer_ack above
    # — this only says "someone answered," never who or whether they were
    # right, so it's safe on the run channel every student shares. Ticks the
    # instructor's live answered-count without waiting on the 3s poll.
    await safe_publish_to_run(rt, str(run_id), "participant_answered", {"participant_id": str(participant.id)})
    return ack


@router.get("/runs/{run_id}/my-score", response_model=MyScoreOut)
async def my_score(run_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user)):
    participant = await _my_participant(db, run_id, current.id)
    score = await participant_score(db, participant_id=participant.id)
    streak = await participant_streak(db, participant_id=participant.id)
    return MyScoreOut(score=score, streak=streak)


@router.get("/runs/{run_id}/leaderboard", response_model=list[StudentLeaderboardEntryOut])
async def student_leaderboard(run_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user)):
    """Blackout-aware (D10): once the run is in its last blackout_count
    questions, a student sees only their own row, not the board."""
    run = await _run_or_404(db, run_id)
    participant = await _my_participant(db, run_id, current.id)
    assignment = await db.get(GameSessionAssignment, run.assignment_id)
    total = await count_questions(db, run.assignment_id)
    blackout = is_blackout_active(
        current_question_position=run.current_question_position, total_questions=total,
        blackout_count=assignment.blackout_count,
    )
    if blackout:
        score = await participant_score(db, participant_id=participant.id)
        return [StudentLeaderboardEntryOut(
            participant_id=participant.id, nickname=participant.nickname_snapshot,
            avatar=participant.avatar, score=score, is_me=True,
        )]
    board = await run_leaderboard(db, run_id)
    return [
        StudentLeaderboardEntryOut(
            participant_id=r["participant_id"], nickname=r["nickname"], avatar=r["avatar"],
            score=r["score"], is_me=(r["participant_id"] == participant.id),
        )
        for r in board
    ]

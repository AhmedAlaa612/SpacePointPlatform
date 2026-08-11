"""Live Games Phase 2C, 8-6 — run/participant/answer schema + scoring
(D8, D14). Redis-free, no HTTP surface yet (8-7/8-8 build the routers
that call these functions).
"""

import uuid

import pytest
from sqlalchemy import select

from app.models.games.game import Game, GameQuestion
from app.models.games.session_assignment import GameSessionAssignment, GameSessionQuestion
from app.models.lms.points import PointEvent
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.session import Session
from app.models.user import User
from app.services.games.runs import (
    advance_run, create_run, get_current_question, join_run, run_leaderboard, start_run, submit_answer,
)
from app.services.games.scoring import score_answer
from app.services.lms.leaderboard import leaderboard as platform_leaderboard


async def _user(db, *, nickname="NebulaFalcon482") -> User:
    user = User(
        id=uuid.uuid4(), full_name="Run Test User", email=f"run-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["student"], status="active", nickname=nickname,
    )
    db.add(user)
    await db.flush()
    return user


async def _assignment_with_questions(db, *, floor_pct=25, time_limit=20, count=2) -> GameSessionAssignment:
    ops = User(
        id=uuid.uuid4(), full_name="Ops", email=f"ops-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["operations"], status="active",
    )
    db.add(ops)
    await db.flush()
    game = Game(id=uuid.uuid4(), title="Transfer Orbits", created_by=ops.id)
    db.add(game)
    await db.flush()
    program = Program(id=uuid.uuid4(), code=f"P-{uuid.uuid4().hex[:8]}", name="P", program_type="workshop", pricing_model="free", active=True)
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="C", status="running")
    db.add(cohort)
    await db.flush()
    from datetime import date
    session = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date.today())
    db.add(session)
    await db.flush()

    assignment = GameSessionAssignment(
        id=uuid.uuid4(), session_id=session.id, game_id=game.id,
        time_limit_seconds=time_limit, floor_pct=floor_pct, blackout_count=3, assigned_by=ops.id,
    )
    db.add(assignment)
    await db.flush()
    for i in range(1, count + 1):
        db.add(GameSessionQuestion(
            id=uuid.uuid4(), assignment_id=assignment.id, position=i, prompt=f"Q{i}",
            points_mode="double" if i == 1 else "normal",
            options=[{"text": "A", "is_correct": True}, {"text": "B", "is_correct": False}],
        ))
    await db.flush()
    return assignment


def test_score_answer_correct_matches_the_floored_linear_decay_formula():
    # max=100, floor=25% -> floor_pts=25; instant answer -> full 100
    assert score_answer(is_correct=True, max_points=100, floor_pct=25, elapsed_seconds=0, time_limit_seconds=20) == 100
    # at the buzzer -> exactly the floor, never zero
    assert score_answer(is_correct=True, max_points=100, floor_pct=25, elapsed_seconds=20, time_limit_seconds=20) == 25
    # halfway -> halfway between floor and max: 25 + 75*0.5 = 62.5 -> rounds to 62 (banker's rounding) or 63
    half = score_answer(is_correct=True, max_points=100, floor_pct=25, elapsed_seconds=10, time_limit_seconds=20)
    assert half in (62, 63)
    # double points scales the same way
    assert score_answer(is_correct=True, max_points=200, floor_pct=25, elapsed_seconds=0, time_limit_seconds=20) == 200
    assert score_answer(is_correct=True, max_points=200, floor_pct=25, elapsed_seconds=20, time_limit_seconds=20) == 50


def test_score_answer_wrong_or_missing_is_always_zero():
    assert score_answer(is_correct=False, max_points=200, floor_pct=25, elapsed_seconds=0, time_limit_seconds=20) == 0
    assert score_answer(is_correct=False, max_points=100, floor_pct=25, elapsed_seconds=20, time_limit_seconds=20) == 0


def test_score_answer_clamps_elapsed_past_the_time_limit_to_the_floor():
    assert score_answer(is_correct=True, max_points=100, floor_pct=25, elapsed_seconds=999, time_limit_seconds=20) == 25


@pytest.mark.asyncio
async def test_a_correct_answer_awards_exactly_one_point_events_row(db):
    assignment = await _assignment_with_questions(db, count=1)
    student = await _user(db)
    await db.flush()

    run = await create_run(db, assignment=assignment, actor_id=student.id)
    participant = await join_run(db, run=run, user=student)
    await start_run(db, run=run)

    question = await get_current_question(db, run)
    assert question is not None and question.points_mode == "double"

    answer = await submit_answer(db, run=run, participant=participant, question=question, selected_option_index=0, elapsed_seconds=0)
    assert answer.is_correct is True
    assert answer.points_awarded == 200  # double, instant answer

    events = (await db.execute(select(PointEvent).where(PointEvent.user_id == student.id))).scalars().all()
    assert len(events) == 1
    assert events[0].source == "game"
    assert events[0].points == 200


@pytest.mark.asyncio
async def test_a_wrong_answer_scores_zero_and_awards_no_points(db):
    assignment = await _assignment_with_questions(db, count=1)
    student = await _user(db)
    await db.flush()

    run = await create_run(db, assignment=assignment, actor_id=student.id)
    participant = await join_run(db, run=run, user=student)
    await start_run(db, run=run)
    question = await get_current_question(db, run)

    answer = await submit_answer(db, run=run, participant=participant, question=question, selected_option_index=1, elapsed_seconds=3)
    assert answer.is_correct is False
    assert answer.points_awarded == 0

    events = (await db.execute(select(PointEvent).where(PointEvent.user_id == student.id))).scalars().all()
    assert events == []


@pytest.mark.asyncio
async def test_answering_the_same_question_twice_is_idempotent(db):
    assignment = await _assignment_with_questions(db, count=1)
    student = await _user(db)
    await db.flush()

    run = await create_run(db, assignment=assignment, actor_id=student.id)
    participant = await join_run(db, run=run, user=student)
    await start_run(db, run=run)
    question = await get_current_question(db, run)

    first = await submit_answer(db, run=run, participant=participant, question=question, selected_option_index=0, elapsed_seconds=0)
    second = await submit_answer(db, run=run, participant=participant, question=question, selected_option_index=1, elapsed_seconds=5)
    assert first.id == second.id  # second call is a no-op, returns the original

    events = (await db.execute(select(PointEvent).where(PointEvent.user_id == student.id))).scalars().all()
    assert len(events) == 1


@pytest.mark.asyncio
async def test_restarting_lets_the_same_question_earn_points_again_in_the_new_run(db):
    """D15's whole point: a restart is a fresh run, so the same question,
    answered again under the new run_id, must be able to earn points again
    — the idempotency key is scoped by run, not just by question."""
    assignment = await _assignment_with_questions(db, count=1)
    student = await _user(db)
    await db.flush()

    run1 = await create_run(db, assignment=assignment, actor_id=student.id)
    p1 = await join_run(db, run=run1, user=student)
    await start_run(db, run=run1)
    q1 = await get_current_question(db, run1)
    await submit_answer(db, run=run1, participant=p1, question=q1, selected_option_index=0, elapsed_seconds=0)

    run2 = await create_run(db, assignment=assignment, actor_id=student.id)
    assert run2.run_no == run1.run_no + 1
    p2 = await join_run(db, run=run2, user=student)
    await start_run(db, run=run2)
    q2 = await get_current_question(db, run2)
    assert q2.id == q1.id  # same underlying question row
    answer2 = await submit_answer(db, run=run2, participant=p2, question=q2, selected_option_index=0, elapsed_seconds=0)
    assert answer2.points_awarded == 200

    events = (await db.execute(select(PointEvent).where(PointEvent.user_id == student.id))).scalars().all()
    assert len(events) == 2  # one per run, not silently deduped across runs


@pytest.mark.asyncio
async def test_advance_run_moves_through_questions_then_ends(db):
    assignment = await _assignment_with_questions(db, count=2)
    student = await _user(db)
    await db.flush()
    run = await create_run(db, assignment=assignment, actor_id=student.id)
    await start_run(db, run=run)
    assert run.current_question_position == 1

    await advance_run(db, run=run)
    assert run.status == "live"
    assert run.current_question_position == 2

    await advance_run(db, run=run)
    assert run.status == "ended"
    assert run.current_question_position is None
    assert run.ended_at is not None


@pytest.mark.asyncio
async def test_run_leaderboard_shows_nickname_and_avatar_never_real_name(db):
    assignment = await _assignment_with_questions(db, count=1)
    alice = await _user(db, nickname="NebulaFalcon482")
    bob = await _user(db, nickname="CometOtter113")
    await db.flush()

    run = await create_run(db, assignment=assignment, actor_id=alice.id)
    pa = await join_run(db, run=run, user=alice, avatar="fox")
    pb = await join_run(db, run=run, user=bob)
    await start_run(db, run=run)
    question = await get_current_question(db, run)

    await submit_answer(db, run=run, participant=pa, question=question, selected_option_index=0, elapsed_seconds=0)
    await submit_answer(db, run=run, participant=pb, question=question, selected_option_index=1, elapsed_seconds=0)

    board = await run_leaderboard(db, run.id)
    assert len(board) == 2
    assert board[0]["nickname"] == "NebulaFalcon482"
    assert board[0]["avatar"] == "fox"
    assert board[0]["score"] == 200
    assert board[1]["nickname"] == "CometOtter113"
    assert board[1]["score"] == 0
    assert all("full_name" not in row and "email" not in row for row in board)


@pytest.mark.asyncio
async def test_late_join_has_no_retroactive_catchup(db):
    assignment = await _assignment_with_questions(db, count=2)
    early = await _user(db, nickname="EarlyBird1")
    late = await _user(db, nickname="LateOwl2")
    await db.flush()

    run = await create_run(db, assignment=assignment, actor_id=early.id)
    p_early = await join_run(db, run=run, user=early)
    await start_run(db, run=run)
    q1 = await get_current_question(db, run)
    await submit_answer(db, run=run, participant=p_early, question=q1, selected_option_index=0, elapsed_seconds=0)

    await advance_run(db, run=run)  # question 2 now live
    p_late = await join_run(db, run=run, user=late)  # joins after Q1 already passed
    q2 = await get_current_question(db, run)
    await submit_answer(db, run=run, participant=p_late, question=q2, selected_option_index=0, elapsed_seconds=0)

    board = {row["nickname"]: row["score"] for row in await run_leaderboard(db, run.id)}
    assert board["EarlyBird1"] == 200  # Q1 (double)
    assert board["LateOwl2"] == 100    # only Q2 (normal), no points for the missed Q1


@pytest.mark.asyncio
async def test_game_points_flow_into_the_platform_leaderboard_with_no_extra_plumbing(db):
    """D14: a completed game's score feeds the platform's persistent points
    ledger. Proves the whole path, not just that a PointEvent row exists —
    services/lms/leaderboard.py sums point_events with no games-specific
    join, so this should Just Work the moment award_points(source="game")
    is called."""
    assignment = await _assignment_with_questions(db, count=1)
    student = await _user(db, nickname="LedgerCheck99")
    await db.flush()

    run = await create_run(db, assignment=assignment, actor_id=student.id)
    participant = await join_run(db, run=run, user=student)
    await start_run(db, run=run)
    question = await get_current_question(db, run)
    await submit_answer(db, run=run, participant=participant, question=question, selected_option_index=0, elapsed_seconds=0)

    board = await platform_leaderboard(db)
    entry = next(row for row in board if row["user_id"] == student.id)
    assert entry["display_name"] == "LedgerCheck99"
    assert entry["points"] == 200

"""Live games — per-session assignment routes (Live Games Phase 2C, 8-4) —
`/games/sessions/*`. Two populations on purpose, not one router-wide
gate: attaching or removing a game from a session (`create_assignment`,
`delete_assignment`) is a planning action, kept `require_lms_content`
(operations + facilitator — same as `/games/admin/*`'s template
authoring, D4). Everything else here — reading the assignment, editing
its config/note, and the question CRUD on its snapshot — is
`require_session_delivery` (instructor + facilitator + operations), the
router's default: the operator was explicit that an instructor "can
change some configs if he wants" once a game is assigned (D11), and
later that "an instructor can edit the questions in their session
assigned game and add questions to it, even mid game" (D13's own
grilling round). Admin passes every gate automatically either way.

Question CRUD on an assignment's snapshot mirrors `routers/games/admin.py`'s
question section almost exactly — same shape, scoped by `assignment_id`
instead of `game_id`, and reusing the same request/response schemas since
the field shapes are identical.

D13's mid-game rule (8-7): once a run is `live`, editing a question's
content or reordering the set is blocked (409) — `GameRun
.current_question_position` addresses questions by position, so a
reorder mid-game would silently point it at a different question.
**Add and delete stay allowed live**, matching D13 exactly. Deleting an
already-answered question while a run is live reverses that question's
points first (D16) — `services/games/runs.py::reverse_question_points`
— before the row (and, via `ON DELETE SET NULL`, its answers'
`question_id`) actually goes away.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_lms_content, require_session_delivery
from app.db.session import get_db
from app.models.games.game import Game, GameQuestion
from app.models.games.run import GameRun
from app.models.games.session_assignment import GameSessionAssignment, GameSessionQuestion
from app.models.sessions.session import Session
from app.models.user import User
from app.schemas.games_admin import (
    GameQuestionIn,
    GameQuestionOut,
    GameQuestionReorderIn,
    GameQuestionUpdate,
    GameSessionAssignmentCreate,
    GameSessionAssignmentDetailOut,
    GameSessionAssignmentOut,
    GameSessionAssignmentUpdate,
)
from app.services.games.points import max_points_for
from app.services.games.runs import reverse_question_points

router = APIRouter(prefix="/games/sessions", tags=["games-sessions"], dependencies=[Depends(require_session_delivery)])


async def _live_run(db: AsyncSession, assignment_id: uuid.UUID) -> GameRun | None:
    return await db.scalar(select(GameRun).where(GameRun.assignment_id == assignment_id, GameRun.status == "live"))


def _question_out(q: GameSessionQuestion) -> GameQuestionOut:
    return GameQuestionOut(
        id=q.id, position=q.position, prompt=q.prompt, options=q.options,
        time_limit_seconds=q.time_limit_seconds, points_mode=q.points_mode,
        max_points=max_points_for(q.points_mode),
    )


async def _assignment_or_404(db: AsyncSession, assignment_id: uuid.UUID) -> GameSessionAssignment:
    assignment = await db.get(GameSessionAssignment, assignment_id)
    if assignment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Game assignment not found")
    return assignment


async def _assignment_out(db: AsyncSession, assignment: GameSessionAssignment) -> GameSessionAssignmentOut:
    count = await db.scalar(
        select(func.count()).select_from(GameSessionQuestion).where(GameSessionQuestion.assignment_id == assignment.id)
    )
    game = await db.get(Game, assignment.game_id)
    return GameSessionAssignmentOut(
        id=assignment.id, session_id=assignment.session_id, game_id=assignment.game_id,
        game_title=game.title if game else "(deleted game)",
        instructor_note=assignment.instructor_note, time_limit_seconds=assignment.time_limit_seconds,
        floor_pct=assignment.floor_pct, blackout_count=assignment.blackout_count,
        assigned_by=assignment.assigned_by, created_at=assignment.created_at, question_count=count or 0,
    )


# ── assignments ──────────────────────────────────────────────────────────

@router.get("/{session_id}/assignments", response_model=list[GameSessionAssignmentOut])
async def list_assignments(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(GameSessionAssignment)
        .where(GameSessionAssignment.session_id == session_id)
        .order_by(GameSessionAssignment.created_at)
    )).scalars().all()
    return [await _assignment_out(db, a) for a in rows]


@router.post("/{session_id}/assignments", response_model=GameSessionAssignmentDetailOut, status_code=status.HTTP_201_CREATED)
async def create_assignment(
    session_id: uuid.UUID, body: GameSessionAssignmentCreate,
    db: AsyncSession = Depends(get_db), current: User = Depends(require_lms_content),
):
    session = await db.get(Session, session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    game = await db.get(Game, body.game_id)
    if game is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Game not found")

    assignment = GameSessionAssignment(
        id=uuid.uuid4(), session_id=session_id, game_id=game.id, instructor_note=body.instructor_note,
        time_limit_seconds=game.default_time_limit_seconds, floor_pct=game.default_floor_pct,
        blackout_count=game.default_blackout_count, assigned_by=current.id,
    )
    db.add(assignment)
    await db.flush()

    template_questions = (await db.execute(
        select(GameQuestion).where(GameQuestion.game_id == game.id).order_by(GameQuestion.position)
    )).scalars().all()
    for q in template_questions:
        db.add(GameSessionQuestion(
            id=uuid.uuid4(), assignment_id=assignment.id, position=q.position, prompt=q.prompt,
            options=q.options, time_limit_seconds=q.time_limit_seconds, points_mode=q.points_mode,
        ))

    await db.commit()
    await db.refresh(assignment)
    out = await _assignment_out(db, assignment)
    questions = (await db.execute(
        select(GameSessionQuestion).where(GameSessionQuestion.assignment_id == assignment.id).order_by(GameSessionQuestion.position)
    )).scalars().all()
    return GameSessionAssignmentDetailOut(**out.model_dump(), questions=[_question_out(q) for q in questions])


@router.get("/assignments/{assignment_id}", response_model=GameSessionAssignmentDetailOut)
async def get_assignment(assignment_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    assignment = await _assignment_or_404(db, assignment_id)
    questions = (await db.execute(
        select(GameSessionQuestion).where(GameSessionQuestion.assignment_id == assignment_id).order_by(GameSessionQuestion.position)
    )).scalars().all()
    out = await _assignment_out(db, assignment)
    return GameSessionAssignmentDetailOut(**out.model_dump(), questions=[_question_out(q) for q in questions])


@router.patch("/assignments/{assignment_id}", response_model=GameSessionAssignmentOut)
async def update_assignment(assignment_id: uuid.UUID, body: GameSessionAssignmentUpdate, db: AsyncSession = Depends(get_db)):
    assignment = await _assignment_or_404(db, assignment_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(assignment, field, value)
    await db.commit()
    await db.refresh(assignment)
    return await _assignment_out(db, assignment)


@router.delete("/assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_assignment(assignment_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_lms_content)):
    assignment = await _assignment_or_404(db, assignment_id)
    await db.delete(assignment)
    await db.commit()


# ── assignment questions (independent snapshot copy) ───────────────────

@router.post("/assignments/{assignment_id}/questions", response_model=GameQuestionOut, status_code=status.HTTP_201_CREATED)
async def create_assignment_question(assignment_id: uuid.UUID, body: GameQuestionIn, db: AsyncSession = Depends(get_db)):
    await _assignment_or_404(db, assignment_id)
    position = body.position
    if position is None:
        max_pos = await db.scalar(select(func.max(GameSessionQuestion.position)).where(GameSessionQuestion.assignment_id == assignment_id))
        position = (max_pos or 0) + 1
    existing = (await db.execute(
        select(GameSessionQuestion.id).where(GameSessionQuestion.assignment_id == assignment_id, GameSessionQuestion.position == position)
    )).first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"Position {position} is already taken in this assignment")

    question = GameSessionQuestion(
        id=uuid.uuid4(), assignment_id=assignment_id, position=position, prompt=body.prompt,
        options=[o.model_dump() for o in body.options],
        time_limit_seconds=body.time_limit_seconds, points_mode=body.points_mode,
    )
    db.add(question)
    await db.commit()
    await db.refresh(question)
    return _question_out(question)


@router.patch("/questions/{question_id}", response_model=GameQuestionOut)
async def update_assignment_question(question_id: uuid.UUID, body: GameQuestionUpdate, db: AsyncSession = Depends(get_db)):
    question = await db.get(GameSessionQuestion, question_id)
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Question not found")
    if await _live_run(db, question.assignment_id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Can't edit a question while the game is live — add or delete instead")

    changes = body.model_dump(exclude_unset=True)
    if "position" in changes and changes["position"] != question.position:
        taken = (await db.execute(
            select(GameSessionQuestion.id).where(
                GameSessionQuestion.assignment_id == question.assignment_id, GameSessionQuestion.position == changes["position"],
            )
        )).first()
        if taken:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Position already taken in this assignment")

    for field, value in changes.items():
        setattr(question, field, value)
    await db.commit()
    await db.refresh(question)
    return _question_out(question)


@router.post("/questions/{question_id}/duplicate", response_model=GameQuestionOut, status_code=status.HTTP_201_CREATED)
async def duplicate_assignment_question(question_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    source = await db.get(GameSessionQuestion, question_id)
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Question not found")
    max_pos = await db.scalar(select(func.max(GameSessionQuestion.position)).where(GameSessionQuestion.assignment_id == source.assignment_id))
    copy = GameSessionQuestion(
        id=uuid.uuid4(), assignment_id=source.assignment_id, position=(max_pos or 0) + 1, prompt=source.prompt,
        options=source.options, time_limit_seconds=source.time_limit_seconds, points_mode=source.points_mode,
    )
    db.add(copy)
    await db.commit()
    await db.refresh(copy)
    return _question_out(copy)


@router.post("/assignments/{assignment_id}/questions/reorder", response_model=list[GameQuestionOut])
async def reorder_assignment_questions(assignment_id: uuid.UUID, body: GameQuestionReorderIn, db: AsyncSession = Depends(get_db)):
    await _assignment_or_404(db, assignment_id)
    if await _live_run(db, assignment_id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Can't reorder questions while the game is live")
    questions = (await db.execute(
        select(GameSessionQuestion).where(GameSessionQuestion.assignment_id == assignment_id)
    )).scalars().all()
    by_id = {q.id: q for q in questions}
    if set(body.question_ids) != set(by_id) or len(body.question_ids) != len(by_id):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="question_ids must include every question in this assignment exactly once",
        )
    for offset, question_id in enumerate(body.question_ids, start=1):
        by_id[question_id].position = -offset
    await db.flush()
    for position, question_id in enumerate(body.question_ids, start=1):
        by_id[question_id].position = position
    await db.commit()

    rows = (await db.execute(
        select(GameSessionQuestion).where(GameSessionQuestion.assignment_id == assignment_id).order_by(GameSessionQuestion.position)
    )).scalars().all()
    return [_question_out(q) for q in rows]


@router.delete("/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_assignment_question(question_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    question = await db.get(GameSessionQuestion, question_id)
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Question not found")
    live_run = await _live_run(db, question.assignment_id)
    if live_run is not None:
        await reverse_question_points(db, run=live_run, question_id=question.id)
    await db.delete(question)
    await db.commit()

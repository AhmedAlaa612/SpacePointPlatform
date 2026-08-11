"""Live game facilitator-authoring routes (Live Games Phase 2C, 8-3) —
`/games/admin/*`, gated by `require_lms_content` (same population as
course/mission authoring — operations + facilitator; admin passes
automatically).

Simple CRUD lives directly in the router, matching the established
`routers/lms/admin.py`/`routers/missions/admin.py` convention. `position`
handling (auto-append, collision check, negative-offset reorder) mirrors
`routers/lms/admin.py`'s items section exactly — same shape, new domain.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_lms_content
from app.db.session import get_db
from app.models.games.game import Game, GameQuestion
from app.models.user import User
from app.schemas.games_admin import (
    GameCreate,
    GameDetailOut,
    GameOut,
    GameQuestionIn,
    GameQuestionOut,
    GameQuestionReorderIn,
    GameQuestionUpdate,
    GameUpdate,
)
from app.services.games.points import max_points_for

router = APIRouter(prefix="/games/admin", tags=["games-admin"], dependencies=[Depends(require_lms_content)])


def _question_out(q: GameQuestion) -> GameQuestionOut:
    return GameQuestionOut(
        id=q.id, position=q.position, prompt=q.prompt, options=q.options,
        time_limit_seconds=q.time_limit_seconds, points_mode=q.points_mode,
        max_points=max_points_for(q.points_mode),
    )


async def _game_or_404(db: AsyncSession, game_id: uuid.UUID) -> Game:
    game = await db.get(Game, game_id)
    if game is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Game not found")
    return game


async def _game_out(db: AsyncSession, game: Game) -> GameOut:
    count = await db.scalar(select(func.count()).select_from(GameQuestion).where(GameQuestion.game_id == game.id))
    return GameOut(
        id=game.id, title=game.title, description=game.description, created_by=game.created_by,
        default_time_limit_seconds=game.default_time_limit_seconds, default_floor_pct=game.default_floor_pct,
        default_blackout_count=game.default_blackout_count, created_at=game.created_at, question_count=count or 0,
    )


# ── games ────────────────────────────────────────────────────────────────

@router.get("", response_model=list[GameOut])
async def list_games(db: AsyncSession = Depends(get_db)):
    games = (await db.execute(select(Game).order_by(Game.created_at.desc()))).scalars().all()
    return [await _game_out(db, g) for g in games]


@router.post("", response_model=GameOut, status_code=status.HTTP_201_CREATED)
async def create_game(body: GameCreate, db: AsyncSession = Depends(get_db), current: User = Depends(require_lms_content)):
    game = Game(id=uuid.uuid4(), created_by=current.id, **body.model_dump())
    db.add(game)
    await db.commit()
    await db.refresh(game)
    return await _game_out(db, game)


@router.get("/{game_id}", response_model=GameDetailOut)
async def get_game(game_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    game = await _game_or_404(db, game_id)
    questions = (await db.execute(
        select(GameQuestion).where(GameQuestion.game_id == game_id).order_by(GameQuestion.position)
    )).scalars().all()
    out = await _game_out(db, game)
    return GameDetailOut(**out.model_dump(), questions=[_question_out(q) for q in questions])


@router.patch("/{game_id}", response_model=GameOut)
async def update_game(game_id: uuid.UUID, body: GameUpdate, db: AsyncSession = Depends(get_db)):
    game = await _game_or_404(db, game_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(game, field, value)
    await db.commit()
    await db.refresh(game)
    return await _game_out(db, game)


@router.delete("/{game_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_game(game_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    game = await _game_or_404(db, game_id)
    await db.delete(game)
    await db.commit()


# ── questions ────────────────────────────────────────────────────────────

@router.post("/{game_id}/questions", response_model=GameQuestionOut, status_code=status.HTTP_201_CREATED)
async def create_question(game_id: uuid.UUID, body: GameQuestionIn, db: AsyncSession = Depends(get_db)):
    await _game_or_404(db, game_id)
    position = body.position
    if position is None:
        max_pos = await db.scalar(select(func.max(GameQuestion.position)).where(GameQuestion.game_id == game_id))
        position = (max_pos or 0) + 1
    existing = (await db.execute(
        select(GameQuestion.id).where(GameQuestion.game_id == game_id, GameQuestion.position == position)
    )).first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"Position {position} is already taken in this game")

    question = GameQuestion(
        id=uuid.uuid4(), game_id=game_id, position=position, prompt=body.prompt,
        options=[o.model_dump() for o in body.options],
        time_limit_seconds=body.time_limit_seconds, points_mode=body.points_mode,
    )
    db.add(question)
    await db.commit()
    await db.refresh(question)
    return _question_out(question)


@router.patch("/questions/{question_id}", response_model=GameQuestionOut)
async def update_question(question_id: uuid.UUID, body: GameQuestionUpdate, db: AsyncSession = Depends(get_db)):
    question = await db.get(GameQuestion, question_id)
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Question not found")

    changes = body.model_dump(exclude_unset=True)
    if "position" in changes and changes["position"] != question.position:
        taken = (await db.execute(
            select(GameQuestion.id).where(
                GameQuestion.game_id == question.game_id, GameQuestion.position == changes["position"],
            )
        )).first()
        if taken:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Position already taken in this game")

    for field, value in changes.items():
        setattr(question, field, value)
    await db.commit()
    await db.refresh(question)
    return _question_out(question)


@router.post("/questions/{question_id}/duplicate", response_model=GameQuestionOut, status_code=status.HTTP_201_CREATED)
async def duplicate_question(question_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    source = await db.get(GameQuestion, question_id)
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Question not found")
    max_pos = await db.scalar(select(func.max(GameQuestion.position)).where(GameQuestion.game_id == source.game_id))
    copy = GameQuestion(
        id=uuid.uuid4(), game_id=source.game_id, position=(max_pos or 0) + 1, prompt=source.prompt,
        options=source.options, time_limit_seconds=source.time_limit_seconds, points_mode=source.points_mode,
    )
    db.add(copy)
    await db.commit()
    await db.refresh(copy)
    return _question_out(copy)


@router.post("/{game_id}/questions/reorder", response_model=list[GameQuestionOut])
async def reorder_questions(game_id: uuid.UUID, body: GameQuestionReorderIn, db: AsyncSession = Depends(get_db)):
    await _game_or_404(db, game_id)
    questions = (await db.execute(select(GameQuestion).where(GameQuestion.game_id == game_id))).scalars().all()
    by_id = {q.id: q for q in questions}
    if set(body.question_ids) != set(by_id) or len(body.question_ids) != len(by_id):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="question_ids must include every question in this game exactly once",
        )
    for offset, question_id in enumerate(body.question_ids, start=1):
        by_id[question_id].position = -offset
    await db.flush()
    for position, question_id in enumerate(body.question_ids, start=1):
        by_id[question_id].position = position
    await db.commit()

    rows = (await db.execute(
        select(GameQuestion).where(GameQuestion.game_id == game_id).order_by(GameQuestion.position)
    )).scalars().all()
    return [_question_out(q) for q in rows]


@router.delete("/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question(question_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    question = await db.get(GameQuestion, question_id)
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Question not found")
    await db.delete(question)
    await db.commit()

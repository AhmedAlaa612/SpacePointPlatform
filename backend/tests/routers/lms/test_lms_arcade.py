import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.lms.arcade_game import ArcadeGame, ArcadeGameAttempt
from app.models.lms.program import LmsProgram, LmsProgramAssignment, LmsProgramItem, LmsProgramItemProgress
from app.models.user import User


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _make_user(db: AsyncSession, role: str = "student") -> User:
    user = User(
        id=uuid.uuid4(),
        full_name=f"Arcade User {uuid.uuid4().hex[:6]}",
        email=f"arcade-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        roles=[role],
        status="active",
    )
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_arcade_catalog_and_submit_attempt(db: AsyncSession, client: AsyncClient):
    student = await _make_user(db, "student")
    # Ensure at least one game exists
    game = await db.scalar(select(ArcadeGame).limit(1))
    if game is None:
        game = ArcadeGame(
            id=uuid.uuid4(),
            game_key="orbit",
            position=1,
            module_key="intro",
            module_no="1",
            module_name="Introduction",
            kind="Checkpoint",
            is_3d=False,
            title="Orbit Architect",
            points_explorer=50,
            points_engineer=75,
            is_active=True,
        )
        db.add(game)
        await db.flush()

    # 1. Fetch catalog
    res = await client.get("/lms/arcade/games", headers=_headers(student))
    assert res.status_code == 200
    games = res.json()
    assert len(games) >= 1
    target = next((g for g in games if g["game_key"] == game.game_key), None)
    assert target is not None
    assert target["explorer"]["best_score"] == 0

    # 2. Submit passing attempt in explorer mode
    submit_payload = {
        "mode": "explorer",
        "score": 85,
        "accuracy": 90,
        "passed": True,
        "elapsed_seconds": 32,
        "notes": [{"ok": True, "t": "Well done"}],
    }
    submit_res = await client.post(
        f"/lms/arcade/games/{game.game_key}/attempts",
        json=submit_payload,
        headers=_headers(student),
    )
    assert submit_res.status_code == 201
    attempt_data = submit_res.json()
    assert attempt_data["passed"] is True
    assert attempt_data["score"] == 85
    assert attempt_data["points_awarded"] == game.points_explorer

    # Re-fetch catalog to verify best score is updated
    res2 = await client.get("/lms/arcade/games", headers=_headers(student))
    assert res2.status_code == 200
    target2 = next(g for g in res2.json() if g["game_key"] == game.game_key)
    assert target2["explorer"]["best_score"] == 85
    assert target2["explorer"]["passed"] is True


@pytest.mark.asyncio
async def test_arcade_autopass_reconciliation(db: AsyncSession, client: AsyncClient):
    student = await _make_user(db, "student")
    # Setup an arcade game
    game = await db.scalar(select(ArcadeGame).where(ArcadeGame.game_key == "orbit"))
    if game is None:
        game = ArcadeGame(
            id=uuid.uuid4(),
            game_key="orbit",
            position=1,
            module_key="intro",
            module_no="1",
            module_name="Introduction",
            kind="Checkpoint",
            is_3d=False,
            title="Orbit Architect",
            points_explorer=50,
            points_engineer=75,
            is_active=True,
        )
        db.add(game)
        await db.flush()

    # Pre-record a passing attempt in explorer mode
    attempt = ArcadeGameAttempt(
        id=uuid.uuid4(),
        game_id=game.id,
        user_id=student.id,
        mode="explorer",
        score=95,
        accuracy=100,
        passed=True,
        elapsed_seconds=25,
        attempt_no=1,
    )
    db.add(attempt)

    # Create program, item requiring this game in explorer mode, assignment, and progress
    program = LmsProgram(id=uuid.uuid4(), name="Test Arcade Program")
    db.add(program)
    item = LmsProgramItem(
        id=uuid.uuid4(),
        owner_type="program",
        owner_id=program.id,
        position=1,
        item_type="arcade_game",
        title="Play Orbit Architect",
        arcade_game_id=game.id,
        arcade_game_mode="explorer",
    )
    db.add(item)
    assignment = LmsProgramAssignment(id=uuid.uuid4(), user_id=student.id, lms_program_id=program.id)
    db.add(assignment)
    progress = LmsProgramItemProgress(id=uuid.uuid4(), assignment_id=assignment.id, item_id=item.id, status="pending")
    db.add(progress)
    await db.flush()

    # Query student checklist - verify the item automatically resolves to 'done' (autopass)
    res = await client.get(
        f"/lms/programs/{assignment.id}",
        headers=_headers(student),
    )
    assert res.status_code == 200
    data = res.json()
    checklist_item = next((i for i in data["items"] if i["id"] == str(item.id)), None)
    assert checklist_item is not None
    assert checklist_item["status"] == "done"
    assert checklist_item["arcade_game_key"] == "orbit"
    assert checklist_item["arcade_game_mode"] == "explorer"

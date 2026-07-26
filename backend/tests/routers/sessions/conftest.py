"""Shared test-only setup for the sessions-domain router tests (V2 R2-3,
R2-5).

Two things live here that test_programs_cohorts.py, test_registration_desk.py,
and test_checkin.py all need:

1. Mounting programs.router/cohorts.router/checkin.router onto the app.
   Production wiring for these routers doesn't exist yet — both the R2-3 and
   R2-5 specs explicitly disallow editing app/main.py or
   app/routers/sessions/__init__.py from those tasks, so the routers are
   mounted here, once, for the test session only. (See the bottom of this
   file for exactly what a human needs to add to
   app/routers/sessions/__init__.py to wire them for real.)

2. An "operations" user + a valid JWT for it, built the same way
   app/routers/auth.py's login endpoint builds one (create_access_token),
   since no router tests existed anywhere in this repo yet to copy an
   auth-test-helper pattern from.
"""

import uuid

import pytest_asyncio

from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.models.user import User
from app.routers.sessions.checkin import router as checkin_router
from app.routers.sessions.cohorts import router as cohorts_router
from app.routers.sessions.programs import router as programs_router

_mounted_paths = {getattr(r, "path", None) for r in app.routes}
if "/sessions/programs" not in _mounted_paths:
    app.include_router(programs_router)
if "/sessions/cohorts" not in _mounted_paths:
    app.include_router(cohorts_router)
if "/sessions/checkin" not in _mounted_paths:
    app.include_router(checkin_router)


@pytest_asyncio.fixture
async def operations_user(db) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name="Ops Desk",
        email=f"ops-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("not-a-real-password"),
        roles=["operations"],
        status="active",
    )
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def operations_headers(operations_user: User) -> dict:
    token = create_access_token(operations_user.id, ["operations"])
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def other_role_user(db) -> User:
    """A logged-in user who holds none of the roles require_operations
    allows — used for the 403 role-guard test."""
    user = User(
        id=uuid.uuid4(),
        full_name="Some Intern",
        email=f"intern-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("not-a-real-password"),
        roles=["intern"],
        status="active",
    )
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def other_role_headers(other_role_user: User) -> dict:
    token = create_access_token(other_role_user.id, ["intern"])
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def instructor_user(db) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name="Test Instructor",
        email=f"instructor-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("not-a-real-password"),
        roles=["instructor"],
        status="active",
    )
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def instructor_headers(instructor_user: User) -> dict:
    token = create_access_token(instructor_user.id, ["instructor"])
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def facilitator_user(db) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name="Test Facilitator",
        email=f"facilitator-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("not-a-real-password"),
        roles=["facilitator"],
        status="active",
    )
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def facilitator_headers(facilitator_user: User) -> dict:
    token = create_access_token(facilitator_user.id, ["facilitator"])
    return {"Authorization": f"Bearer {token}"}

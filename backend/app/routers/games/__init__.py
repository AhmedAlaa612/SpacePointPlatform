"""Live games routers (Live Games Phase 2C) — facilitator authoring (8-3)
and per-session assignment (8-4) so far; live-play/manager surfaces land
in later tasks. Aggregate so main.py mounts one set of `/games` routes,
same pattern `routers/missions/__init__.py` uses.
"""

from fastapi import APIRouter

from app.routers.games.admin import router as admin_router
from app.routers.games.sessions import router as sessions_router

router = APIRouter()
router.include_router(admin_router)
router.include_router(sessions_router)

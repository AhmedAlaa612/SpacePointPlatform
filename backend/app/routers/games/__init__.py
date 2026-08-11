"""Live games routers (Live Games Phase 2C) — facilitator authoring surface
(8-3) so far; assignment/live-play/manager surfaces land in later tasks.
Aggregate so main.py mounts one set of `/games` routes, same pattern
`routers/missions/__init__.py` uses.
"""

from fastapi import APIRouter

from app.routers.games.admin import router as admin_router

router = APIRouter()
router.include_router(admin_router)

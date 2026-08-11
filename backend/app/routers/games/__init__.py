"""Live games routers (Live Games Phase 2C) — facilitator authoring (8-3),
per-session assignment (8-4), and the real-time WS transport (8-5) so
far; live-play/manager surfaces land in later tasks. Aggregate so
main.py mounts one set of routes, same pattern
`routers/missions/__init__.py` uses. `realtime_router` carries its own
`/ws/games` prefix (not `/games`) — it's a WebSocket endpoint, not part
of the REST surface the other two cover.
"""

from fastapi import APIRouter

from app.routers.games.admin import router as admin_router
from app.routers.games.realtime import router as realtime_router
from app.routers.games.sessions import router as sessions_router

router = APIRouter()
router.include_router(admin_router)
router.include_router(sessions_router)
router.include_router(realtime_router)

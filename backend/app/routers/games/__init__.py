"""Live games routers (Live Games Phase 2C) — facilitator authoring (8-3),
per-session assignment (8-4), the real-time WS transport (8-5),
instructor live-play (8-7), and student play (8-8). Aggregate so main.py
mounts one set of routes, same pattern `routers/missions/__init__.py`
uses. `realtime_router` carries its own `/ws/games` prefix (not
`/games`) — it's a WebSocket endpoint, not part of the REST surface the
others cover.
"""

from fastapi import APIRouter

from app.routers.games.admin import router as admin_router
from app.routers.games.live import router as live_router
from app.routers.games.realtime import router as realtime_router
from app.routers.games.sessions import router as sessions_router
from app.routers.games.student import router as student_router

router = APIRouter()
router.include_router(admin_router)
router.include_router(sessions_router)
router.include_router(live_router)
router.include_router(student_router)
router.include_router(realtime_router)

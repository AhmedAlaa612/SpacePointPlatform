"""Ground Station routers — aggregated so main.py mounts one set of routes,
same pattern `routers/games/__init__.py` uses. `realtime_router` carries its
own `/ws/ground-station` prefix (a WebSocket endpoint, not part of the REST
surface the others cover).
"""

from fastapi import APIRouter

from app.routers.ground_station.admin import router as admin_router
from app.routers.ground_station.attempts import router as attempts_router
from app.routers.ground_station.console import router as console_router
from app.routers.ground_station.ingest import router as ingest_router
from app.routers.ground_station.realtime import router as realtime_router

router = APIRouter()
router.include_router(admin_router)
router.include_router(attempts_router)
router.include_router(console_router)
router.include_router(ingest_router)
router.include_router(realtime_router)

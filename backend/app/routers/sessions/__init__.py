from fastapi import APIRouter

from app.routers.sessions.checkin import router as checkin_router
from app.routers.sessions.calendar import router as calendar_router
from app.routers.sessions.cohorts import router as cohorts_router
from app.routers.sessions.delivery import router as delivery_router
from app.routers.sessions.imports import router as imports_router
from app.routers.sessions.programs import router as programs_router
from app.routers.sessions.public import router as public_router
from app.routers.sessions.staffing import router as staffing_router
from app.routers.sessions.dashboard import router as dashboard_router
from app.routers.sessions.openings import router as openings_router

# Aggregate all sessions sub-routers under a single router main.py mounts.
# Every sub-router already carries its own prefix (public="/public", the rest
# ="/sessions") — no additional prefix here or at the app.include_router call.
router = APIRouter()
router.include_router(public_router)
# Mounted before the /{session_id}/* routers: `/sessions/delivery-roles` and
# `/sessions/addons/...` are literal paths that a `{session_id}` route would
# otherwise try to parse as a UUID and reject with a 422.
router.include_router(openings_router)
router.include_router(programs_router)
router.include_router(cohorts_router)
router.include_router(checkin_router)
router.include_router(calendar_router)
router.include_router(imports_router)
router.include_router(staffing_router)
router.include_router(delivery_router)
router.include_router(dashboard_router)

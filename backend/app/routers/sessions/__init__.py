from fastapi import APIRouter

from app.routers.sessions.checkin import router as checkin_router
from app.routers.sessions.calendar import router as calendar_router
from app.routers.sessions.cohorts import router as cohorts_router
from app.routers.sessions.day import router as day_router
from app.routers.sessions.delivery import router as delivery_router
from app.routers.sessions.lms_progress import router as lms_progress_router
from app.routers.sessions.imports import router as imports_router
from app.routers.sessions.programs import router as programs_router
from app.routers.sessions.program_certificate_templates import router as program_certificate_templates_router
from app.routers.sessions.public import router as public_router
from app.routers.sessions.staffing import router as staffing_router
from app.routers.sessions.dashboard import router as dashboard_router
from app.routers.sessions.openings import router as openings_router
from app.routers.sessions.journey import router as journey_router
from app.routers.sessions.pre_session_quiz import router as pre_session_quiz_router

# Aggregate all sessions sub-routers under a single router main.py mounts.
# Every sub-router already carries its own prefix (public="/public", the rest
# ="/sessions") — no additional prefix here or at the app.include_router call.
router = APIRouter()
router.include_router(public_router)
# Mounted before the /{session_id}/* routers: `/sessions/delivery-roles` and
# `/sessions/addons/...` are literal paths that a `{session_id}` route would
# otherwise try to parse as a UUID and reject with a 422.
router.include_router(openings_router)
# Same reason as above: /sessions/materials, /sessions/responsibilities and
# /sessions/billable are literal paths that a {session_id} route would try to
# parse as a UUID.
router.include_router(journey_router)
router.include_router(pre_session_quiz_router)
# Same reason again: `/sessions/day-reviews` is a literal path, and a
# `{session_id}` route mounted ahead of it would try to parse "day-reviews"
# as a UUID and 422 before this router ever sees the request.
router.include_router(day_router)
# Mounted before programs_router: `/sessions/programs/stock-template-image`
# and `/sessions/programs/stock-signature-image` are literal paths that
# `/sessions/programs/{program_id}` in programs_router would otherwise intercept
# and fail authentication on.
router.include_router(program_certificate_templates_router)
router.include_router(programs_router)
router.include_router(cohorts_router)
router.include_router(checkin_router)
router.include_router(calendar_router)
router.include_router(imports_router)
router.include_router(staffing_router)
router.include_router(delivery_router)
router.include_router(lms_progress_router)
router.include_router(dashboard_router)

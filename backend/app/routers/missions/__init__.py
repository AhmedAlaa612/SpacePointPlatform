"""Missions routers — student surface (P5-4) + authoring/review surface +
design mission surface (P7-5).

Aggregate so main.py mounts one set of `/missions` routes. `admin_router`
and `design_router` MUST be included before `student_router`: their static
`/missions/admin` and `/missions/design` would otherwise be shadowed by
student_router's dynamic `/missions/{mission_id}` — Starlette matches
routes in registration order, not by specificity, and all three are
exactly one path segment after `/missions/`.
"""

from fastapi import APIRouter

from app.routers.missions.admin import router as admin_router
from app.routers.missions.design import router as design_router
from app.routers.missions.student import router as student_router

router = APIRouter()
router.include_router(admin_router)
router.include_router(design_router)
router.include_router(student_router)

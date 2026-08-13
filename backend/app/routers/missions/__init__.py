"""Missions routers — student surface (P5-4) + authoring/review surface +
design mission surface (P7-5) + operate mission surface (Phase 2B 7B-3) +
intern proposal pipeline (Phase 2B 7B-6) + mission-manager surface
(Phase 2B 7B-7).

Aggregate so main.py mounts one set of `/missions` routes. `admin_router`,
`design_router`, `operate_router`, `proposals_router`, and `manager_router`
MUST be included before `student_router`: their static `/missions/admin`,
`/missions/design`, `/missions/operate`, `/missions/proposals`, and
`/missions/manager` and `/missions/library` would otherwise be shadowed by student_router's
dynamic `/missions/{mission_id}` — Starlette matches routes in
registration order, not by specificity, and all seven are exactly one path
segment after `/missions/`.
"""

from fastapi import APIRouter

from app.routers.missions.admin import router as admin_router
from app.routers.missions.design import router as design_router
from app.routers.missions.library import router as library_router
from app.routers.missions.manager import router as manager_router
from app.routers.missions.operate import router as operate_router
from app.routers.missions.proposals import router as proposals_router
from app.routers.missions.student import router as student_router

router = APIRouter()
router.include_router(admin_router)
router.include_router(design_router)
router.include_router(library_router)
router.include_router(operate_router)
router.include_router(proposals_router)
router.include_router(manager_router)
router.include_router(student_router)

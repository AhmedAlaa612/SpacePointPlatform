"""Missions routers — student surface (P5-4) + authoring/review surface.

Aggregate so main.py mounts one set of `/missions` routes. `admin_router`
MUST be included first: its static `/missions/admin` would otherwise be
shadowed by student_router's dynamic `/missions/{mission_id}` — Starlette
matches routes in registration order, not by specificity, and both are
exactly one path segment after `/missions/`.
"""

from fastapi import APIRouter

from app.routers.missions.admin import router as admin_router
from app.routers.missions.student import router as student_router

router = APIRouter()
router.include_router(admin_router)
router.include_router(student_router)

"""Instructor assessment & performance ranking routers (2026-09) — question
bank authoring, cohort assignment, and instructor-facing attempts. Rating
and ranking-weight routes join this same aggregate as they land (see
`app/models/instructor_assessment/__init__.py` for the domain overview).
Aggregated so `main.py` mounts one set of routes, same pattern
`routers/games/__init__.py` uses.
"""

from fastapi import APIRouter

from app.routers.instructor_assessment.admin import router as admin_router
from app.routers.instructor_assessment.attempt_review import router as attempt_review_router
from app.routers.instructor_assessment.attempts import router as attempts_router
from app.routers.instructor_assessment.cohorts import router as cohorts_router
from app.routers.instructor_assessment.ratings import router as ratings_router
from app.routers.instructor_assessment.performance import router as performance_router
from app.routers.instructor_assessment.ranking import router as ranking_router

router = APIRouter()
router.include_router(admin_router)
router.include_router(cohorts_router)
router.include_router(attempts_router)
router.include_router(attempt_review_router)
router.include_router(ratings_router)
router.include_router(performance_router)
router.include_router(ranking_router)

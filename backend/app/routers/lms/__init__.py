"""LMS routers (LM1-3) — the student surface.

Aggregate so main.py mounts one `/lms` router; LM1-4 (auth) and LM1-5
(authoring) will join it later.
"""

from fastapi import APIRouter

from app.routers.lms.student import router as student_router

router = APIRouter()
router.include_router(student_router)
"""LMS routers — student surface (LM1-3) + authoring surface (LM1-5).

Aggregate so main.py mounts one set of `/lms` routes.
"""

from fastapi import APIRouter

from app.routers.lms.admin import router as admin_router
from app.routers.lms.student import router as student_router

router = APIRouter()
router.include_router(student_router)
router.include_router(admin_router)
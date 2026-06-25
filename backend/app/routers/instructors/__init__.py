from fastapi import APIRouter

from app.routers.instructors.applicant import router as applicant_router
from app.routers.instructors.admin import router as admin_router

# Aggregate all instructors sub-routers under a single router that main.py
# mounts under /instructors (mirrors routers/ambassadors/__init__.py).
router = APIRouter()
router.include_router(applicant_router)
router.include_router(admin_router)

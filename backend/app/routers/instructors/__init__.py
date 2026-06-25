from fastapi import APIRouter

from app.routers.instructors.applicant import router as applicant_router
from app.routers.instructors.admin import router as admin_router
from app.routers.instructors.instructor import router as instructor_router
from app.routers.instructors.training import router as training_router
from app.routers.instructors.library import router as library_router
from app.routers.instructors.payments import router as payments_router
from app.routers.instructors.facilitator import router as facilitator_router

# Aggregate all instructors sub-routers under a single router that main.py
# mounts under /instructors (mirrors routers/ambassadors/__init__.py).
router = APIRouter()
router.include_router(applicant_router)
router.include_router(admin_router)
router.include_router(instructor_router)
router.include_router(training_router)
router.include_router(library_router)
router.include_router(payments_router)
router.include_router(facilitator_router)

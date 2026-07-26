from fastapi import APIRouter

from app.routers.spine.contacts import router as contacts_router
from app.routers.spine.merge_reviews import router as merge_reviews_router

# Aggregate all spine sub-routers under a single router that main.py will
# mount at root (this codebase has no /api prefix anywhere — see app/main.py).
# Each sub-router already carries its own prefix="/spine", matching the
# ambassadors/sessions aggregate-router pattern.
router = APIRouter()
router.include_router(contacts_router)
router.include_router(merge_reviews_router)

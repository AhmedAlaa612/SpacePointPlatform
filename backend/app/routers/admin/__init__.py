from fastapi import APIRouter

from app.routers.admin.users import router as users_router
from app.routers.admin.settings import router as settings_router
from app.routers.admin.applications import router as applications_router

# Aggregate all admin sub-routers under a single router that main.py mounts under /admin
router = APIRouter()
router.include_router(users_router)
router.include_router(settings_router)
router.include_router(applications_router)

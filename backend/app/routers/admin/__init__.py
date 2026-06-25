from fastapi import APIRouter

from app.routers.admin.users import router as users_router

# Aggregate all admin sub-routers under a single router that main.py mounts under /admin
router = APIRouter()
router.include_router(users_router)

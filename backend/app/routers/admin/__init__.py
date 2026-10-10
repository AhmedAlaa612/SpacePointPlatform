from fastapi import APIRouter

from app.routers.admin.users import router as users_router
from app.routers.admin.settings import router as settings_router
from app.routers.admin.applications import router as applications_router
from app.routers.admin.birthdays import router as birthdays_router
from app.routers.admin.website_config import router as website_config_router
from app.routers.admin.website_programs import router as website_programs_router
from app.routers.admin.website_sponsors import router as website_sponsors_router
from app.routers.admin.website_content import router as website_content_router
from app.routers.admin.website_articles import router as website_articles_router
from app.routers.admin.website_people import router as website_people_router
from app.routers.admin.website_labs import router as website_labs_router
from app.routers.shop_admin import router as shop_admin_router

# Aggregate all admin sub-routers under a single router that main.py mounts under /admin
router = APIRouter()
router.include_router(users_router)
router.include_router(settings_router)
router.include_router(applications_router)
router.include_router(birthdays_router, prefix="/birthdays")
router.include_router(website_config_router)
router.include_router(website_programs_router)
router.include_router(website_sponsors_router)
router.include_router(website_content_router)
router.include_router(website_articles_router)
router.include_router(website_people_router)
router.include_router(website_labs_router)
router.include_router(shop_admin_router)

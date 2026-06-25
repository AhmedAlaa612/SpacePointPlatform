from fastapi import APIRouter

from app.routers.ambassadors.leads import router as leads_router
from app.routers.ambassadors.tasks import router as tasks_router
from app.routers.ambassadors.network import router as network_router
from app.routers.ambassadors.dashboard import router as dashboard_router
from app.routers.ambassadors.titles import router as titles_router
from app.routers.ambassadors.badges import router as badges_router
from app.routers.ambassadors.teacher import router as teacher_router
from app.routers.ambassadors.points import router as points_router
from app.routers.ambassadors.achievements import router as achievements_router
from app.routers.ambassadors.materials import router as materials_router
from app.routers.ambassadors.public import router as public_router

# Aggregate all ambassador sub-routers under a single router
# that main.py will mount under /ambassadors
router = APIRouter()
router.include_router(leads_router)
router.include_router(tasks_router)
router.include_router(network_router)
router.include_router(dashboard_router)
router.include_router(titles_router)
router.include_router(badges_router)
router.include_router(teacher_router)
router.include_router(points_router)
router.include_router(achievements_router)
router.include_router(materials_router)
router.include_router(public_router)

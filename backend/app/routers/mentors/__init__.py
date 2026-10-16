from fastapi import APIRouter

from app.routers.mentors.mentor import router as mentor_router
from app.routers.mentors.operations import router as operations_router
from app.routers.mentors.public import router as public_router

router = APIRouter()
router.include_router(operations_router)
router.include_router(mentor_router)
router.include_router(public_router)

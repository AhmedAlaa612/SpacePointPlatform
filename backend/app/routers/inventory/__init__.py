from fastapi import APIRouter

from app.routers.inventory.catalog import router as catalog_router
from app.routers.inventory.checks import router as checks_router
from app.routers.inventory.kits import router as kits_router
from app.routers.inventory.stock import router as stock_router

# Every sub-router already carries the "/inventory" prefix — no extra prefix
# here or at the app.include_router call. No "/api" anywhere; nginx strips it.
router = APIRouter()
router.include_router(catalog_router)
router.include_router(kits_router)
router.include_router(stock_router)
router.include_router(checks_router)

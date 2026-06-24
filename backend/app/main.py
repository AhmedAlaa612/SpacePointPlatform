from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import auth

app = FastAPI(title=settings.PROJECT_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)

# Domain routers are mounted here as Phases 1–5 land (PLAN §3 / §12):
#   app.include_router(interns_router,     prefix="/interns")
#   app.include_router(ambassadors_router, prefix="/ambassadors")
#   app.include_router(instructors_router, prefix="/instructors")
#   app.include_router(admin_router,       prefix="/admin")
#   app.include_router(apply_router,       prefix="/apply")


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "service": settings.PROJECT_NAME}

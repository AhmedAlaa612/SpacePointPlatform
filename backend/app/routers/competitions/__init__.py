"""Competition judging routers (2026-08-24) — aggregate so main.py mounts
one set of routes. `admin_router` is `/competitions/admin/*` (ops:
`require_lms_content`, same authoring gate `/lms/admin` uses); `judge_router`
is `/competitions/judge/*` (`require_judge`). Both prefixes are static and
one segment deep, so registration order between them doesn't matter — unlike
`routers/missions/__init__.py`'s ordering constraint, there's no dynamic
top-level route here to shadow.

Mounted at its own top-level prefix, not nested under `/lms/` or
`/missions/`: judging is neither checklist authoring nor a mission
attempt, and a judge account should never need to know either of those
domains exist.
"""

from fastapi import APIRouter

from app.routers.competitions.admin import router as admin_router
from app.routers.competitions.judge import router as judge_router

router = APIRouter()
router.include_router(admin_router)
router.include_router(judge_router)

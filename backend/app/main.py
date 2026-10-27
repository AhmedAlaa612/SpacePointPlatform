import logging
from contextlib import asynccontextmanager

from arq import create_pool
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.log_context import RequestContextMiddleware, configure_logging

# Must run before any router import below — those transitively import every
# service/model module, and this needs to be active before any of them could
# ever log. Safe to call at import time (rather than needing an on_startup
# hook, unlike the worker process — see app/workers/main.py): uvicorn's own
# Config.__init__ runs its own dictConfig *before* it imports "app.main:app",
# so this call runs strictly after uvicorn's and wins, since it explicitly
# redeclares the uvicorn.* logger names below.
configure_logging(level=settings.LOG_LEVEL)

from app.routers import admin, auth, documents, notifications
from app.routers.public_website import router as public_website_router
from app.routers.public_sponsors import router as public_sponsors_router
from app.routers.public_content import router as public_content_router
from app.routers.public_articles import router as public_articles_router
from app.routers.public_people import router as public_people_router
from app.routers.public_labs import router as public_labs_router
from app.routers.public_shop import router as public_shop_router
from app.routers.public_events import router as public_events_router
from app.routers.organization_events import router as organization_events_router
from app.routers.organization_programs import router as organization_programs_router
from app.routers.contributor_articles import router as contributor_articles_router
from app.routers.admin.birthdays import router as birthdays_router
from app.routers.apply import router as apply_router
from app.routers.internship import router as internship_router
from app.routers.files import router as files_router
from app.routers.interns import admin as interns_admin
from app.routers.interns import intern as interns_intern
from app.routers.interns import leader as interns_leader
from app.routers.interns import shared as interns_shared
from app.routers.ambassadors import router as ambassadors_router
from app.routers.instructors import router as instructors_router
from app.routers.inventory import router as inventory_router
from app.routers.games import router as games_router
from app.routers.ground_station import router as ground_station_router
from app.routers.instructor_assessment import router as instructor_assessment_router
from app.services.games.realtime import get_realtime_redis
from app.routers.competitions import router as competitions_router
from app.routers.lms import router as lms_router
from app.routers.missions import router as missions_router
from app.routers.sessions import router as sessions_router
from app.routers.spine import router as spine_router
from app.routers.teams import router as teams_router
from app.routers.video import router as video_router
from app.routers.mentors import router as mentors_router
from app.routers.operations_test_accounts import router as operations_test_accounts_router
from app.workers.heartbeat import HEARTBEAT_KEY
from app.workers.settings import redis_settings


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ARQ connection pool for *enqueueing* jobs from the web process (V2
    # R2-1) — separate from the worker process itself (app/workers/main.py),
    # which consumes them. Stored on app.state so routers can reach it via
    # the get_arq_redis dependency below.
    #
    # Redis being unreachable must never take the whole API down with it
    # (2026-07-24) — local dev without Docker running, or a real Redis blip
    # in production, should still serve every non-ARQ route. `app.state.arq_redis`
    # is None in that case; callers use workers.settings.safe_enqueue, which
    # no-ops (logged) instead of raising — same "a failed side-effect must
    # never undo a successful request" convention issue_ticket() already
    # follows for email sends.
    try:
        app.state.arq_redis = await create_pool(redis_settings())
    except Exception:
        logger.warning(
            "Could not connect to Redis at startup — ticket/import-batch emails "
            "will be skipped until it's available. The API itself still starts.",
            exc_info=True,
        )
        app.state.arq_redis = None

    # Live games' real-time broadcast connection (8-7) — separate from the
    # ARQ pool above (job-queue traffic, different tuning); same
    # None-if-unreachable resilience, see get_realtime_redis_dep.
    try:
        app.state.realtime_redis = get_realtime_redis()
        await app.state.realtime_redis.ping()
    except Exception:
        logger.warning(
            "Could not connect to Redis for live-games broadcasts at startup — "
            "the API itself still starts; broadcasts drop until it's available.",
            exc_info=True,
        )
    try:
        from app.db.session import AsyncSessionLocal, engine
        from app.models.website_event import MegaEvent, WebsiteEvent
        from app.services.website_events import ensure_default_events_seeded
        from sqlalchemy import text
        async with engine.begin() as conn:
            await conn.execute(text("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'organization';"))
            await conn.run_sync(
                lambda sync_conn: MegaEvent.__table__.create(sync_conn, checkfirst=True)
            )
            await conn.run_sync(
                lambda sync_conn: WebsiteEvent.__table__.create(sync_conn, checkfirst=True)
            )
        async with AsyncSessionLocal() as db:
            await db.execute(text("ALTER TABLE cohorts ADD COLUMN IF NOT EXISTS checklist_title_override VARCHAR(255);"))
            await db.execute(text("ALTER TABLE cohorts ADD COLUMN IF NOT EXISTS submission_windows JSONB DEFAULT '[]'::jsonb;"))
            await db.execute(text("ALTER TABLE learner_teams ADD COLUMN IF NOT EXISTS first_locked_at TIMESTAMP WITH TIME ZONE;"))
            await db.execute(text("ALTER TABLE learner_teams ADD COLUMN IF NOT EXISTS timing_adjustment_override DOUBLE PRECISION;"))
            await db.execute(text("ALTER TABLE learner_teams ADD COLUMN IF NOT EXISTS timing_adjustment_notes VARCHAR(255);"))
            await db.execute(text("ALTER TABLE cohort_media_consents ADD COLUMN IF NOT EXISTS student_email_raw VARCHAR(255);"))
            await db.execute(text("ALTER TABLE competition_rubric_criteria ADD COLUMN IF NOT EXISTS scored_by VARCHAR(32) DEFAULT 'judge';"))
            await db.execute(text("ALTER TABLE competition_rubric_criteria ADD COLUMN IF NOT EXISTS sub_criteria JSONB DEFAULT '[]'::jsonb;"))
            await db.execute(text("ALTER TABLE learner_teams ADD COLUMN IF NOT EXISTS ops_criterion_scores JSONB DEFAULT '{}'::jsonb;"))
            await db.execute(text("ALTER TABLE learner_teams ADD COLUMN IF NOT EXISTS ops_criterion_notes TEXT;"))
            await db.execute(text("ALTER TABLE learner_teams ADD COLUMN IF NOT EXISTS ops_scored_by UUID REFERENCES users(id) ON DELETE SET NULL;"))
            await db.execute(text("ALTER TABLE learner_teams ADD COLUMN IF NOT EXISTS ops_scored_at TIMESTAMP WITH TIME ZONE;"))
            await db.execute(text("ALTER TABLE mega_events ADD COLUMN IF NOT EXISTS top_banner_url VARCHAR(512);"))
            await db.execute(text("ALTER TABLE website_events ADD COLUMN IF NOT EXISTS top_banner_url VARCHAR(512);"))
            await db.execute(text("ALTER TABLE mega_events ADD COLUMN IF NOT EXISTS default_language VARCHAR(8) DEFAULT 'en';"))
            await db.execute(text("ALTER TABLE mega_events ADD COLUMN IF NOT EXISTS ar_content JSONB DEFAULT '{}'::jsonb;"))
            await db.execute(text("ALTER TABLE website_events ADD COLUMN IF NOT EXISTS default_language VARCHAR(8) DEFAULT 'en';"))
            await db.execute(text("ALTER TABLE website_events ADD COLUMN IF NOT EXISTS ar_content JSONB DEFAULT '{}'::jsonb;"))
            await db.execute(text("UPDATE cohorts SET checklist_title_override = 'testcohortname', name = 'Cohort Test' WHERE name = 'testcohortname';"))
            await db.commit()
            await ensure_default_events_seeded(db)
            try:
                from app.services.lms.arcade import ensure_arcade_games_seeded
                await ensure_arcade_games_seeded(db)
            except Exception:
                logger.warning("Could not auto-seed arcade games at startup", exc_info=True)
    except Exception:
        logger.warning("Could not auto-add schema updates or seed events at startup", exc_info=True)

    yield
    if app.state.arq_redis is not None:
        await app.state.arq_redis.aclose()
    if app.state.realtime_redis is not None:
        await app.state.realtime_redis.aclose()


app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(dict.fromkeys(settings.cors_origins + settings.public_form_origins)),
    allow_origin_regex=r"https?://((localhost|127\.0\.0\.1)(:\d+)?|([a-z0-9-]+\.)?spacepoint\.ae)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Without this the browser can read every *other* response header fine
    # but silently drops X-Request-ID — CORS hides any response header not
    # explicitly exposed, even same-origin-looking XHR/fetch calls that go
    # through this middleware at all (any cross-origin call, which is most
    # of them: the frontend and API run on different ports even in dev).
    # Media & document viewers (pdf.js) also require Range and Length headers.
    expose_headers=[
        "X-Request-ID",
        "Content-Disposition",
        "Content-Length",
        "Accept-Ranges",
        "Content-Range",
        "X-Pdf-Key",
        "X-Pdf-Iv",
    ],
)

# Raw ASGI middleware, not @app.middleware("http") — see
# RequestContextMiddleware's own docstring (app/core/log_context.py) for
# why: BaseHTTPMiddleware's dispatch function returns before the response
# is actually sent, so resetting context there (the previous version of
# this) ran before uvicorn's own access-log line and any unhandled
# exception's traceback log ever saw it.
app.add_middleware(RequestContextMiddleware)


app.include_router(auth.router)
app.include_router(files_router)          # public (HMAC-signed): /files/* — local storage backend
app.include_router(apply_router)          # public: /apply/*
app.include_router(public_website_router)  # public: /public/website/* (Step 1 — website global config)
app.include_router(public_sponsors_router)  # public: /public/sponsors (Step 3 — partners & clients showcase; path predates the /public/website/* namespace)
app.include_router(public_content_router)  # public: /public/faqs, /public/media, /public/newsletters, /public/newsletter/subscribe (Step 4)
app.include_router(public_articles_router)  # public: /public/articles, /public/articles/{slug} (Step 5)
app.include_router(public_people_router)  # public: /public/team, /ambassadors, /alumni, /student-missions (Step 6)
app.include_router(public_labs_router)  # public: /public/labs/projects (Step 7)
app.include_router(public_shop_router)  # public: /public/shop/* (Step 7 — products, checkout, webhook)
app.include_router(public_events_router)  # public: /public/website/events/* (Step 8 — events & mega-events)
app.include_router(organization_events_router)  # organization self-service: /organization/* (Step 8)
app.include_router(organization_programs_router)  # organization self-service: /organization/programs, /organization/cohorts/*
app.include_router(contributor_articles_router)  # contributor: /articles/me, /articles (Step 5)
app.include_router(notifications.router)  # shared: /notifications/*
app.include_router(documents.router)  # shared: /documents/*  (Phase 4)
app.include_router(admin.router, prefix="/admin")  # shared: /admin/users/*  (generic user management)
app.include_router(birthdays_router, prefix="/api/v1/admin/birthdays")

# Internship request/letter (2026-08-20) — /me/role-requests, /admin/role-requests/*,
# /intern/internship-letter/*. Not nested under /interns (kanban domain) or
# /instructors — see routers/internship.py's module docstring.
app.include_router(internship_router)

# Interns domain (Phase 1) — /interns/*
app.include_router(interns_admin.router, prefix="/interns")
app.include_router(interns_leader.router, prefix="/interns")
app.include_router(interns_intern.router, prefix="/interns")
app.include_router(interns_shared.router, prefix="/interns")

# Ambassadors domain (Phase 2) — /ambassadors/*
app.include_router(ambassadors_router, prefix="/ambassadors")

# Instructors domain (Phase 3) — /instructors/*  (public apply endpoint lives
# in routers/auth.py — /auth/instructor-apply — matching the existing
# instructor pipeline convention, not a separate /apply/* router)
app.include_router(instructors_router, prefix="/instructors")

# Sessions domain (V2 R1-5+): /public/register/{cohort_key}, /sessions/*
app.include_router(sessions_router)

# Spine domain (V2 R2-4): /spine/contacts/*, /spine/organizations/*, /spine/merge-reviews/*
app.include_router(spine_router)

# Inventory domain (I1-3): /inventory/*
app.include_router(inventory_router)

# LMS domain (LM1-3): /lms/*
app.include_router(lms_router)

# Missions domain (Phase 2 Stage 5): /missions/*
app.include_router(missions_router)

# Team membership (2026-08-17, generalized out of missions): /teams/*
app.include_router(teams_router)

# Live games domain (Live Games Phase 2C): /games/*
app.include_router(games_router)

# Ground Station domain (2026-09): /ground-station/*, /ws/ground-station/*
# — live CubeSat telemetry/command tool ported from the legacy Madar platform.
app.include_router(ground_station_router)

# Competition judging domain (2026-08-24): /competitions/*
app.include_router(competitions_router)

# Instructor assessment & performance ranking domain (2026-09): /instructor-assessment/*
app.include_router(instructor_assessment_router)

# Standardized video service's own playback surface (2026-09): /videos/*
# — one route for every hls_encrypted video regardless of owner_type. See
# routers/video.py's module docstring.
app.include_router(video_router)

# Mentorship platform: /operations/mentor-domains, /operations/mentors/*, /mentors/*
app.include_router(mentors_router)

# Operations test accounts management (@spacepoint.local & cascade delete): /operations/test-accounts/*
app.include_router(operations_test_accounts_router)


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "service": settings.PROJECT_NAME}


@app.get("/health/worker", tags=["health"])
async def health_worker(request: Request):
    if request.app.state.arq_redis is None:
        return {"status": "down", "last_heartbeat": None}
    last_beat = await request.app.state.arq_redis.get(HEARTBEAT_KEY)
    return {"status": "ok" if last_beat else "down", "last_heartbeat": last_beat}

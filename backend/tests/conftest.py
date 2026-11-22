"""Shared pytest fixtures.

Bootstrapped in V2 R1-3 — no test harness existed before this (the full
monorepo/CI test setup is still V2 C0-2). This is deliberately minimal: one
fixture giving a test an AsyncSession, wrapped in a transaction that's rolled
back afterward so tests never leave data behind in DATABASE_URL_TEST and never
touch DATABASE_URL (the dev database) at all.

Tests use `await db.flush()`, never `await db.commit()` — everything stays
inside the one outer transaction this fixture rolls back at teardown.
"""

import httpx
import pytest
import pytest_asyncio
from arq import create_pool
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.services import storage, storage_local
from app.services.games.realtime import get_realtime_redis_dep
from app.workers.settings import get_arq_redis, redis_settings

if not settings.DATABASE_URL_TEST:
    raise RuntimeError(
        "DATABASE_URL_TEST is not set — add it to backend/.env before running tests. "
        "It must point at a dedicated test database, never DATABASE_URL."
    )
if not settings.REDIS_URL_TEST:
    raise RuntimeError(
        "REDIS_URL_TEST is not set — add it to backend/.env before running tests. "
        "It must be a separate Redis logical DB index, never REDIS_URL."
    )


@pytest.fixture(autouse=True)
def _no_real_r2_in_tests(monkeypatch):
    """`video_service.py` hardcodes `storage_backend="r2"` for every new
    upload (see `_NEW_UPLOAD_BACKEND`) — deliberate for production (VPS is no
    longer a valid upload destination), but it means any test that attaches a
    video would otherwise reach for real Cloudflare R2 credentials this
    environment doesn't have and must never have (the R2 secret access key
    never belongs in CI/this repo). Route a "r2" backend through the same
    local-disk backend every other test already uses; storage_r2.py's own
    wire behavior (SigV4 signing, key prefixing) is not this fixture's
    concern to re-verify."""
    real_impl = storage._impl

    def _impl(backend: str | None = None):
        name = backend or settings.STORAGE_BACKEND
        if name == "r2":
            return storage_local
        return real_impl(backend)

    monkeypatch.setattr(storage, "_impl", _impl)


@pytest_asyncio.fixture(scope="session")
async def _engine():
    # Created inside a fixture (not at module import time) so it's bound to
    # the event loop pytest-asyncio actually runs tests in — an asyncpg
    # connection pool created before any loop exists breaks across tests
    # with "another operation is in progress" once a second test reuses it.
    from sqlalchemy import text
    from app.db.base import Base
    import app.models  # noqa: F401

    engine = create_async_engine(settings.DATABASE_URL_TEST)
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, checkfirst=True))
        await conn.execute(text("ALTER TABLE learner_teams ADD COLUMN IF NOT EXISTS final_lock_penalty DOUBLE PRECISION;"))
        await conn.execute(text("ALTER TABLE learner_teams ADD COLUMN IF NOT EXISTS final_lock_notes VARCHAR(255);"))
        await conn.execute(text("ALTER TABLE lms_program_team_item_progress ADD COLUMN IF NOT EXISTS penalty_points DOUBLE PRECISION;"))
        await conn.execute(text("ALTER TABLE lms_program_team_item_progress ADD COLUMN IF NOT EXISTS penalty_notes VARCHAR(255);"))
        await conn.execute(text("ALTER TABLE instructor_checklist_progress ADD COLUMN IF NOT EXISTS sub_item_proofs JSONB NOT NULL DEFAULT '{}'::jsonb;"))
        await conn.execute(text("ALTER TABLE session_ops_checklist_progress ADD COLUMN IF NOT EXISTS sub_item_proofs JSONB NOT NULL DEFAULT '{}'::jsonb;"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS org_role VARCHAR(32);"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS org_roles VARCHAR(32)[] NOT NULL DEFAULT '{}';"))
        await conn.execute(text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS readiness_scope VARCHAR(32) NOT NULL DEFAULT 'own';"))
        await conn.execute(text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS allowed_readiness_preset_ids JSONB NOT NULL DEFAULT '[]'::jsonb;"))
        await conn.execute(text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS program_scope VARCHAR(20) NOT NULL DEFAULT 'own';"))
        await conn.execute(text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS allowed_program_ids JSONB NOT NULL DEFAULT '[]'::jsonb;"))
        await conn.execute(text("ALTER TABLE cohorts ADD COLUMN IF NOT EXISTS management_mode VARCHAR(20) NOT NULL DEFAULT 'spacepoint';"))
        await conn.execute(text("ALTER TABLE locations ADD COLUMN IF NOT EXISTS organization_id UUID REFERENCES organizations(id) ON DELETE SET NULL;"))
        await conn.execute(text("ALTER TABLE pre_session_quiz_questions ADD COLUMN IF NOT EXISTS organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE;"))
        await conn.execute(text("ALTER TABLE pre_session_quiz_datasheets ADD COLUMN IF NOT EXISTS organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE;"))
        await conn.execute(text("ALTER TABLE pre_session_quiz_presets ADD COLUMN IF NOT EXISTS organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE;"))
        await conn.execute(text("ALTER TABLE cohorts ADD COLUMN IF NOT EXISTS inherit_default_checklists BOOLEAN NOT NULL DEFAULT TRUE;"))
        await conn.execute(text("ALTER TABLE cohorts ADD COLUMN IF NOT EXISTS variation_id UUID REFERENCES program_variations(id) ON DELETE SET NULL;"))
        await conn.execute(text("ALTER TABLE cohorts ADD COLUMN IF NOT EXISTS is_template_legacy BOOLEAN NOT NULL DEFAULT FALSE;"))
        await conn.execute(text("ALTER TABLE cohorts ADD COLUMN IF NOT EXISTS pricing_model VARCHAR(24);"))
        await conn.execute(text("ALTER TABLE cohorts ADD COLUMN IF NOT EXISTS price NUMERIC(10, 2);"))
        await conn.execute(text("ALTER TABLE cohorts ADD COLUMN IF NOT EXISTS completion_rule_type VARCHAR(16);"))
        await conn.execute(text("ALTER TABLE cohorts ADD COLUMN IF NOT EXISTS completion_rule_value NUMERIC(6, 2);"))
        await conn.execute(text("ALTER TABLE cohorts ADD COLUMN IF NOT EXISTS default_certificate_template_id UUID REFERENCES program_certificate_templates(id) ON DELETE SET NULL;"))
        await conn.execute(text("ALTER TABLE cohorts ADD COLUMN IF NOT EXISTS default_team_certificate_template_id UUID REFERENCES program_certificate_templates(id) ON DELETE SET NULL;"))
        await conn.execute(text("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS instructor_checklist_overridden BOOLEAN NOT NULL DEFAULT FALSE;"))
        await conn.execute(text("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS internal_checklist_overridden BOOLEAN NOT NULL DEFAULT FALSE;"))
        await conn.execute(text("ALTER TABLE delivery_checklist_items ADD COLUMN IF NOT EXISTS variation_id UUID REFERENCES program_variations(id) ON DELETE CASCADE;"))
        await conn.execute(text("ALTER TABLE delivery_checklist_items ADD COLUMN IF NOT EXISTS variation_day_id UUID REFERENCES program_variation_days(id) ON DELETE CASCADE;"))
        await conn.execute(text("ALTER TABLE delivery_checklist_items DROP CONSTRAINT IF EXISTS ck_delivery_checklist_exactly_one_owner;"))
        await conn.execute(text(
            "ALTER TABLE delivery_checklist_items ADD CONSTRAINT ck_delivery_checklist_exactly_one_owner CHECK ("
            "(CASE WHEN program_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN variation_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN variation_day_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN cohort_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN session_id IS NOT NULL THEN 1 ELSE 0 END) = 1);"
        ))
        await conn.execute(text("ALTER TABLE pre_session_quiz_assignments ADD COLUMN IF NOT EXISTS variation_id UUID REFERENCES program_variations(id) ON DELETE CASCADE;"))
        await conn.execute(text("ALTER TABLE pre_session_quiz_assignments ADD COLUMN IF NOT EXISTS variation_day_id UUID REFERENCES program_variation_days(id) ON DELETE CASCADE;"))
        await conn.execute(text("ALTER TABLE pre_session_quiz_assignments DROP CONSTRAINT IF EXISTS ck_pre_session_quiz_assignment_one_owner;"))
        await conn.execute(text(
            "ALTER TABLE pre_session_quiz_assignments ADD CONSTRAINT ck_pre_session_quiz_assignment_one_owner CHECK ("
            "(CASE WHEN program_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN variation_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN variation_day_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN cohort_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN session_id IS NOT NULL THEN 1 ELSE 0 END) = 1);"
        ))
        await conn.execute(text("ALTER TABLE program_openings ALTER COLUMN program_id DROP NOT NULL;"))
        await conn.execute(text("ALTER TABLE program_openings ADD COLUMN IF NOT EXISTS variation_id UUID REFERENCES program_variations(id) ON DELETE CASCADE;"))
        await conn.execute(text("ALTER TABLE program_openings DROP CONSTRAINT IF EXISTS uq_program_opening_role;"))
        await conn.execute(text("ALTER TABLE program_openings DROP CONSTRAINT IF EXISTS ck_program_opening_one_owner;"))
        await conn.execute(text(
            "ALTER TABLE program_openings ADD CONSTRAINT ck_program_opening_one_owner CHECK ("
            "(CASE WHEN program_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN variation_id IS NOT NULL THEN 1 ELSE 0 END) = 1);"
        ))
        await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_program_opening_role ON program_openings (program_id, role_id) WHERE program_id IS NOT NULL;"))
        await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_program_opening_variation_role ON program_openings (variation_id, role_id) WHERE variation_id IS NOT NULL;"))
        await conn.execute(text("ALTER TABLE session_materials ADD COLUMN IF NOT EXISTS variation_id UUID REFERENCES program_variations(id) ON DELETE CASCADE;"))
        await conn.execute(text("ALTER TABLE session_materials DROP CONSTRAINT IF EXISTS ck_material_exactly_one_owner;"))
        await conn.execute(text(
            "ALTER TABLE session_materials ADD CONSTRAINT ck_material_exactly_one_owner CHECK ("
            "(CASE WHEN program_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN variation_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN cohort_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN session_id IS NOT NULL THEN 1 ELSE 0 END) = 1);"
        ))
        await conn.execute(text("ALTER TABLE competition_rubrics ADD COLUMN IF NOT EXISTS variation_id UUID REFERENCES program_variations(id) ON DELETE CASCADE;"))
        await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_competition_rubrics_variation_id ON competition_rubrics (variation_id) WHERE variation_id IS NOT NULL;"))
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db(_engine):
    async with _engine.connect() as conn:
        trans = await conn.begin()
        # join_transaction_mode="create_savepoint" tells the session the
        # connection already has an externally-managed transaction (ours,
        # for rollback-based test isolation) — without it, any code under
        # test that opens its own nested transaction (SAVEPOINTs, used by
        # merge_contacts/register for conflict handling) fights with this
        # fixture's transaction and SQLAlchemy warns "transaction already
        # deassociated from connection" instead of cleanly nesting.
        session = AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()


@pytest_asyncio.fixture
async def db_session(db):
    yield db


@pytest_asyncio.fixture(scope="session")
async def _arq_engine():
    pool = await create_pool(redis_settings(settings.REDIS_URL_TEST))
    yield pool
    await pool.close()


@pytest_asyncio.fixture
async def arq_redis(_arq_engine):
    """A real ARQ pool against REDIS_URL_TEST (never REDIS_URL) — enqueuing a
    job doesn't require a running worker to succeed, so this is enough to
    assert a job was queued without needing a live worker process in tests.
    Flushed after every test so queued jobs don't leak between tests.

    Requesting this fixture is what makes a test need a live Redis. Nothing
    else should depend on it — see `client` vs `arq_client` below."""
    yield _arq_engine
    await _arq_engine.flushdb()


@pytest_asyncio.fixture
async def realtime_redis():
    """A real redis.asyncio connection against REDIS_URL_TEST (never
    REDIS_URL) for the live-games pub/sub tests (8-5). Flushed after
    every test so channels/keys don't leak between tests. Requesting
    this fixture is what makes a test need a live Redis, same convention
    as `arq_redis`."""
    from app.services.games.realtime import get_realtime_redis

    client = get_realtime_redis(settings.REDIS_URL_TEST)
    yield client
    await client.flushdb()
    await client.aclose()


@pytest_asyncio.fixture
async def client(db):
    """The default HTTP client: real app, real routes, **no Redis**.

    `get_arq_redis` is overridden to None, which is exactly what the app does
    for real when Redis is unreachable at startup — `safe_enqueue` no-ops with
    a logged warning instead of raising (see app/main.py's lifespan, and
    test_redis_resilience.py, which proves every enqueue path survives it).

    Use this for everything. A role guard, a 404, or a payment confirmation
    should never need a message broker to test. Five tests genuinely assert a
    job was queued; those use `arq_client` instead.
    """
    async def _override_get_db():
        yield db

    async def _override_get_arq_redis():
        return None

    async def _override_get_realtime_redis():
        return None

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_arq_redis] = _override_get_arq_redis
    app.dependency_overrides[get_realtime_redis_dep] = _override_get_realtime_redis
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def arq_client(db, arq_redis):
    """`client`, but wired to a real ARQ pool — for the handful of tests that
    assert a job actually landed on the queue. Take `arq_redis` alongside it to
    inspect `arq:queue`. **Requires a running Redis**; prefer `client`."""
    async def _override_get_db():
        yield db

    async def _override_get_arq_redis():
        return arq_redis

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_arq_redis] = _override_get_arq_redis
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def realtime_client(db, realtime_redis):
    """`client`, but wired to a real live-games broadcast connection — for
    the handful of tests that assert a WS message actually got published.
    Take `realtime_redis` alongside it to subscribe and inspect what went
    out. **Requires a running Redis**; prefer `client`."""
    async def _override_get_db():
        yield db

    async def _override_get_arq_redis():
        return None

    async def _override_get_realtime_redis():
        return realtime_redis

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_arq_redis] = _override_get_arq_redis
    app.dependency_overrides[get_realtime_redis_dep] = _override_get_realtime_redis
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    app.dependency_overrides.clear()

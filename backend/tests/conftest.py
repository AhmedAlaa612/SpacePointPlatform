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
import pytest_asyncio
from arq import create_pool
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.db.session import get_db
from app.main import app
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


@pytest_asyncio.fixture(scope="session")
async def _engine():
    # Created inside a fixture (not at module import time) so it's bound to
    # the event loop pytest-asyncio actually runs tests in — an asyncpg
    # connection pool created before any loop exists breaks across tests
    # with "another operation is in progress" once a second test reuses it.
    engine = create_async_engine(settings.DATABASE_URL_TEST)
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

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_arq_redis] = _override_get_arq_redis
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

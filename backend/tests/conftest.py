"""Shared pytest fixtures.

Bootstrapped in V2 R1-3 — no test harness existed before this (the full
monorepo/CI test setup is still V2 C0-2). This is deliberately minimal: one
fixture giving a test an AsyncSession, wrapped in a transaction that's rolled
back afterward so tests never leave data behind in DATABASE_URL_TEST and never
touch DATABASE_URL (the dev database) at all.

Tests use `await db.flush()`, never `await db.commit()` — everything stays
inside the one outer transaction this fixture rolls back at teardown.
"""

import pytest_asyncio
from arq import create_pool
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.workers.settings import redis_settings

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
    Flushed after every test so queued jobs don't leak between tests."""
    yield _arq_engine
    await _arq_engine.flushdb()

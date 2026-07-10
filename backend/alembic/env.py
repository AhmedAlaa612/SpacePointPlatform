"""Alembic environment — runs migrations synchronously via psycopg2.

The app itself is async (asyncpg), but Alembic is run as a one-shot CLI /
container-entrypoint step, where a plain sync connection is simpler and, unlike
asyncpg, lets a single migration execute multi-statement SQL (needed by the
baseline revision). The async driver suffix is stripped from DATABASE_URL below.
"""

from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context

from app.core.config import settings
from app.db.base import Base
import app.models  # noqa: F401  — registers every model on Base.metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _sync_url() -> str:
    """postgresql+asyncpg://…  →  postgresql+psycopg2://…  (Alembic runs sync)."""
    url = settings.DATABASE_URL
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_sync_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_sync_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

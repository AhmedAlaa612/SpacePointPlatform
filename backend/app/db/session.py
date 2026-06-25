import ssl

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings

# Permissive SSL context — required for the Supabase connection pooler.
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,  # idle pooled connections get silently dropped (NAT/
    # Windows network-name-no-longer-available resets) — ping before reuse
    # instead of handing out a dead connection and crashing the request.
    connect_args={
        "ssl": _ssl_ctx,
        # Supabase's pooler doesn't support prepared statements — disable
        # asyncpg's statement cache so it works on both poolers.
        "statement_cache_size": 0,
    },
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

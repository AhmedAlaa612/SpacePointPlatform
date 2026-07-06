import ssl

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings


def _is_supabase_url(url: str) -> bool:
    """Supabase-hosted Postgres (direct or pooler) needs two workarounds a
    plain Postgres (e.g. the VPS instance) must NOT get."""
    return "supabase.co" in url or "supabase.com" in url or "supabase.in" in url


_connect_args: dict = {}
if _is_supabase_url(settings.DATABASE_URL):
    # Permissive SSL context — required for the Supabase connection pooler.
    _ssl_ctx = ssl.create_default_context()
    _ssl_ctx.check_hostname = False
    _ssl_ctx.verify_mode = ssl.CERT_NONE
    _connect_args = {
        "ssl": _ssl_ctx,
        # Supabase's pooler doesn't support prepared statements — disable
        # asyncpg's statement cache so it works on both poolers.
        "statement_cache_size": 0,
    }

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,  # idle pooled connections get silently dropped (NAT/
    # Windows network-name-no-longer-available resets) — ping before reuse
    # instead of handing out a dead connection and crashing the request.
    connect_args=_connect_args,
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

"""Supabase Storage wrapper — all production file I/O goes through here.

The supabase-py storage client is synchronous, so each call is offloaded to a
worker thread to avoid blocking the async event loop. Buckets are listed in
PLAN §8.1 / §10.
"""

from functools import lru_cache

import anyio
from supabase import Client, create_client

from app.core.config import settings


@lru_cache
def _client() -> Client:
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)


async def upload_file(bucket: str, path: str, data: bytes, content_type: str) -> str:
    """Upload bytes and return the (public) object URL."""

    def _do() -> str:
        client = _client()
        client.storage.from_(bucket).upload(
            path,
            data,
            {"content-type": content_type, "upsert": "true"},
        )
        return client.storage.from_(bucket).get_public_url(path)

    return await anyio.to_thread.run_sync(_do)


async def delete_file(bucket: str, path: str) -> None:
    def _do() -> None:
        _client().storage.from_(bucket).remove([path])

    await anyio.to_thread.run_sync(_do)


async def get_signed_url(bucket: str, path: str, expires_in: int = 3600) -> str:
    def _do() -> str:
        res = _client().storage.from_(bucket).create_signed_url(path, expires_in)
        return res.get("signedURL") or res.get("signed_url", "")

    return await anyio.to_thread.run_sync(_do)

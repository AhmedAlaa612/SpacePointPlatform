"""Supabase Storage backend — the pre-cutover default (STORAGE_BACKEND=supabase).

The supabase-py storage client is synchronous, so each call is offloaded to a
worker thread to avoid blocking the async event loop. Buckets are listed in
PLAN §8.1 / §10.

Do NOT import this module from routers — go through app.services.storage,
which dispatches on settings.STORAGE_BACKEND (GO_LIVE §3.A3).
"""

from functools import lru_cache

import anyio
from supabase import Client, create_client

from app.core.config import settings

# Only these buckets are created `public: true` (PLAN §10). get_public_url()
# returns a URL that looks valid but 400s at fetch time on a private bucket,
# so private buckets need a signed URL instead — long-lived since these are
# meant to be stored once and referenced indefinitely (contracts, documents),
# not the short-lived signed URLs used for on-demand video streaming.
_PUBLIC_BUCKETS: set[str] = set()  # library-resources moved to private; signed URLs generated at query time
_LONG_LIVED_SIGNED_URL_SECONDS = 10 * 365 * 24 * 3600  # ~10 years


@lru_cache
def _client() -> Client:
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)


async def upload_file(bucket: str, path: str, data: bytes, content_type: str) -> str:
    """Upload bytes and return a URL that actually resolves: a public URL for
    public buckets, a long-lived signed URL for private ones."""

    def _do() -> str:
        client = _client()
        client.storage.from_(bucket).upload(
            path,
            data,
            {"content-type": content_type, "upsert": "true"},
        )
        if bucket in _PUBLIC_BUCKETS:
            return client.storage.from_(bucket).get_public_url(path)
        res = client.storage.from_(bucket).create_signed_url(path, _LONG_LIVED_SIGNED_URL_SECONDS)
        return res.get("signedURL") or res.get("signed_url", "")

    return await anyio.to_thread.run_sync(_do)


async def upload_to_path(bucket: str, path: str, data: bytes, content_type: str) -> str:
    """Upload bytes and return only the storage path. Caller is responsible for
    generating signed URLs at query time via get_signed_url()."""

    def _do() -> None:
        _client().storage.from_(bucket).upload(
            path,
            data,
            {"content-type": content_type, "upsert": "true"},
        )

    await anyio.to_thread.run_sync(_do)
    return path


async def delete_file(bucket: str, path: str) -> None:
    def _do() -> None:
        _client().storage.from_(bucket).remove([path])

    await anyio.to_thread.run_sync(_do)


async def get_signed_url(bucket: str, path: str, expires_in: int = 3600) -> str:
    def _do() -> str:
        res = _client().storage.from_(bucket).create_signed_url(path, expires_in)
        return res.get("signedURL") or res.get("signed_url", "")

    return await anyio.to_thread.run_sync(_do)


async def download_file(bucket: str, path: str) -> bytes:
    def _do() -> bytes:
        return _client().storage.from_(bucket).download(path)

    return await anyio.to_thread.run_sync(_do)


async def list_files(bucket: str, path: str = "") -> list[dict]:
    """List all files/folders inside a Supabase storage bucket at the given path."""
    def _do() -> list[dict]:
        return _client().storage.from_(bucket).list(path)

    return await anyio.to_thread.run_sync(_do)

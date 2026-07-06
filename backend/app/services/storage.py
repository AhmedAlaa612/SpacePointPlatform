"""Storage facade — ALL production file I/O goes through here.

The actual backend is selected by settings.STORAGE_BACKEND (GO_LIVE §3.A3):
- "supabase" (default): Supabase Storage buckets      → storage_supabase.py
- "local":  STORAGE_ROOT/{bucket}/{path} on disk,
            Fernet-encrypted at rest, HMAC-signed
            /files/{bucket}/{path} URLs                → storage_local.py

Both backends expose the identical async interface:
    upload_file(bucket, path, data, content_type)  -> long-lived signed URL
    upload_to_path(bucket, path, data, content_type) -> path (str)
    delete_file(bucket, path)                      -> None
    get_signed_url(bucket, path, expires_in=3600)  -> signed URL
    download_file(bucket, path)                    -> bytes (decrypted)
    list_files(bucket, path="")                    -> list[dict] (supabase shape)

Since A2 (path-based storage), DB rows store {bucket, file_path} as the source
of truth and the legacy *_url columns only as a fallback; readers turn them
into fresh URLs at query time via resolve_url() below. Routers must NEVER
import storage_supabase/storage_local directly (the /files route is the one
exception — it always serves from local disk).
"""

from app.core.config import settings


def _impl():
    if settings.STORAGE_BACKEND == "local":
        from app.services import storage_local as impl
    else:
        from app.services import storage_supabase as impl
    return impl


async def upload_file(bucket: str, path: str, data: bytes, content_type: str) -> str:
    """Upload bytes and return a long-lived URL that actually resolves.
    Prefer storing the (bucket, path) pair you passed in — regenerate URLs at
    query time with get_signed_url()/resolve_url()."""
    return await _impl().upload_file(bucket, path, data, content_type)


async def upload_to_path(bucket: str, path: str, data: bytes, content_type: str) -> str:
    """Upload bytes and return only the storage path. Caller is responsible for
    generating signed URLs at query time via get_signed_url()."""
    return await _impl().upload_to_path(bucket, path, data, content_type)


async def delete_file(bucket: str, path: str) -> None:
    await _impl().delete_file(bucket, path)


async def get_signed_url(bucket: str, path: str, expires_in: int = 3600) -> str:
    return await _impl().get_signed_url(bucket, path, expires_in)


async def download_file(bucket: str, path: str) -> bytes:
    return await _impl().download_file(bucket, path)


async def list_files(bucket: str, path: str = "") -> list[dict]:
    """List files/folders at the given path, in the supabase-py dict shape
    (folders have metadata=None; files carry size/mimetype/lastModified)."""
    return await _impl().list_files(bucket, path)


async def resolve_url(
    bucket: str | None,
    path: str | None,
    fallback_url: str | None = None,
    expires_in: int = 3600,
) -> str | None:
    """Query-time URL resolution for A2 path-based rows.

    Prefers generating a fresh signed URL from (bucket, path); falls back to
    the stored legacy URL column (pre-A2 rows, or if signing fails). Returns
    None only when there is nothing on file at all.
    """
    if bucket and path:
        try:
            return await get_signed_url(bucket, path, expires_in)
        except Exception:  # noqa: BLE001 — fall back to the stored URL
            pass
    return fallback_url

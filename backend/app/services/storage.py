"""Storage facade — ALL production file I/O goes through here.

The actual backend is selected by settings.STORAGE_BACKEND (GO_LIVE §3.A3):
- "supabase" (default): Supabase Storage buckets      → storage_supabase.py
- "local":  STORAGE_ROOT/{bucket}/{path} on disk,
            Fernet-encrypted at rest, HMAC-signed
            /files/{bucket}/{path} URLs                → storage_local.py
- "r2":     Cloudflare R2, one bucket with the app's
            bucket name as a key prefix, presigned
            S3 URLs                                    → storage_r2.py

Both backends expose the identical async interface:
    upload_file(bucket, path, data, content_type)  -> long-lived signed URL
    upload_to_path(bucket, path, data, content_type) -> path (str)
    delete_file(bucket, path)                      -> None
    get_signed_url(bucket, path, expires_in=3600)  -> signed URL
    download_file(bucket, path)                    -> bytes (decrypted)
    list_files(bucket, path="")                    -> list[dict] (supabase shape)

Every function takes an optional `backend=` override. It exists for one
reason: video bytes need to live somewhere other than everything else. 400
concurrent students pulling HLS segments through the API is ~1 Gbps and a
Fernet decrypt per segment on a 4-vCPU box, so video moves to R2 — while
payment letters, signed contracts, certificates and every document bucket stay
exactly where they are, on a backend nobody has to re-verify under deadline.
Callers that pass nothing are completely unaffected; the video path is the only
one that passes it, reading it from `videos.storage_backend` per row.

Since A2 (path-based storage), DB rows store {bucket, file_path} as the source
of truth and the legacy *_url columns only as a fallback; readers turn them
into fresh URLs at query time via resolve_url() below. Routers must NEVER
import storage_supabase/storage_local directly (the /files route is the one
exception — it always serves from local disk).
"""

from app.core.config import settings


def default_video_backend() -> str | None:
    """The backend a NEWLY uploaded video should be stored on, or None for the
    deployment default.

    Deliberately not "the backend video reads from" — that is per-video state
    and lives on `videos.storage_backend`. This setting only supplies the
    value stamped onto new rows, which is what makes turning it on safe: it
    cannot affect a single video that already exists."""
    return settings.VIDEO_STORAGE_BACKEND or None


def _impl(backend: str | None = None):
    name = backend or settings.STORAGE_BACKEND
    if name == "local":
        from app.services import storage_local as impl
    elif name == "r2":
        from app.services import storage_r2 as impl
    else:
        from app.services import storage_supabase as impl
    return impl


async def upload_file(
    bucket: str, path: str, data: bytes, content_type: str, *, backend: str | None = None,
) -> str:
    """Upload bytes and return a long-lived URL that actually resolves.
    Prefer storing the (bucket, path) pair you passed in — regenerate URLs at
    query time with get_signed_url()/resolve_url()."""
    return await _impl(backend).upload_file(bucket, path, data, content_type)


async def upload_to_path(
    bucket: str, path: str, data: bytes, content_type: str, *, backend: str | None = None,
) -> str:
    """Upload bytes and return only the storage path. Caller is responsible for
    generating signed URLs at query time via get_signed_url()."""
    return await _impl(backend).upload_to_path(bucket, path, data, content_type)


async def delete_file(bucket: str, path: str, *, backend: str | None = None) -> None:
    await _impl(backend).delete_file(bucket, path)


async def get_signed_url(
    bucket: str, path: str, expires_in: int = 3600, *, backend: str | None = None,
) -> str:
    return await _impl(backend).get_signed_url(bucket, path, expires_in)


async def download_file(bucket: str, path: str, *, backend: str | None = None) -> bytes:
    return await _impl(backend).download_file(bucket, path)


async def list_files(bucket: str, path: str = "", *, backend: str | None = None) -> list[dict]:
    """List files/folders at the given path, in the supabase-py dict shape
    (folders have metadata=None; files carry size/mimetype/lastModified)."""
    return await _impl(backend).list_files(bucket, path)


async def resolve_url(
    bucket: str | None,
    path: str | None,
    fallback_url: str | None = None,
    expires_in: int = 3600,
    *,
    backend: str | None = None,
) -> str | None:
    """Query-time URL resolution for A2 path-based rows.

    Prefers generating a fresh signed URL from (bucket, path); falls back to
    the stored legacy URL column (pre-A2 rows, or if signing fails). Returns
    None only when there is nothing on file at all.
    """
    if bucket and path:
        try:
            return await get_signed_url(bucket, path, expires_in, backend=backend)
        except Exception:  # noqa: BLE001 — fall back to the stored URL
            pass
    return fallback_url

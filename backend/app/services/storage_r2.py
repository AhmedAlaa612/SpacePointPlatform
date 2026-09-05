"""Cloudflare R2 storage backend (STORAGE_BACKEND / VIDEO_STORAGE_BACKEND = "r2").

Same six-function interface as storage_local.py / storage_supabase.py — go
through app.services.storage, never import this directly from a router.

R2 is S3-compatible, so boto3 works against it unmodified. Three details differ
from a real AWS S3 and all three are load-bearing:

- `region_name` is always the literal string "auto". R2 has no regions in the
  S3 sense (a bucket's physical location is a creation-time hint, not part of
  the request), but SigV4 still requires *some* region in the signature, and
  the signature only verifies against "auto".
- `signature_version="s3v4"` and `addressing_style="path"` must be pinned.
  boto3's defaults drift toward virtual-host addressing, which R2's endpoint
  does not serve.
- One R2 bucket holds everything. The app's own "bucket" argument (lms-hls,
  lms-video-sources, ...) becomes a *key prefix* inside settings.R2_BUCKET, so
  the six-function interface stays identical while the account keeps a single
  bucket to configure, meter and CORS.

**No Fernet here, deliberately.** storage_local.py encrypts every blob at rest
because a copy of that VPS disk would otherwise be a copy of the content. R2's
protection model is different and does not need it: objects are encrypted at
rest by Cloudflare, the bucket is private, and access is granted per-object by
a time-limited presigned URL. Layering Fernet on top would also defeat the
entire point of moving video here — a Fernet blob cannot be range-requested or
played by a browser, so every byte would have to be proxied back through the
API and decrypted, which is exactly the load this migration exists to remove.
For HLS specifically the segments are *already* AES-128 encrypted by the
transcode step, and the decryption key is served by the API behind the same
enrollment check as before (see routers/lms/video.py) — so a leaked or expired
segment URL yields ciphertext, not content.
"""

import mimetypes
from datetime import timezone
from functools import lru_cache

import anyio
import anyio.to_thread  # noqa: F401 — bind the submodule; `import anyio` alone does not

from app.core.config import settings

# Mirrors the other backends: upload_file() returns a URL meant to be stored
# once and referenced indefinitely. AWS SigV4 caps a presigned URL's lifetime
# at 7 days, so unlike storage_local's ~10 years this genuinely cannot be
# "long-lived" — callers that need durable access must re-sign at query time
# via get_signed_url()/resolve_url(), which is what every A2 path-based reader
# already does.
_MAX_PRESIGN_SECONDS = 7 * 24 * 3600


def _endpoint() -> str:
    if settings.R2_ENDPOINT_URL:
        return settings.R2_ENDPOINT_URL.rstrip("/")
    if not settings.R2_ACCOUNT_ID:
        raise RuntimeError(
            "R2_ACCOUNT_ID (or R2_ENDPOINT_URL) must be set when a storage backend resolves to 'r2'"
        )
    return f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"


@lru_cache
def _client():
    import boto3
    from botocore.config import Config

    if not (settings.R2_ACCESS_KEY_ID and settings.R2_SECRET_ACCESS_KEY and settings.R2_BUCKET):
        raise RuntimeError(
            "R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY and R2_BUCKET must all be set "
            "when a storage backend resolves to 'r2'"
        )
    return boto3.client(
        "s3",
        endpoint_url=_endpoint(),
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        region_name="auto",
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            retries={"max_attempts": 3, "mode": "standard"},
            # botocore defaults this to 10 — below anyio's 40 worker threads,
            # so under load most R2 calls hit a full pool, opened a throwaway
            # connection, paid a full TLS handshake, and discarded it on
            # release. urllib3 does that silently (block=False), so it never
            # surfaced as an error, only as every "warm" download costing what
            # a cold one costs. See settings.R2_MAX_POOL_CONNECTIONS.
            max_pool_connections=settings.R2_MAX_POOL_CONNECTIONS,
        ),
    )


def _key(bucket: str, path: str) -> str:
    """The app's (bucket, path) pair as one R2 object key.

    Guards the same traversal cases storage_local._safe_path does. There is no
    filesystem here so `..` is not dangerous in the same way, but a key
    containing it would still be a different object than the caller meant, and
    silently reading/writing the wrong one is worse than a 400."""
    if not bucket or "/" in bucket or "\\" in bucket or bucket in (".", ".."):
        raise ValueError(f"Invalid bucket name: {bucket!r}")
    if not path:
        raise ValueError("Empty storage path")
    if path.startswith("/") or ".." in path.split("/"):
        raise ValueError(f"Storage path escapes bucket: {path!r}")
    return f"{bucket}/{path}"


async def upload_to_path(bucket: str, path: str, data: bytes, content_type: str) -> str:
    """Upload bytes and return only the storage path. Caller generates signed
    URLs at query time via get_signed_url().

    Unlike storage_local, content_type IS stored — R2 serves it straight back
    to the browser as the response's Content-Type, and hls.js/`<video>` are
    served directly by R2 with no app in the middle to re-infer it."""

    def _do() -> None:
        _client().put_object(
            Bucket=settings.R2_BUCKET,
            Key=_key(bucket, path),
            Body=bytes(data),
            ContentType=content_type or mimetypes.guess_type(path)[0] or "application/octet-stream",
        )

    await anyio.to_thread.run_sync(_do)
    return path


async def upload_file(bucket: str, path: str, data: bytes, content_type: str) -> str:
    """Upload bytes, then return a signed URL (same contract as the other
    backends' upload_file). Capped at R2's 7-day presign maximum — see
    _MAX_PRESIGN_SECONDS."""
    await upload_to_path(bucket, path, data, content_type)
    return await get_signed_url(bucket, path, _MAX_PRESIGN_SECONDS)


async def get_signed_url(bucket: str, path: str, expires_in: int = 3600) -> str:
    """A presigned GET URL against the R2 S3 endpoint.

    Purely local HMAC computation — no network call, and no R2 operation is
    billed for producing one. That is what makes it cheap to sign every segment
    line when rewriting an HLS playlist per request.
    """
    expires_in = min(int(expires_in), _MAX_PRESIGN_SECONDS)

    def _do() -> str:
        return _client().generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.R2_BUCKET, "Key": _key(bucket, path)},
            ExpiresIn=expires_in,
        )

    return await anyio.to_thread.run_sync(_do)


async def get_signed_urls(bucket: str, paths: list[str], expires_in: int = 3600) -> list[str]:
    """Presign many keys in ONE thread hop.

    Presigning is pure local HMAC (see get_signed_url), so the work itself is
    microseconds — but `await anyio.to_thread.run_sync` per URL is not. Each
    one costs a worker-thread-limiter acquisition plus a full trip around the
    event loop, and an HLS playlist rewrite signs one URL per segment: ~5 for
    the 50-second clip the load tests used, ~180 for a half-hour lecture at
    10s segments. Under 400 concurrent starts the loop is deep enough that
    those round trips, not the HMAC, are the cost — and they were being paid
    sequentially inside the request.

    Signing the whole playlist in a single hop makes that per-request cost
    O(1) trips instead of O(segments).
    """
    if not paths:
        return []
    expires_in = min(int(expires_in), _MAX_PRESIGN_SECONDS)

    def _do() -> list[str]:
        client = _client()
        bucket_name = settings.R2_BUCKET
        return [
            client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket_name, "Key": _key(bucket, path)},
                ExpiresIn=expires_in,
            )
            for path in paths
        ]

    return await anyio.to_thread.run_sync(_do)


async def download_file(bucket: str, path: str) -> bytes:
    """Read an object's bytes. Raises FileNotFoundError when it doesn't exist,
    matching storage_local's contract so callers need no backend-specific
    except clause."""

    def _do() -> bytes:
        client = _client()
        try:
            return client.get_object(Bucket=settings.R2_BUCKET, Key=_key(bucket, path))["Body"].read()
        except client.exceptions.NoSuchKey as exc:
            raise FileNotFoundError(f"{bucket}/{path}") from exc

    return await anyio.to_thread.run_sync(_do)


async def delete_file(bucket: str, path: str) -> None:
    def _do() -> None:
        # S3 DELETE is idempotent — deleting a missing key succeeds, which
        # matches storage_local's unlink(missing_ok=True).
        _client().delete_object(Bucket=settings.R2_BUCKET, Key=_key(bucket, path))

    await anyio.to_thread.run_sync(_do)


async def list_files(bucket: str, path: str = "") -> list[dict]:
    """List immediate children of {bucket}/{path}, in the supabase-py dict
    shape every caller already expects (folders have metadata=None; files carry
    size/mimetype/lastModified).

    Object stores have no directories, so "immediate children" is synthesised
    with Delimiter="/": CommonPrefixes become the folder entries, Contents the
    file entries. Paginated because a single video's HLS output is already ~35
    objects and ListObjectsV2 caps at 1000 per response.
    """
    prefix = f"{bucket}/" if not path else f"{_key(bucket, path).rstrip('/')}/"

    def _do() -> list[dict]:
        out: list[dict] = []
        paginator = _client().get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=settings.R2_BUCKET, Prefix=prefix, Delimiter="/"):
            for folder in page.get("CommonPrefixes", []):
                out.append({
                    "name": folder["Prefix"][len(prefix):].rstrip("/"),
                    "id": None,
                    "updated_at": None,
                    "created_at": None,
                    "last_accessed_at": None,
                    "metadata": None,
                })
            for obj in page.get("Contents", []):
                name = obj["Key"][len(prefix):]
                if not name:  # the prefix "directory marker" itself, if one exists
                    continue
                ts = obj["LastModified"].astimezone(timezone.utc).isoformat()
                out.append({
                    "name": name,
                    "id": name,
                    "updated_at": ts,
                    "created_at": ts,
                    "last_accessed_at": ts,
                    "metadata": {
                        "size": obj["Size"],
                        "mimetype": mimetypes.guess_type(name)[0] or "application/octet-stream",
                        "lastModified": ts,
                    },
                })
        return sorted(out, key=lambda e: e["name"])

    return await anyio.to_thread.run_sync(_do)


__all__ = [
    "upload_file",
    "upload_to_path",
    "delete_file",
    "get_signed_url",
    "get_signed_urls",
    "download_file",
    "list_files",
]

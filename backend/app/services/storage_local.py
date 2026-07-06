"""Local filesystem storage backend with encryption at rest (STORAGE_BACKEND=local).

GO_LIVE §3.A3 / boss requirement #4:
- Files live at STORAGE_ROOT/{bucket}/{path}.
- EVERY file is Fernet-encrypted on write with STORAGE_ENCRYPTION_KEY (all
  buckets, uniformly — no "sensitive-only" carve-outs) and decrypted on read.
  A copy of the disk alone exposes only ciphertext; a copy of the DB alone
  exposes only bucket/path strings.
- "Signed URL" = app-served  /files/{bucket}/{path}?exp=<unix>&sig=<hex>
  where sig = HMAC-SHA256(SECRET_KEY, f"{bucket}|{path}|{exp}").
  The FastAPI route (app/routers/files.py) validates sig+expiry, decrypts and
  streams with a mimetypes-inferred content type.

Do NOT import this module from routers (the /files route is the one exception,
since it always serves from local disk) — go through app.services.storage,
which dispatches on settings.STORAGE_BACKEND.
"""

import hashlib
import hmac
import mimetypes
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

import anyio

from app.core.config import settings

# Mirrors the Supabase backend: upload_file() returns a URL meant to be stored
# once and referenced indefinitely, so it gets a very generous expiry. Signed
# URLs generated at query time (get_signed_url) default to 1 hour.
_LONG_LIVED_SIGNED_URL_SECONDS = 10 * 365 * 24 * 3600  # ~10 years


@lru_cache
def _fernet():
    from cryptography.fernet import Fernet

    key = settings.STORAGE_ENCRYPTION_KEY
    if not key:
        raise RuntimeError(
            "STORAGE_ENCRYPTION_KEY must be set when STORAGE_BACKEND=local "
            '(generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")'
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def _root() -> Path:
    return Path(settings.STORAGE_ROOT).resolve()


def _safe_path(bucket: str, path: str) -> Path:
    """Resolve STORAGE_ROOT/{bucket}/{path}, refusing anything that escapes the
    root (path traversal via ../, absolute paths, drive letters...)."""
    if not bucket or "/" in bucket or "\\" in bucket or bucket in (".", ".."):
        raise ValueError(f"Invalid bucket name: {bucket!r}")
    if not path:
        raise ValueError("Empty storage path")
    root = _root()
    full = (root / bucket / path).resolve()
    if not full.is_relative_to(root / bucket):
        raise ValueError(f"Storage path escapes bucket: {path!r}")
    return full


def _sign(bucket: str, path: str, exp: int) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode(),
        f"{bucket}|{path}|{exp}".encode(),
        hashlib.sha256,
    ).hexdigest()


def verify_signature(bucket: str, path: str, exp: int, sig: str) -> bool:
    """True iff sig matches HMAC-SHA256(SECRET_KEY, bucket|path|exp) and exp is
    still in the future. Used by the GET /files route."""
    if exp < int(time.time()):
        return False
    return hmac.compare_digest(_sign(bucket, path, exp), sig)


async def get_signed_url(bucket: str, path: str, expires_in: int = 3600) -> str:
    exp = int(time.time()) + expires_in
    sig = _sign(bucket, path, exp)
    base = settings.BASE_URL.rstrip("/")
    return f"{base}/files/{quote(bucket)}/{quote(path)}?exp={exp}&sig={sig}"


async def upload_to_path(bucket: str, path: str, data: bytes, content_type: str) -> str:
    """Encrypt and write bytes; return only the storage path. Caller generates
    signed URLs at query time via get_signed_url(). content_type is accepted
    for interface parity but not stored — it is re-inferred from the file
    extension via mimetypes at serve time."""

    def _do() -> None:
        token = _fernet().encrypt(bytes(data))
        full = _safe_path(bucket, path)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(token)

    await anyio.to_thread.run_sync(_do)
    return path


async def upload_file(bucket: str, path: str, data: bytes, content_type: str) -> str:
    """Encrypt and write bytes, then return a long-lived signed /files URL
    (same contract as the Supabase backend's upload_file)."""
    await upload_to_path(bucket, path, data, content_type)
    return await get_signed_url(bucket, path, _LONG_LIVED_SIGNED_URL_SECONDS)


async def delete_file(bucket: str, path: str) -> None:
    def _do() -> None:
        _safe_path(bucket, path).unlink(missing_ok=True)

    await anyio.to_thread.run_sync(_do)


async def download_file(bucket: str, path: str) -> bytes:
    """Read and decrypt. Raises FileNotFoundError if the blob doesn't exist."""

    def _do() -> bytes:
        return _fernet().decrypt(_safe_path(bucket, path).read_bytes())

    return await anyio.to_thread.run_sync(_do)


async def list_files(bucket: str, path: str = "") -> list[dict]:
    """List immediate children of STORAGE_ROOT/{bucket}/{path}, in the same dict
    shape the supabase-py storage client returns (the admin Storage Browser and
    routers/documents.py's recursive lister depend on it):
    - folders: metadata is None (that's how callers detect a directory)
    - files:   metadata carries size / mimetype / lastModified
    Note: size is the on-disk (encrypted) size — plaintext size would require
    decrypting every blob just to list it.
    """

    def _do() -> list[dict]:
        base = _safe_path(bucket, path) if path else _root() / bucket
        if not base.is_dir():
            return []
        out: list[dict] = []
        for entry in sorted(base.iterdir(), key=lambda e: e.name):
            if entry.is_dir():
                out.append({
                    "name": entry.name,
                    "id": None,
                    "updated_at": None,
                    "created_at": None,
                    "last_accessed_at": None,
                    "metadata": None,
                })
            else:
                st = entry.stat()
                ts = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()
                out.append({
                    "name": entry.name,
                    "id": entry.name,
                    "updated_at": ts,
                    "created_at": ts,
                    "last_accessed_at": ts,
                    "metadata": {
                        "size": st.st_size,
                        "mimetype": mimetypes.guess_type(entry.name)[0] or "application/octet-stream",
                        "lastModified": ts,
                    },
                })
        return out

    return await anyio.to_thread.run_sync(_do)

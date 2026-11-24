"""Storage facade for LMS Books — routes to dedicated R2 bucket when configured,
and falls back cleanly to the deployment's STORAGE_BACKEND (local/supabase) in dev/tests.
"""

from __future__ import annotations

import posixpath

from app.core.config import settings
from app.services import storage, storage_r2

BOOK_BUNDLE_PREFIX = "lms-books"
BOOK_COVER_PREFIX = "lms-book-covers"


def resolve_books_backend(override: str | None = None) -> str:
    """Return the active storage backend for new or stored book assets."""
    return override or settings.BOOKS_STORAGE_BACKEND or settings.STORAGE_BACKEND


def _r2_books_bucket() -> str:
    return settings.R2_BOOKS_BUCKET or settings.R2_BUCKET


def sanitize_relative_path(path: str) -> str:
    """Validate and normalize a bundle-relative path (reject traversal & absolute paths)."""
    raw = (path or "").strip()
    if not raw or "\x00" in raw or "\\" in raw or raw.startswith("/"):
        raise ValueError(f"Invalid asset path: {path!r}")
    parts = [p for p in raw.split("/") if p]
    if not parts or any(p in (".", "..") for p in parts):
        raise ValueError(f"Asset path escapes root: {path!r}")
    norm = posixpath.normpath("/".join(parts))
    if norm in ("", ".", "..") or norm.startswith("/") or norm.startswith("../"):
        raise ValueError(f"Invalid normalized asset path: {path!r}")
    return norm


def _r2_impl_if_active(backend: str | None = None):
    resolved = resolve_books_backend(backend)
    impl = storage._impl(resolved)
    return impl if impl is storage_r2 else None


async def upload_book_file(
    prefix: str,
    path: str,
    data: bytes,
    content_type: str,
    *,
    backend: str | None = None,
) -> str:
    """Upload a book cover or bundle file to R2 (or fallback storage) and return its path."""
    clean = sanitize_relative_path(path)
    resolved = resolve_books_backend(backend)
    if _r2_impl_if_active(resolved) is not None:
        return await storage_r2.upload_to_path(
            prefix, clean, data, content_type, r2_bucket=_r2_books_bucket()
        )
    return await storage.upload_to_path(prefix, clean, data, content_type, backend=resolved)


async def download_book_file(
    prefix: str,
    path: str,
    *,
    backend: str | None = None,
) -> bytes:
    """Download a book bundle file or cover bytes."""
    clean = sanitize_relative_path(path)
    resolved = resolve_books_backend(backend)
    if _r2_impl_if_active(resolved) is not None:
        return await storage_r2.download_file(prefix, clean, r2_bucket=_r2_books_bucket())
    return await storage.download_file(prefix, clean, backend=resolved)


async def resolve_book_cover_url(
    bucket: str | None,
    path: str | None,
    *,
    expires_in: int = 3600,
    backend: str | None = None,
) -> str | None:
    """Generate a signed URL for a book cover image (returns None when unset)."""
    if not bucket or not path:
        return None
    resolved = resolve_books_backend(backend)
    try:
        if _r2_impl_if_active(resolved) is not None:
            return await storage_r2.get_signed_url(
                bucket, path, expires_in=expires_in, r2_bucket=_r2_books_bucket()
            )
        return await storage.get_signed_url(bucket, path, expires_in=expires_in, backend=resolved)
    except Exception:
        return None


async def delete_book_file(
    prefix: str,
    path: str,
    *,
    backend: str | None = None,
) -> None:
    """Delete a book asset if it exists."""
    clean = sanitize_relative_path(path)
    resolved = resolve_books_backend(backend)
    if _r2_impl_if_active(resolved) is not None:
        await storage_r2.delete_file(prefix, clean, r2_bucket=_r2_books_bucket())
        return
    await storage.delete_file(prefix, clean, backend=resolved)

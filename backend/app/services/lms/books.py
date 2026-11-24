"""LMS Interactive Books service — enrollments, R2 bundle ingestion, HTML runtime injection,
progress syncing, and instructor/ops exercise analytics.
"""

from __future__ import annotations

import base64
import csv
import html
from html.parser import HTMLParser
import io
import json
import mimetypes
import re
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lms.book import (
    LmsBook,
    LmsBookEnrollment,
    LmsBookExerciseResponse,
    LmsBookProgress,
)
from app.models.lms.program import LmsProgramAssignment
from app.models.user import User
from app.schemas.lms_books import BookExerciseIn, BookProgressSyncIn
from app.services.lms import books_storage
from app.services.lms.books_storage import (
    BOOK_BUNDLE_PREFIX,
    resolve_books_backend,
    sanitize_relative_path,
)

STATIC_BOOKS_DIR = Path(__file__).resolve().parents[2] / "static" / "books"

MAX_ZIP_BYTES = 150 * 1024 * 1024
MAX_ZIP_FILES = 1000
_STAFF_TEACHER_ROLES = {"admin", "operations", "facilitator", "lms_author", "instructor"}

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify_book(title: str) -> str:
    base = _SLUG_RE.sub("-", (title or "").strip().lower()).strip("-")
    return base[:96] or f"book-{uuid.uuid4().hex[:8]}"


def can_user_teacher_mode(user: User) -> bool:
    roles = set(user.role_values or [])
    return bool(roles & _STAFF_TEACHER_ROLES)


def book_enrollment_is_active() -> tuple:
    return (
        LmsBookEnrollment.status == "active",
        or_(LmsBookEnrollment.expires_at.is_(None), LmsBookEnrollment.expires_at > func.now()),
    )


def _resolve_expires_at(book: LmsBook) -> datetime | None:
    if book.access_days is None:
        return None
    return datetime.now(timezone.utc) + timedelta(days=book.access_days)


async def enroll_book(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    book_id: uuid.UUID,
    source: str = "self",
    granted_by: uuid.UUID | None = None,
    purchase_id: uuid.UUID | None = None,
    expires_at: datetime | None = None,
) -> LmsBookEnrollment:
    """Grant (or reactivate) a student's access to an LMS Book (idempotent)."""
    book = await db.get(LmsBook, book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")

    book_expiry = _resolve_expires_at(book)
    if expires_at is not None:
        effective_expiry = min(book_expiry, expires_at) if book_expiry is not None else expires_at
    else:
        effective_expiry = book_expiry

    existing = (
        await db.execute(
            select(LmsBookEnrollment).where(
                LmsBookEnrollment.user_id == user_id,
                LmsBookEnrollment.book_id == book_id,
            )
        )
    ).scalars().first()

    now = datetime.now(timezone.utc)
    if existing is not None:
        expired = existing.expires_at is not None and existing.expires_at <= now
        if existing.status != "active" or expired:
            existing.status = "active"
            existing.expires_at = effective_expiry
            if purchase_id is not None:
                existing.purchase_id = purchase_id
            if granted_by is not None:
                existing.granted_by = granted_by
            await db.flush()
        return existing

    row = LmsBookEnrollment(
        id=uuid.uuid4(),
        user_id=user_id,
        book_id=book_id,
        source=source,
        status="active",
        granted_by=granted_by,
        purchase_id=purchase_id,
        expires_at=effective_expiry,
        created_at=now,
    )
    db.add(row)
    await db.flush()
    return row


async def has_book_access(db: AsyncSession, *, user: User, book: LmsBook) -> bool:
    """Staff/instructors can always preview; learners need an active enrollment."""
    if can_user_teacher_mode(user):
        return True
    if not book.is_published:
        return False
    row = await db.scalar(
        select(LmsBookEnrollment.id).where(
            LmsBookEnrollment.user_id == user.id,
            LmsBookEnrollment.book_id == book.id,
            *book_enrollment_is_active(),
        )
    )
    return row is not None


async def unpack_and_upload_book_zip(
    db: AsyncSession,
    *,
    book: LmsBook,
    zip_bytes: bytes,
) -> dict[str, Any]:
    """Validate, unpack, and upload a zipped interactive HTML book bundle into R2/storage."""
    if not zip_bytes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Uploaded archive is empty")

    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid .zip archive")

    entries: list[tuple[zipfile.ZipInfo, str]] = []
    total_size = 0
    for info in zf.infolist():
        if info.is_dir():
            continue
        # Reject symlinks
        mode = (info.external_attr >> 16) & 0o170000
        if mode == 0o120000:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Archive cannot contain symbolic links")
        name = info.filename.replace("\\", "/")
        if name.startswith("__MACOSX/") or name.endswith("/.DS_Store") or name == ".DS_Store":
            continue
        try:
            clean = sanitize_relative_path(name)
        except ValueError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Unsafe file path in archive: {info.filename}")
        total_size += info.file_size
        if total_size > MAX_ZIP_BYTES:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Uncompressed book exceeds 150 MB limit")
        entries.append((info, clean))
        if len(entries) > MAX_ZIP_FILES:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Archive exceeds 1000 file limit")

    if not entries:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Archive contains no files")

    # Strip single root directory if the boss zipped a folder (e.g. "My Book/index.html" -> "index.html")
    first_segments = {p.split("/", 1)[0] for _, p in entries}
    all_nested = all("/" in p for _, p in entries)
    if len(first_segments) == 1 and all_nested:
        entries = [(info, p.split("/", 1)[1]) for info, p in entries]

    paths = {p for _, p in entries}
    manifest_data: dict[str, Any] = {}
    if "book.json" in paths:
        try:
            manifest_info = next(info for info, p in entries if p == "book.json")
            manifest_data = json.loads(zf.read(manifest_info).decode("utf-8"))
        except Exception as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Invalid book.json manifest: {exc}")

    entry_file = sanitize_relative_path(str(manifest_data.get("entry") or book.bundle_entry or "index.html"))
    if entry_file not in paths:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Bundle archive must include {entry_file} at its root",
        )

    next_version = int(book.bundle_version or 0) + 1
    backend = resolve_books_backend()

    for info, rel_path in entries:
        data = zf.read(info)
        ctype = mimetypes.guess_type(rel_path)[0] or "application/octet-stream"
        if rel_path.endswith(".html"):
            ctype = "text/html; charset=utf-8"
        elif rel_path.endswith(".js"):
            ctype = "application/javascript; charset=utf-8"
        elif rel_path.endswith(".css"):
            ctype = "text/css; charset=utf-8"
        await books_storage.upload_book_file(
            BOOK_BUNDLE_PREFIX,
            f"{book.id}/v{next_version}/{rel_path}",
            data,
            ctype,
            backend=backend,
        )

    book.bundle_version = next_version
    book.bundle_entry = entry_file
    book.bundle_storage_backend = backend
    book.bundle_size_bytes = total_size

    if isinstance(manifest_data.get("outline"), list):
        book.outline = manifest_data["outline"]
    if isinstance(manifest_data.get("profiles"), list):
        book.profiles = manifest_data["profiles"]
    if isinstance(manifest_data.get("default_profile"), str) and manifest_data["default_profile"].strip():
        book.default_profile = manifest_data["default_profile"].strip()[:32]
    if isinstance(manifest_data.get("languages"), list) and manifest_data["languages"]:
        book.languages = [str(x).lower()[:8] for x in manifest_data["languages"]]
    if not book.title_ar and isinstance(manifest_data.get("title_ar"), str):
        book.title_ar = manifest_data["title_ar"][:200]

    book.updated_at = datetime.now(timezone.utc)
    await db.flush()

    return {
        "book_id": book.id,
        "bundle_version": next_version,
        "bundle_entry": entry_file,
        "bundle_storage_backend": backend,
        "bundle_size_bytes": total_size,
        "files_uploaded": len(entries),
        "chapters_detected": len(book.outline or []),
        "profiles_detected": len(book.profiles or []),
    }


def inject_runtime_into_html(
    html_bytes: bytes,
    *,
    book_id: str,
    user_id: str,
    version: int,
    can_teacher: bool,
    initial_state: dict[str, Any] | None = None,
    visited_spreads: list[str] | None = None,
    start_spread: str | None = None,
    start_chapter: str | None = None,
    start_profile: str | None = None,
    start_theme: str | None = None,
    start_lang: str | None = None,
) -> bytes:
    """Inject SpacePoint Reader CSS, config meta tag, and LMS Bridge JS into an HTML entry document."""
    text = html_bytes.decode("utf-8", errors="replace")

    cfg_payload = {
        "bookId": book_id,
        "userId": user_id,
        "version": version,
        "canTeacher": bool(can_teacher),
        "runtimeBase": "__sp_runtime__",
        "initialState": initial_state or {},
        "visitedSpreads": visited_spreads or [],
        "startSpread": start_spread or "",
        "startChapter": start_chapter or "",
        "startProfile": start_profile or "",
        "startTheme": start_theme or "",
        "startLang": start_lang or "",
    }
    escaped_cfg = html.escape(json.dumps(cfg_payload, ensure_ascii=False), quote=True)

    head_injection = (
        f'<meta name="sp-book-config" content="{escaped_cfg}">\n'
        '<script src="__sp_runtime__/bridge.js"></script>\n'
        '<link rel="stylesheet" href="__sp_runtime__/reader.css">\n'
    )

    # Inject early in <head> (so bridge.js runs before inline book scripts) and append reader.css last in head if </head> exists
    head_open = re.search(r"<head[^>]*>", text, re.IGNORECASE)
    head_close = re.search(r"</head>", text, re.IGNORECASE)

    if head_open and head_close:
        early_part = (
            f'<meta name="sp-book-config" content="{escaped_cfg}">\n'
            '<script src="__sp_runtime__/bridge.js"></script>\n'
        )
        css_part = '<link rel="stylesheet" href="__sp_runtime__/reader.css">\n'
        idx_open = head_open.end()
        text = text[:idx_open] + "\n" + early_part + text[idx_open:]
        head_close2 = re.search(r"</head>", text, re.IGNORECASE)
        if head_close2:
            idx_close = head_close2.start()
            text = text[:idx_close] + "\n" + css_part + text[idx_close:]
    else:
        body_open = re.search(r"<body[^>]*>", text, re.IGNORECASE)
        if body_open:
            idx = body_open.start()
            text = text[:idx] + head_injection + text[idx:]
        else:
            text = head_injection + text

    return text.encode("utf-8")


_VOID_HTML_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr",
}
_SVG_SELF_CLOSING_NO_CHILDREN = {"circle", "ellipse", "line", "path", "polygon", "polyline", "rect", "stop", "use"}
_COVER_PAGE_CACHE: dict[tuple[str, int], str] = {}
_LOGO_DATA_URI_CACHE: str | None = None
_BRAND_TEXT_RE = re.compile(
    r"<([a-zA-Z0-9]+)\b([^>]*\bclass\s*=\s*(?:\"[^\"]*\bbrand\b[^\"]*\"|'[^']*\bbrand\b[^']*')[^>]*)>([^<]*?SPACE[^<]*?)</\1>",
    re.IGNORECASE | re.DOTALL,
)


def _logo_data_uri() -> str:
    global _LOGO_DATA_URI_CACHE
    if _LOGO_DATA_URI_CACHE is not None:
        return _LOGO_DATA_URI_CACHE
    logo_path = STATIC_BOOKS_DIR / "logo-white.png"
    if logo_path.exists():
        b64 = base64.b64encode(logo_path.read_bytes()).decode("ascii")
        _LOGO_DATA_URI_CACHE = f"data:image/png;base64,{b64}"
    else:
        _LOGO_DATA_URI_CACHE = ""
    return _LOGO_DATA_URI_CACHE


class _BookCoverExtractor(HTMLParser):
    """Extracts stylesheets and the first cover/page fragment while stripping scripts & inline handlers."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.styles: list[str] = []
        self._in_style = False
        self._style_chunks: list[str] = []
        self._in_script = False
        # slot priority: 0 = data-book-cover, 1 = data-name="cover", 2 = class~="cover", 3 = first page/spread
        self.captured: dict[int, str] = {}
        self._active: dict[int, tuple[int, list[str]]] = {}
        self._skip_script_depth = 0

    def _serialize_start(self, tag: str, attrs: list[tuple[str, str | None]], *, self_close: bool = False) -> str:
        safe_attrs: list[str] = []
        for k, v in attrs:
            kl = (k or "").lower()
            if not kl or kl.startswith("on"):
                continue
            if kl in ("href", "src", "xlink:href") and v and v.strip().lower().startswith("javascript:"):
                continue
            if v is None:
                safe_attrs.append(kl)
            else:
                safe_attrs.append(f'{k}="{html.escape(v, quote=True)}"')
        attr_str = (" " + " ".join(safe_attrs)) if safe_attrs else ""
        return f"<{tag}{attr_str}/>" if self_close else f"<{tag}{attr_str}>"

    def _matched_slots(self, tag: str, attrs: list[tuple[str, str | None]]) -> list[int]:
        attr_map = {(k or "").lower(): (v or "") for k, v in attrs}
        classes = set(attr_map.get("class", "").split())
        slots: list[int] = []
        if "data-book-cover" in attr_map:
            slots.append(0)
        if attr_map.get("data-name") == "cover":
            slots.append(1)
        if "cover" in classes:
            slots.append(2)
        if "page" in classes or "spread" in classes:
            slots.append(3)
        return slots

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tlow = tag.lower()
        if tlow == "script":
            self._in_script = True
            self._skip_script_depth += 1
            return
        if self._in_script:
            return
        if tlow == "style":
            self._in_style = True
            self._style_chunks = []

        for slot in self._matched_slots(tlow, attrs):
            if slot not in self.captured and slot not in self._active:
                self._active[slot] = (0, [])

        serialized = self._serialize_start(tag, attrs, self_close=False)
        is_void = tlow in _VOID_HTML_TAGS
        for slot, (depth, buf) in list(self._active.items()):
            buf.append(serialized)
            if not is_void:
                self._active[slot] = (depth + 1, buf)
            elif depth == 0:
                self.captured[slot] = "".join(buf)
                del self._active[slot]

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tlow = tag.lower()
        if tlow == "script" or self._in_script:
            return
        for slot in self._matched_slots(tlow, attrs):
            if slot not in self.captured and slot not in self._active:
                self.captured[slot] = self._serialize_start(tag, attrs, self_close=True)
        if self._active:
            serialized = self._serialize_start(tag, attrs, self_close=True)
            for _slot, (_depth, buf) in self._active.items():
                buf.append(serialized)

    def handle_endtag(self, tag: str) -> None:
        tlow = tag.lower()
        if tlow == "script":
            if self._skip_script_depth > 0:
                self._skip_script_depth -= 1
            if self._skip_script_depth == 0:
                self._in_script = False
            return
        if self._in_script:
            return
        if tlow == "style" and self._in_style:
            self._in_style = False
            css_text = "".join(self._style_chunks).strip()
            if css_text:
                self.styles.append(css_text)
            self._style_chunks = []
        if tlow in _VOID_HTML_TAGS:
            return

        closing = f"</{tag}>"
        for slot, (depth, buf) in list(self._active.items()):
            buf.append(closing)
            next_depth = depth - 1
            if next_depth <= 0:
                self.captured[slot] = "".join(buf)
                del self._active[slot]
            else:
                self._active[slot] = (next_depth, buf)

    def handle_data(self, data: str) -> None:
        if self._in_script:
            return
        if self._in_style:
            self._style_chunks.append(data)
        for _slot, (_depth, buf) in self._active.items():
            buf.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._in_script:
            return
        ref = f"&{name};"
        for _slot, (_depth, buf) in self._active.items():
            buf.append(ref)

    def handle_charref(self, name: str) -> None:
        if self._in_script:
            return
        ref = f"&#{name};"
        for _slot, (_depth, buf) in self._active.items():
            buf.append(ref)


def extract_cover_page_html(html_bytes: bytes, *, title: str = "") -> str:
    """Extract the book's first/cover page into a self-contained 480x640 HTML preview document."""
    raw = html_bytes.decode("utf-8", errors="replace")
    parser = _BookCoverExtractor()
    parser.feed(raw)
    parser.close()

    fragment = ""
    for slot in (0, 1, 2, 3):
        if parser.captured.get(slot):
            fragment = parser.captured[slot]
            break

    logo_uri = _logo_data_uri()
    logo_img = (
        f'<img src="{logo_uri}" alt="SpacePoint" class="sp-brand-logo" />'
        if logo_uri
        else ""
    )

    if fragment and logo_img:
        fragment = _BRAND_TEXT_RE.sub(logo_img, fragment)

    if not fragment:
        safe_title = html.escape(title or "Interactive Book")
        fragment = (
            '<div class="page cover sp-fallback-cover">'
            '<div class="pin">'
            f"<div>{logo_img}<h1 style='margin-top:24px'>{safe_title}</h1></div>"
            "</div></div>"
        )

    book_styles = "\n".join(f"<style>\n{s}\n</style>" for s in parser.styles)
    override_css = """
html, body {
  margin: 0 !important;
  padding: 0 !important;
  width: 480px !important;
  height: 640px !important;
  overflow: hidden !important;
  background: #18181b !important;
  background-image: none !important;
  color: #ffffff !important;
  font-family: "Inter Variable", "Inter", "IBM Plex Sans Arabic", system-ui, -apple-system, sans-serif !important;
}
html[data-lang="en"] .ar,
html[data-lang="ar"] .en {
  display: none !important;
}
button, .btn, [data-goto], .btab, .bbadge, .cchip, .hatrow, .tags, .ladder, .bar, .pager {
  display: none !important;
}
body > .spread,
body > .page,
body > [data-book-cover],
.spread > .page,
.page.cover {
  position: static !important;
  inset: auto !important;
  width: 100% !important;
  height: 100% !important;
  min-height: 100% !important;
  display: flex !important;
  flex-direction: column !important;
  visibility: visible !important;
  border-radius: 0 !important;
  box-shadow: none !important;
  overflow: hidden !important;
}
.page::after {
  display: none !important;
}
.page.cover {
  background: #18181b !important;
  background-image: none !important;
  color: #ffffff !important;
  border-top: 6px solid #7c3aed !important;
}
.page.cover .pin,
[data-book-cover] .pin {
  flex: 1 !important;
  height: 100% !important;
  display: flex !important;
  flex-direction: column !important;
  justify-content: space-between !important;
  padding: 36px 34px 28px !important;
  gap: 16px !important;
  overflow: hidden !important;
}
.page.cover h1,
[data-book-cover] h1 {
  font-size: 36px !important;
  line-height: 1.15 !important;
  font-weight: 700 !important;
  letter-spacing: -0.02em !important;
  margin: 0 !important;
  color: #ffffff !important;
}
.page.cover p,
[data-book-cover] p {
  font-size: 14px !important;
  line-height: 1.5 !important;
  color: #d4d4d8 !important;
  margin-top: 12px !important;
}
.page.cover .sub,
[data-book-cover] .sub {
  color: #a78bfa !important;
}
.page.cover .art,
[data-book-cover] svg {
  width: 100% !important;
  max-height: 255px !important;
  flex: 1 1 auto !important;
  object-fit: contain !important;
}
.sp-brand-logo {
  height: 26px !important;
  width: auto !important;
  display: block !important;
  object-fit: contain !important;
  margin-inline-start: auto !important;
}
""".strip()

    safe_doc_title = html.escape(title or "Book Cover")
    return (
        "<!doctype html>"
        '<html lang="en" data-lang="en" data-sp-cover-preview="1">'
        "<head>"
        '<meta charset="utf-8">'
        f"<title>{safe_doc_title}</title>"
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=IBM+Plex+Sans+Arabic:wght@400;500;600;700&display=swap">'
        f"{book_styles}"
        f"<style>{override_css}</style>"
        "</head>"
        f"<body>{fragment}</body>"
        "</html>"
    )


async def get_book_cover_page_html(book: LmsBook) -> str:
    """Download entry HTML from R2/local storage (cached by book_id + bundle_version) and extract its cover page."""
    cache_key = (str(book.id), int(book.bundle_version or 0))
    cached = _COVER_PAGE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    entry = sanitize_relative_path(book.bundle_entry or "index.html")
    rel_key = f"{book.id}/v{int(book.bundle_version or 0)}/{entry}"
    raw_bytes = await books_storage.download_book_file(
        BOOK_BUNDLE_PREFIX,
        rel_key,
        backend=book.bundle_storage_backend,
    )
    rendered = extract_cover_page_html(raw_bytes, title=book.title)
    if len(_COVER_PAGE_CACHE) >= 64:
        oldest_key = next(iter(_COVER_PAGE_CACHE))
        _COVER_PAGE_CACHE.pop(oldest_key, None)
    _COVER_PAGE_CACHE[cache_key] = rendered
    return rendered


async def sync_book_progress(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    book_id: uuid.UUID,
    body: BookProgressSyncIn,
) -> LmsBookProgress:
    row = (
        await db.execute(
            select(LmsBookProgress).where(
                LmsBookProgress.user_id == user_id,
                LmsBookProgress.book_id == book_id,
            )
        )
    ).scalars().first()

    now = datetime.now(timezone.utc)
    if row is None:
        row = LmsBookProgress(
            id=uuid.uuid4(),
            user_id=user_id,
            book_id=book_id,
            visited_spreads=[],
            stars={},
            raw_state={},
        )
        db.add(row)

    if body.current_spread is not None:
        row.current_spread = body.current_spread
    if body.current_chapter is not None:
        row.current_chapter = body.current_chapter
    if body.active_profile is not None:
        row.active_profile = body.active_profile
    if body.visited_spreads is not None:
        merged = list(dict.fromkeys([*(row.visited_spreads or []), *body.visited_spreads]))
        row.visited_spreads = merged
    if body.stars is not None:
        merged_stars = dict(row.stars or {})
        for k, v in body.stars.items():
            merged_stars[k] = max(int(merged_stars.get(k, 0)), int(v))
        row.stars = merged_stars
    if body.stars_earned is not None:
        row.stars_earned = max(int(row.stars_earned or 0), int(body.stars_earned))
    elif row.stars:
        row.stars_earned = sum(int(v or 0) for v in row.stars.values())
    if body.stars_possible is not None:
        row.stars_possible = int(body.stars_possible)
    if body.completion_pct is not None:
        row.completion_pct = max(int(row.completion_pct or 0), min(100, int(body.completion_pct)))
    if body.raw_state is not None:
        merged_raw = dict(row.raw_state or {})
        merged_raw.update(body.raw_state)
        row.raw_state = merged_raw

    row.last_read_at = now
    row.updated_at = now
    await db.flush()
    return row


async def upsert_book_exercise_response(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    book_id: uuid.UUID,
    body: BookExerciseIn,
) -> LmsBookExerciseResponse:
    row = (
        await db.execute(
            select(LmsBookExerciseResponse).where(
                LmsBookExerciseResponse.user_id == user_id,
                LmsBookExerciseResponse.book_id == book_id,
                LmsBookExerciseResponse.exercise_key == body.exercise_key,
            )
        )
    ).scalars().first()

    now = datetime.now(timezone.utc)
    if row is None:
        row = LmsBookExerciseResponse(
            id=uuid.uuid4(),
            user_id=user_id,
            book_id=book_id,
            chapter_key=body.chapter_key,
            exercise_key=body.exercise_key,
            exercise_type=body.exercise_type,
            prompt_text=body.prompt_text,
            answer_json=body.answer_json,
            is_correct=body.is_correct,
            score_stars=body.score_stars,
            max_stars=body.max_stars,
            attempts=1,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        await db.flush()
        return row

    if body.chapter_key is not None:
        row.chapter_key = body.chapter_key
    if body.prompt_text is not None:
        row.prompt_text = body.prompt_text
    row.answer_json = body.answer_json
    if body.is_correct is not None:
        row.is_correct = body.is_correct
    if body.score_stars is not None:
        row.score_stars = max(int(row.score_stars or 0), int(body.score_stars))
    if body.max_stars is not None:
        row.max_stars = body.max_stars
    if body.exercise_type != "notebook":
        row.attempts = int(row.attempts or 0) + 1
    row.updated_at = now
    await db.flush()
    return row


async def book_analytics(
    db: AsyncSession,
    *,
    book_id: uuid.UUID,
    cohort_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    cohort_user_ids: set[uuid.UUID] | None = None
    if cohort_id is not None:
        cohort_user_ids = set(
            (
                await db.execute(
                    select(LmsProgramAssignment.user_id).where(LmsProgramAssignment.cohort_id == cohort_id)
                )
            ).scalars().all()
        )

    enroll_q = select(LmsBookEnrollment).where(
        LmsBookEnrollment.book_id == book_id,
        LmsBookEnrollment.status == "active",
    )
    if cohort_user_ids is not None:
        enroll_q = enroll_q.where(LmsBookEnrollment.user_id.in_(cohort_user_ids or [uuid.UUID(int=0)]))
    enrollments = (await db.execute(enroll_q)).scalars().all()

    prog_q = select(LmsBookProgress).where(LmsBookProgress.book_id == book_id)
    if cohort_user_ids is not None:
        prog_q = prog_q.where(LmsBookProgress.user_id.in_(cohort_user_ids or [uuid.UUID(int=0)]))
    progress_rows = (await db.execute(prog_q)).scalars().all()
    progress_by_user = {p.user_id: p for p in progress_rows}

    resp_q = select(LmsBookExerciseResponse).where(LmsBookExerciseResponse.book_id == book_id)
    if cohort_user_ids is not None:
        resp_q = resp_q.where(LmsBookExerciseResponse.user_id.in_(cohort_user_ids or [uuid.UUID(int=0)]))
    responses = (await db.execute(resp_q.order_by(LmsBookExerciseResponse.updated_at.desc()))).scalars().all()

    user_ids = {e.user_id for e in enrollments} | {p.user_id for p in progress_rows} | {r.user_id for r in responses}
    users_by_id: dict[uuid.UUID, User] = {}
    if user_ids:
        u_rows = (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
        users_by_id = {u.id: u for u in u_rows}

    resp_by_user: dict[uuid.UUID, list[LmsBookExerciseResponse]] = {}
    for r in responses:
        resp_by_user.setdefault(r.user_id, []).append(r)

    learners = []
    for uid in user_ids:
        u = users_by_id.get(uid)
        if u is None:
            continue
        p = progress_by_user.get(uid)
        u_resps = resp_by_user.get(uid, [])
        gradable = [r for r in u_resps if r.exercise_type in ("quiz", "your_turn", "game") and r.is_correct is not None]
        learners.append(
            {
                "user_id": uid,
                "full_name": u.full_name,
                "email": u.email,
                "completion_pct": int(p.completion_pct or 0) if p else 0,
                "stars_earned": int(p.stars_earned or 0) if p else 0,
                "stars_possible": int(p.stars_possible or 0) if p else 0,
                "current_chapter": p.current_chapter if p else None,
                "exercises_answered": len(gradable),
                "exercises_correct": sum(1 for r in gradable if r.is_correct),
                "notebook_count": sum(
                    1
                    for r in u_resps
                    if r.exercise_type == "notebook" and str((r.answer_json or {}).get("text", "")).strip()
                ),
                "last_read_at": p.last_read_at if p else None,
            }
        )
    learners.sort(key=lambda x: (x["completion_pct"], x["stars_earned"]), reverse=True)

    # Aggregate exercises
    ex_groups: dict[str, list[LmsBookExerciseResponse]] = {}
    for r in responses:
        if r.exercise_type == "notebook":
            continue
        ex_groups.setdefault(r.exercise_key, []).append(r)

    exercises = []
    for key, rows in ex_groups.items():
        first = rows[0]
        graded = [r for r in rows if r.is_correct is not None]
        correct_cnt = sum(1 for r in graded if r.is_correct)
        acc = round(100 * correct_cnt / len(graded)) if graded else None
        starred = [r.score_stars for r in rows if r.score_stars is not None]
        avg_stars = round(sum(starred) / len(starred), 2) if starred else None
        exercises.append(
            {
                "exercise_key": key,
                "chapter_key": first.chapter_key,
                "exercise_type": first.exercise_type,
                "prompt_text": first.prompt_text,
                "responses_count": len(rows),
                "correct_count": correct_cnt,
                "accuracy_pct": acc,
                "avg_stars": avg_stars,
                "total_attempts": sum(int(r.attempts or 1) for r in rows),
            }
        )
    exercises.sort(key=lambda x: (x["chapter_key"] or "", x["exercise_type"], x["exercise_key"]))

    notebooks = []
    for r in responses:
        if r.exercise_type != "notebook":
            continue
        ans_text = str((r.answer_json or {}).get("text", "")).strip()
        if not ans_text:
            continue
        u = users_by_id.get(r.user_id)
        if u is None:
            continue
        notebooks.append(
            {
                "user_id": r.user_id,
                "student_name": u.full_name,
                "student_email": u.email,
                "chapter_key": r.chapter_key,
                "exercise_key": r.exercise_key,
                "prompt_text": r.prompt_text,
                "answer_text": ans_text,
                "updated_at": r.updated_at,
            }
        )

    all_graded = [r for r in responses if r.exercise_type in ("quiz", "your_turn", "game") and r.is_correct is not None]
    overall_acc = round(100 * sum(1 for r in all_graded if r.is_correct) / len(all_graded)) if all_graded else None
    active_readers = [p for p in progress_rows if (p.completion_pct or 0) > 0 or p.last_read_at is not None]
    avg_comp = round(sum(int(p.completion_pct or 0) for p in active_readers) / len(active_readers)) if active_readers else 0

    return {
        "book_id": book_id,
        "total_enrolled": len(enrollments),
        "active_readers": len(active_readers),
        "avg_completion_pct": avg_comp,
        "total_responses": len(responses),
        "exercise_accuracy_pct": overall_acc,
        "learners": learners,
        "exercises": exercises,
        "notebooks": notebooks,
    }


async def export_book_responses_csv(
    db: AsyncSession,
    *,
    book_id: uuid.UUID,
    cohort_id: uuid.UUID | None = None,
) -> str:
    data = await book_analytics(db, book_id=book_id, cohort_id=cohort_id)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Section", "Student Name", "Email", "Chapter", "Exercise Key", "Type", "Prompt / Metric", "Answer / Value", "Correct", "Stars", "Updated At"])

    for l in data["learners"]:
        writer.writerow([
            "Learner Progress",
            l["full_name"],
            l["email"],
            l["current_chapter"] or "",
            "",
            "progress",
            f"Completion {l['completion_pct']}%",
            f"Stars {l['stars_earned']}/{l['stars_possible']}",
            f"{l['exercises_correct']}/{l['exercises_answered']}",
            l["stars_earned"],
            l["last_read_at"].isoformat() if l["last_read_at"] else "",
        ])

    resp_q = select(LmsBookExerciseResponse).where(LmsBookExerciseResponse.book_id == book_id)
    if cohort_id is not None:
        cohort_uids = set(
            (await db.execute(select(LmsProgramAssignment.user_id).where(LmsProgramAssignment.cohort_id == cohort_id))).scalars().all()
        )
        resp_q = resp_q.where(LmsBookExerciseResponse.user_id.in_(cohort_uids or [uuid.UUID(int=0)]))
    rows = (await db.execute(resp_q.order_by(LmsBookExerciseResponse.updated_at.desc()))).scalars().all()
    uids = {r.user_id for r in rows}
    users = {u.id: u for u in (await db.execute(select(User).where(User.id.in_(uids)))).scalars().all()} if uids else {}

    for r in rows:
        u = users.get(r.user_id)
        ans = r.answer_json or {}
        ans_display = ans.get("text") or ans.get("answer") or ans.get("value") or json.dumps(ans, ensure_ascii=False)
        writer.writerow([
            "Response",
            u.full_name if u else str(r.user_id),
            u.email if u else "",
            r.chapter_key or "",
            r.exercise_key,
            r.exercise_type,
            r.prompt_text or "",
            ans_display,
            "" if r.is_correct is None else ("Yes" if r.is_correct else "No"),
            "" if r.score_stars is None else r.score_stars,
            r.updated_at.isoformat() if r.updated_at else "",
        ])

    return buf.getvalue()

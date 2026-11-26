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
    LmsBookEdition,
    LmsBookEnrollment,
    LmsBookExerciseResponse,
    LmsBookProgress,
)
from app.models.lms.program import LmsProgramAssignment, LmsProgramCohortOverride, LmsProgramItem
from app.models.sessions.cohort import Cohort
from app.models.spine.organization import Organization
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
_STAFF_PREVIEW_ROLES = {"admin", "operations", "facilitator", "lms_author"}
_STAFF_TEACHER_ROLES = {"admin", "operations", "facilitator", "lms_author", "instructor"}

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify_book(title: str) -> str:
    base = _SLUG_RE.sub("-", (title or "").strip().lower()).strip("-")
    return base[:96] or f"book-{uuid.uuid4().hex[:8]}"


def is_book_staff_preview(user: User) -> bool:
    """True for ops/authors/admins who can preview all books (including drafts/invite-only)."""
    roles = set(user.role_values or [])
    return bool(roles & _STAFF_PREVIEW_ROLES)


def can_manage_master_books(user: User) -> bool:
    """True only for SpacePoint staff/authors permitted to create/upload/publish/delete master books."""
    roles = set(user.role_values or [])
    return bool(roles & _STAFF_PREVIEW_ROLES)


def can_user_teacher_mode(user: User) -> bool:
    """True for staff and instructors who can toggle Teacher notes inside books they can access."""
    roles = set(user.role_values or [])
    return bool(roles & _STAFF_TEACHER_ROLES)


async def resolve_book_user_org(db: AsyncSession, user: User) -> Organization | None:
    """Return the user's sandbox Organization if they hold an organization role."""
    if "organization" not in set(user.role_values or []):
        return None
    from app.services.website_events import resolve_user_organization

    return await resolve_user_organization(db, user)


async def org_cohort_used_book_ids(db: AsyncSession, org_id: uuid.UUID) -> set[uuid.UUID]:
    """Return book IDs already attached to any cohort's LMS checklist in this organization."""
    from app.services.lms.program import effective_cohort_program_items

    cids = (
        await db.execute(select(Cohort.id).where(Cohort.organization_id == org_id))
    ).scalars().all()
    used: set[uuid.UUID] = set()
    for cid in cids:
        resolved = await effective_cohort_program_items(db, cohort_id=cid)
        if not resolved:
            continue
        _prog, items, _inherited = resolved
        for it in items:
            if it.item_type == "book" and it.book_id is not None:
                used.add(it.book_id)
    return used


async def is_book_allowed_for_org(db: AsyncSession, org: Organization, book: LmsBook) -> bool:
    """Whether an organization owner/coordinator can read/use this published SpacePoint book."""
    if not book.is_published:
        return False
    scope = (getattr(org, "book_scope", None) or "none").strip().lower()
    if scope == "all":
        return True
    if scope == "selected":
        allowed = {str(x) for x in (getattr(org, "allowed_book_ids", None) or [])}
        if str(book.id) in allowed:
            return True
    return book.id in await org_cohort_used_book_ids(db, org.id)


async def accessible_org_book_ids(db: AsyncSession, org: Organization) -> set[uuid.UUID] | None:
    """Return allowed published book_ids for `org`, or None when `book_scope == 'all'`."""
    scope = (getattr(org, "book_scope", None) or "none").strip().lower()
    if scope == "all":
        return None
    ids = await org_cohort_used_book_ids(db, org.id)
    if scope == "selected":
        for raw in (getattr(org, "allowed_book_ids", None) or []):
            try:
                ids.add(uuid.UUID(str(raw)))
            except (ValueError, TypeError):
                continue
    return ids


async def user_has_teacher_mode(db: AsyncSession, *, user: User, book: LmsBook) -> bool:
    """True if staff/instructor or an organization owner/coordinator with access to `book`."""
    if can_user_teacher_mode(user):
        return True
    org = await resolve_book_user_org(db, user)
    if org is not None:
        return await is_book_allowed_for_org(db, org, book)
    return False


def can_user_edit_edition(
    user: User,
    edition: LmsBookEdition,
    org: Organization | None,
) -> bool:
    """Staff edit any edition; org owners edit any edition in their org; coordinators edit their own."""
    if can_manage_master_books(user):
        return True
    if org is not None and edition.organization_id == org.id:
        if org.owner_user_id == user.id:
            return True
        if edition.created_by == user.id:
            return True
    return False


def serialize_book_edition(
    edition: LmsBookEdition,
    *,
    current_user: User,
    org: Organization | None,
    creator_name: str | None = None,
) -> dict[str, Any]:
    return {
        "id": edition.id,
        "book_id": edition.book_id,
        "organization_id": edition.organization_id,
        "created_by": edition.created_by,
        "creator_name": creator_name,
        "title": edition.title,
        "title_ar": edition.title_ar,
        "description": edition.description,
        "chapter_keys": list(edition.chapter_keys or []),
        "default_lang": edition.default_lang,
        "can_edit": can_user_edit_edition(current_user, edition, org),
        "created_at": edition.created_at,
        "updated_at": edition.updated_at,
    }


async def visible_editions_for_book(
    db: AsyncSession,
    *,
    book_id: uuid.UUID,
    current_user: User,
    org: Organization | None = None,
) -> list[dict[str, Any]]:
    """Return global SpacePoint editions plus editions belonging to the user's org."""
    stmt = select(LmsBookEdition).where(LmsBookEdition.book_id == book_id)
    if not can_manage_master_books(current_user):
        if org is not None:
            stmt = stmt.where(
                or_(
                    LmsBookEdition.organization_id.is_(None),
                    LmsBookEdition.organization_id == org.id,
                )
            )
        else:
            stmt = stmt.where(LmsBookEdition.organization_id.is_(None))
    rows = (await db.execute(stmt.order_by(LmsBookEdition.created_at.asc()))).scalars().all()
    creator_ids = {r.created_by for r in rows if r.created_by is not None}
    creators: dict[uuid.UUID, str] = {}
    if creator_ids:
        u_rows = (await db.execute(select(User.id, User.full_name).where(User.id.in_(creator_ids)))).all()
        creators = {uid: fname for uid, fname in u_rows}
    return [
        serialize_book_edition(
            r,
            current_user=current_user,
            org=org,
            creator_name=creators.get(r.created_by) if r.created_by else None,
        )
        for r in rows
    ]


def validate_chapter_keys_for_book(book: LmsBook, chapter_keys: list[str]) -> list[str]:
    """Normalize ordered chapter keys and reject unknown keys when the book has a parsed outline."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in chapter_keys or []:
        k = str(raw or "").strip()
        if k and k not in seen:
            seen.add(k)
            cleaned.append(k)
    if not cleaned:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Select at least one chapter")
    outline_keys = {str(ch.get("key") or "") for ch in (book.outline or []) if ch.get("key")}
    if outline_keys:
        unknown = [k for k in cleaned if k not in outline_keys]
        if unknown:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown chapter key(s) for book '{book.title}': {', '.join(unknown)}",
            )
    return cleaned


# Earlier SatKit packaging mapped SBOX `key` (`pbench`, `cbuild`, ...) instead of the DOM spread `name` (`u10box`, `u10box2`, ...).
_LEGACY_SANDBOX_KEY_TO_SPREAD: dict[str, str] = {
    "thrbox": "u2box",
    "colbox": "u3box",
    "trkbox": "u4box",
    "orbbox": "u5box",
    "spinbox": "u6box",
    "oscbox": "u7box",
    "wtank": "u8box",
    "thbox": "u9box",
    "pbench": "u10box",
    "cbuild": "u10box2",
    "magbox": "u11box",
    "sigbox": "u12box",
    "decbox": "u13box",
    "gasbox": "u14box",
}
_SPREAD_TO_LEGACY_SANDBOX_KEY: dict[str, str] = {v: k for k, v in _LEGACY_SANDBOX_KEY_TO_SPREAD.items()}


def normalize_visited_spreads(spreads: list[str] | None) -> list[str]:
    """Map any legacy sandbox keys in `visited_spreads` to their canonical DOM spread names."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in spreads or []:
        s = _LEGACY_SANDBOX_KEY_TO_SPREAD.get(str(raw), str(raw))
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def normalize_outline_spreads(outline: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Return outline chapters with any legacy sandbox keys normalized to DOM spread names."""
    out: list[dict[str, Any]] = []
    for ch in outline or []:
        if not isinstance(ch, dict):
            continue
        lessons = ch.get("lessons")
        if isinstance(lessons, list):
            fixed_lessons: list[dict[str, Any]] = []
            changed = False
            for les in lessons:
                if isinstance(les, dict):
                    sp = str(les.get("spread") or "")
                    mapped = _LEGACY_SANDBOX_KEY_TO_SPREAD.get(sp)
                    if mapped:
                        fixed_lessons.append({**les, "spread": mapped})
                        changed = True
                        continue
                fixed_lessons.append(les)
            out.append({**ch, "lessons": fixed_lessons} if changed else ch)
        else:
            out.append(ch)
    return out


def filter_outline_by_chapters(outline: list[dict[str, Any]] | None, chapter_keys: list[str] | None) -> list[dict[str, Any]]:
    """Return outline chapters filtered and ordered by `chapter_keys` (or full outline when None)."""
    raw = normalize_outline_spreads(outline)
    if not chapter_keys:
        return raw
    by_key = {str(ch.get("key") or ""): ch for ch in raw if ch.get("key")}
    ordered = [by_key[k] for k in chapter_keys if k in by_key]
    return ordered if ordered else [ch for ch in raw if str(ch.get("key") or "") in set(chapter_keys)]


async def sync_manifest_profiles_to_editions(
    db: AsyncSession,
    book: LmsBook,
    *,
    actor_user_id: uuid.UUID | None = None,
) -> list[LmsBookEdition]:
    """Ensure non-empty tracks in `book.profiles` exist as SpacePoint `LmsBookEdition` rows."""
    profiles = [p for p in (book.profiles or []) if isinstance(p, dict) and (p.get("groups") or [])]
    if not profiles:
        return []
    existing = (
        await db.execute(
            select(LmsBookEdition).where(
                LmsBookEdition.book_id == book.id,
                LmsBookEdition.organization_id.is_(None),
            )
        )
    ).scalars().all()
    existing_titles = {e.title.strip().lower() for e in existing if e.title}
    existing_slices = {tuple(str(k) for k in (e.chapter_keys or [])) for e in existing}

    created: list[LmsBookEdition] = []
    now = datetime.now(timezone.utc)
    for prof in profiles:
        groups = [str(k).strip() for k in (prof.get("groups") or []) if str(k or "").strip()]
        if not groups:
            continue
        title = str(prof.get("label_en") or prof.get("key") or "Edition").strip()[:200]
        if not title:
            continue
        if title.lower() in existing_titles or tuple(groups) in existing_slices:
            continue
        title_ar = str(prof.get("label_ar")).strip()[:200] if prof.get("label_ar") else None
        default_lang = str(prof.get("default_lang")).strip()[:8] if prof.get("default_lang") else None
        ed = LmsBookEdition(
            id=uuid.uuid4(),
            book_id=book.id,
            organization_id=None,
            created_by=actor_user_id or book.created_by,
            title=title,
            title_ar=title_ar,
            description=str(prof.get("subtitle_en")).strip() if prof.get("subtitle_en") else None,
            chapter_keys=groups,
            default_lang=default_lang,
            created_at=now,
            updated_at=now,
        )
        db.add(ed)
        created.append(ed)
        existing_titles.add(title.lower())
        existing_slices.add(tuple(groups))
    if created:
        await db.flush()
    return created


async def resolve_item_chapters(
    db: AsyncSession,
    book: LmsBook,
    *,
    book_chapters: list[str] | None = None,
    book_edition_id: uuid.UUID | None = None,
    book_chapter: str | None = None,
    book_profile: str | None = None,
) -> tuple[list[str] | None, LmsBookEdition | None]:
    """Resolve explicit chapter keys + optional edition object for a book item."""
    if book_edition_id is not None:
        edition = await db.get(LmsBookEdition, book_edition_id)
        if edition is not None and edition.book_id == book.id:
            keys = [str(k) for k in (edition.chapter_keys or []) if str(k).strip()]
            return (keys or None), edition
    if book_chapters:
        keys = [str(k).strip() for k in book_chapters if str(k or "").strip()]
        if keys:
            return list(dict.fromkeys(keys)), None
    if book_chapter:
        return [book_chapter], None
    if book_profile:
        for prof in book.profiles or []:
            if str(prof.get("key") or "") == book_profile:
                groups = [str(g).strip() for g in (prof.get("groups") or []) if str(g or "").strip()]
                if groups:
                    return list(dict.fromkeys(groups)), None
    return None, None


def compute_book_slice_completion(
    book: LmsBook,
    progress: LmsBookProgress | None,
    chapter_keys: list[str] | None,
) -> int:
    """Compute completion percentage strictly across `chapter_keys` (or whole book when None)."""
    if progress is None:
        return 0
    if not chapter_keys:
        return int(progress.completion_pct or 0)
    target_set = {str(k) for k in chapter_keys if str(k).strip()}
    if not target_set:
        return int(progress.completion_pct or 0)
    target_spreads: list[str] = []
    for ch in book.outline or []:
        if str(ch.get("key") or "") not in target_set:
            continue
        for lesson in ch.get("lessons") or []:
            sp = str(lesson.get("spread") or "").strip()
            if sp and sp not in target_spreads:
                target_spreads.append(sp)
    if target_spreads:
        visited = {str(s) for s in (progress.visited_spreads or [])}
        # Accept either DOM spread name (e.g. u10box2) or legacy sandbox key (e.g. cbuild)
        expanded_visited = set(visited)
        for v in visited:
            if v in _LEGACY_SANDBOX_KEY_TO_SPREAD:
                expanded_visited.add(_LEGACY_SANDBOX_KEY_TO_SPREAD[v])
            if v in _SPREAD_TO_LEGACY_SANDBOX_KEY:
                expanded_visited.add(_SPREAD_TO_LEGACY_SANDBOX_KEY[v])
        matched = 0
        for sp in target_spreads:
            canonical = _LEGACY_SANDBOX_KEY_TO_SPREAD.get(sp, sp)
            if sp in expanded_visited or canonical in expanded_visited:
                matched += 1
        return round(100 * matched / len(target_spreads))
    return 100 if progress.current_chapter in target_set else 0


async def instructor_program_book_ids(db: AsyncSession, *, user: User) -> set[uuid.UUID]:
    """Return book_ids included in the effective LMS Program of any cohort this instructor teaches."""
    if is_book_staff_preview(user) or "instructor" not in set(user.role_values or []):
        return set()
    from app.services.lms.program import effective_cohort_program_items
    from app.services.missions.cohort_access import instructor_cohort_ids

    cohort_ids = await instructor_cohort_ids(db, user=user)
    if not cohort_ids:
        return set()
    book_ids: set[uuid.UUID] = set()
    for cid in cohort_ids:
        resolved = await effective_cohort_program_items(db, cohort_id=cid)
        if not resolved:
            continue
        _program, items, _inherited = resolved
        for it in items:
            if it.item_type == "book" and it.book_id is not None:
                book_ids.add(it.book_id)
    return book_ids


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
    book_edition_id: uuid.UUID | None = None,
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
        changed = False
        if existing.status != "active" or expired:
            existing.status = "active"
            existing.expires_at = effective_expiry
            if purchase_id is not None:
                existing.purchase_id = purchase_id
            if granted_by is not None:
                existing.granted_by = granted_by
            changed = True
        # Upgrade a scoped enrollment if full access is now granted via purchase/self/ops or unscoped invite
        if source in ("self", "ops", "purchase") and existing.source in ("program", "invite_code"):
            existing.source = source
            existing.book_edition_id = None
            changed = True
        elif source == "invite_code" and book_edition_id is None and existing.book_edition_id is not None:
            existing.book_edition_id = None
            changed = True
        elif source == "invite_code" and book_edition_id is not None and existing.source == "program":
            existing.source = "invite_code"
            existing.book_edition_id = book_edition_id
            changed = True
        if changed:
            await db.flush()
        return existing

    row = LmsBookEnrollment(
        id=uuid.uuid4(),
        user_id=user_id,
        book_id=book_id,
        book_edition_id=book_edition_id,
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


async def resolve_user_book_access(
    db: AsyncSession,
    *,
    user: User,
    book: LmsBook,
) -> tuple[bool, list[dict[str, Any]]]:
    """Resolve what scope a user has for `book`.

    Returns `(has_full, scoped_slices)`:
    - `has_full=True` means the full book (all chapters & edition switching) is allowed.
    - When `has_full=False`, `scoped_slices` lists dicts `{edition_id, title, title_ar, chapter_keys}`
      from the student's active program/cohort items or edition-scoped invite code enrollment.
    """
    if is_book_staff_preview(user):
        return True, []
    if not book.is_published:
        return False, []
    org = await resolve_book_user_org(db, user)
    if org is not None and await is_book_allowed_for_org(db, org, book):
        return True, []
    if "instructor" in set(user.role_values or []):
        if book.id in await instructor_program_book_ids(db, user=user):
            return True, []

    enrollment = (
        await db.execute(
            select(LmsBookEnrollment).where(
                LmsBookEnrollment.user_id == user.id,
                LmsBookEnrollment.book_id == book.id,
                *book_enrollment_is_active(),
            )
        )
    ).scalars().first()
    if enrollment is None:
        return False, []

    if enrollment.source in ("self", "ops", "purchase"):
        return True, []
    if enrollment.source == "invite_code" and enrollment.book_edition_id is None:
        return True, []

    slices: list[dict[str, Any]] = []
    seen_keys: set[tuple[str | None, tuple[str, ...]]] = set()

    if enrollment.source == "invite_code" and enrollment.book_edition_id is not None:
        ed = await db.get(LmsBookEdition, enrollment.book_edition_id)
        if ed is not None and ed.book_id == book.id and (ed.chapter_keys or []):
            ch_keys = [str(k) for k in ed.chapter_keys]
            sig = (str(ed.id), tuple(ch_keys))
            seen_keys.add(sig)
            slices.append({
                "edition_id": ed.id,
                "title": ed.title,
                "title_ar": ed.title_ar,
                "chapter_keys": ch_keys,
            })

    # Inspect active program assignments across cohorts for this user.
    from app.services.lms.program import effective_cohort_program_items

    cohort_ids = (
        await db.execute(
            select(LmsProgramAssignment.cohort_id).where(LmsProgramAssignment.user_id == user.id)
        )
    ).scalars().all()
    for cid in cohort_ids:
        if cid is None:
            continue
        resolved = await effective_cohort_program_items(db, cohort_id=cid)
        if not resolved:
            continue
        _prog, items, _inherited = resolved
        for it in items:
            if it.item_type != "book" or it.book_id != book.id:
                continue
            ch_keys, edition = await resolve_item_chapters(
                db,
                book,
                book_chapters=getattr(it, "book_chapters", None),
                book_edition_id=getattr(it, "book_edition_id", None),
                book_chapter=it.book_chapter,
                book_profile=it.book_profile,
            )
            if not ch_keys:
                return True, []
            ed_id = edition.id if edition else None
            sig = (str(ed_id) if ed_id else None, tuple(ch_keys))
            if sig in seen_keys:
                continue
            seen_keys.add(sig)
            slices.append({
                "edition_id": ed_id,
                "item_id": it.id,
                "title": edition.title if edition else (it.title or book.title),
                "title_ar": edition.title_ar if edition else book.title_ar,
                "chapter_keys": ch_keys,
            })

    # If enrolled via `program` yet no matching cohort checklist item specifies a slice
    # (e.g. legacy program-level full book), do not strand the student — treat as full only if no slices found and source != invite_code.
    if not slices and enrollment.source == "program":
        return True, []
    return False, slices


async def has_book_access(db: AsyncSession, *, user: User, book: LmsBook) -> bool:
    """True if the user has either full access or at least one scoped slice of `book`."""
    has_full, slices = await resolve_user_book_access(db, user=user, book=book)
    return has_full or bool(slices)


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
        await sync_manifest_profiles_to_editions(db, book, actor_user_id=book.created_by)
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


def _runtime_asset_version() -> str:
    """Short mtime-based version stamp so browsers refresh bridge.js / reader.css immediately."""
    stamps: list[int] = []
    for name in ("bridge.js", "reader.css"):
        p = STATIC_BOOKS_DIR / name
        try:
            stamps.append(int(p.stat().st_mtime))
        except OSError:
            pass
    return str(max(stamps)) if stamps else "1"


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
    allowed_chapters: list[str] | None = None,
    locked_scope: bool = False,
    edition_id: str | None = None,
    edition_title: str | None = None,
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
        "allowedChapters": [str(c) for c in allowed_chapters] if allowed_chapters else None,
        "lockedScope": bool(locked_scope),
        "editionId": edition_id or "",
        "editionTitle": edition_title or "",
    }
    escaped_cfg = html.escape(json.dumps(cfg_payload, ensure_ascii=False), quote=True)
    rt_v = _runtime_asset_version()

    head_injection = (
        f'<meta name="sp-book-config" content="{escaped_cfg}">\n'
        f'<script src="__sp_runtime__/bridge.js?v={rt_v}"></script>\n'
        f'<link rel="stylesheet" href="__sp_runtime__/reader.css?v={rt_v}">\n'
    )

    # Inject early in <head> (so bridge.js runs before inline book scripts) and append reader.css last in head if </head> exists
    head_open = re.search(r"<head[^>]*>", text, re.IGNORECASE)
    head_close = re.search(r"</head>", text, re.IGNORECASE)

    if head_open and head_close:
        early_part = (
            f'<meta name="sp-book-config" content="{escaped_cfg}">\n'
            f'<script src="__sp_runtime__/bridge.js?v={rt_v}"></script>\n'
        )
        css_part = f'<link rel="stylesheet" href="__sp_runtime__/reader.css?v={rt_v}">\n'
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


async def _cohort_book_slice(
    db: AsyncSession,
    *,
    book: LmsBook,
    cohort_id: uuid.UUID,
) -> tuple[list[str] | None, str | None]:
    """Return merged assigned chapters + optional edition title for `book` in `cohort_id`."""
    from app.services.lms.program import effective_cohort_program_items

    resolved = await effective_cohort_program_items(db, cohort_id=cohort_id)
    if not resolved:
        return None, None
    _prog, items, _inherited = resolved
    chapters: list[str] = []
    titles: list[str] = []
    for it in items:
        if it.item_type != "book" or it.book_id != book.id:
            continue
        ch_keys, edition = await resolve_item_chapters(
            db,
            book,
            book_chapters=getattr(it, "book_chapters", None),
            book_edition_id=getattr(it, "book_edition_id", None),
            book_chapter=it.book_chapter,
            book_profile=it.book_profile,
        )
        if not ch_keys:
            return None, None
        for k in ch_keys:
            if k not in chapters:
                chapters.append(k)
        if edition and edition.title not in titles:
            titles.append(edition.title)
    return (chapters or None), (", ".join(titles) if titles else None)


async def book_analytics(
    db: AsyncSession,
    *,
    book_id: uuid.UUID,
    cohort_id: uuid.UUID | None = None,
    edition_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    book = await db.get(LmsBook, book_id)
    slice_chapters: list[str] | None = None
    edition_title: str | None = None
    if book is not None and edition_id is not None:
        ed = await db.get(LmsBookEdition, edition_id)
        if ed is not None and ed.book_id == book.id and ed.chapter_keys:
            slice_chapters = [str(k) for k in ed.chapter_keys]
            edition_title = ed.title
    elif book is not None and cohort_id is not None:
        slice_chapters, edition_title = await _cohort_book_slice(db, book=book, cohort_id=cohort_id)

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
    if slice_chapters:
        resp_q = resp_q.where(
            or_(
                LmsBookExerciseResponse.chapter_key.in_(slice_chapters),
                LmsBookExerciseResponse.chapter_key.is_(None),
            )
        )
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
        comp_pct = (
            compute_book_slice_completion(book, p, slice_chapters)
            if book is not None and slice_chapters
            else (int(p.completion_pct or 0) if p else 0)
        )
        u_resps = resp_by_user.get(uid, [])
        gradable = [r for r in u_resps if r.exercise_type in ("quiz", "your_turn", "game") and r.is_correct is not None]
        learners.append(
            {
                "user_id": uid,
                "full_name": u.full_name,
                "email": u.email,
                "completion_pct": comp_pct,
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
    active_learners = [l for l in learners if l["completion_pct"] > 0 or l["last_read_at"] is not None]
    avg_comp = round(sum(l["completion_pct"] for l in active_learners) / len(active_learners)) if active_learners else 0

    return {
        "book_id": book_id,
        "chapter_keys": slice_chapters,
        "edition_title": edition_title,
        "total_enrolled": len(enrollments),
        "active_readers": len(active_learners),
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
    edition_id: uuid.UUID | None = None,
) -> str:
    data = await book_analytics(db, book_id=book_id, cohort_id=cohort_id, edition_id=edition_id)
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
    if data.get("chapter_keys"):
        resp_q = resp_q.where(
            or_(
                LmsBookExerciseResponse.chapter_key.in_(data["chapter_keys"]),
                LmsBookExerciseResponse.chapter_key.is_(None),
            )
        )
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

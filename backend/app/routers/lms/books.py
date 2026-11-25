"""LMS Interactive Books routers — public/student catalog, reader session, R2 bundle delivery,
progress & exercise syncing, and admin/ops authoring & analytics.
"""

from __future__ import annotations

import hashlib
import mimetypes
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from jose import JWTError
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_current_active_user,
    get_current_user_optional,
    require_lms_content,
)
from app.core.security import create_book_token, decode_book_token
from app.db.session import get_db
from app.models.lms.book import (
    LmsBook,
    LmsBookEdition,
    LmsBookEnrollment,
    LmsBookExerciseResponse,
    LmsBookProgress,
)
from app.models.lms.invite_grant import InvitationCodeGrant
from app.models.lms.program import LmsProgramItem
from app.models.spine.organization import Organization
from app.models.user import User
from app.schemas.lms_books import (
    BookAdminOut,
    BookAnalyticsOut,
    BookBulkGrantIn,
    BookBulkGrantOut,
    BookBundleUploadOut,
    BookCatalogOut,
    BookCreateIn,
    BookDetailOut,
    BookEditionCreateIn,
    BookEditionOut,
    BookEditionUpdateIn,
    BookEnrollmentGrantIn,
    BookEnrollmentOut,
    BookExerciseIn,
    BookExerciseOut,
    BookProgressOut,
    BookProgressSyncIn,
    BookReaderSessionOut,
    BookUpdateIn,
)
from app.services.lms import books_storage
from app.services.lms.books import (
    STATIC_BOOKS_DIR,
    accessible_org_book_ids,
    book_analytics,
    book_enrollment_is_active,
    can_manage_master_books,
    can_user_edit_edition,
    compute_book_slice_completion,
    enroll_book,
    export_book_responses_csv,
    filter_outline_by_chapters,
    get_book_cover_page_html,
    has_book_access,
    inject_runtime_into_html,
    instructor_program_book_ids,
    is_book_allowed_for_org,
    is_book_staff_preview,
    resolve_book_user_org,
    resolve_item_chapters,
    resolve_user_book_access,
    serialize_book_edition,
    slugify_book,
    sync_book_progress,
    unpack_and_upload_book_zip,
    upsert_book_exercise_response,
    user_has_teacher_mode,
    validate_chapter_keys_for_book,
    visible_editions_for_book,
)
from app.services.lms.books_storage import BOOK_BUNDLE_PREFIX, BOOK_COVER_PREFIX, sanitize_relative_path

router = APIRouter(tags=["lms-books"])

_ALLOWED_COVER_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif", "image/svg+xml"}
_MAX_COVER_BYTES = 10 * 1024 * 1024
_MAX_BUNDLE_ZIP_BYTES = 120 * 1024 * 1024


def _progress_out(row: LmsBookProgress | None) -> BookProgressOut | None:
    if row is None:
        return None
    return BookProgressOut(
        current_spread=row.current_spread,
        current_chapter=row.current_chapter,
        active_profile=row.active_profile,
        visited_spreads=list(row.visited_spreads or []),
        stars=dict(row.stars or {}),
        stars_earned=int(row.stars_earned or 0),
        stars_possible=int(row.stars_possible or 0),
        completion_pct=int(row.completion_pct or 0),
        last_read_at=row.last_read_at,
    )


def _cover_page_url(book: LmsBook) -> str | None:
    if book.is_published and int(book.bundle_version or 0) > 0:
        return f"/lms/books/public/{book.id}/cover-page?v={int(book.bundle_version or 0)}"
    return None


async def _book_catalog_out(
    book: LmsBook,
    *,
    enrolled: bool,
    is_preview: bool,
    progress: LmsBookProgress | None,
    edition_id: uuid.UUID | None = None,
    item_id: uuid.UUID | None = None,
    edition_title: str | None = None,
    title_ar_override: str | None = None,
    allowed_chapters: list[str] | None = None,
    locked_scope: bool = False,
) -> BookCatalogOut:
    display_title = (
        f"{book.title} — {edition_title}"
        if locked_scope and edition_title and edition_title != book.title
        else book.title
    )
    filtered_outline = filter_outline_by_chapters(book.outline, allowed_chapters)
    comp_pct = (
        compute_book_slice_completion(book, progress, allowed_chapters)
        if allowed_chapters
        else (int(progress.completion_pct or 0) if progress else 0)
    )
    return BookCatalogOut(
        id=book.id,
        slug=book.slug,
        title=display_title,
        title_ar=title_ar_override or book.title_ar,
        subtitle=book.subtitle,
        author_name=book.author_name,
        cover_url=await books_storage.resolve_book_cover_url(book.cover_bucket, book.cover_path),
        cover_page_url=_cover_page_url(book),
        languages=list(book.languages or ["en"]),
        access_mode=book.access_mode,
        price_cents=book.price_cents,
        currency=book.currency,
        enrolled=enrolled,
        is_preview=is_preview,
        completion_pct=comp_pct,
        stars_earned=int(progress.stars_earned or 0) if progress else 0,
        stars_possible=int(progress.stars_possible or 0) if progress else 0,
        chapter_count=len(filtered_outline),
        edition_id=edition_id,
        item_id=item_id,
        edition_title=edition_title,
        allowed_chapters=allowed_chapters,
        locked_scope=locked_scope,
    )


async def _book_detail_out(
    book: LmsBook,
    *,
    enrolled: bool,
    is_preview: bool,
    progress: LmsBookProgress | None,
    edition_id: uuid.UUID | None = None,
    edition_title: str | None = None,
    title_ar_override: str | None = None,
    allowed_chapters: list[str] | None = None,
    locked_scope: bool = False,
    editions: list[dict[str, Any]] | None = None,
) -> BookDetailOut:
    cat = await _book_catalog_out(
        book,
        enrolled=enrolled,
        is_preview=is_preview,
        progress=progress,
        edition_id=edition_id,
        edition_title=edition_title,
        title_ar_override=title_ar_override,
        allowed_chapters=allowed_chapters,
        locked_scope=locked_scope,
    )
    filtered_outline = filter_outline_by_chapters(book.outline, allowed_chapters)
    prog_out = _progress_out(progress)
    if prog_out is not None and allowed_chapters:
        prog_out.completion_pct = cat.completion_pct
    return BookDetailOut(
        **cat.model_dump(),
        description=book.description,
        access_days=book.access_days,
        bundle_version=int(book.bundle_version or 0),
        is_published=book.is_published,
        default_profile=book.default_profile or "all",
        outline=filtered_outline,
        profiles=[] if locked_scope else (book.profiles or []),
        editions=[] if locked_scope else (editions or []),
        progress=prog_out,
    )


# ── Public / Student Catalog & Detail ────────────────────────────────────────

@router.get("/lms/books/public", response_model=list[BookCatalogOut])
async def list_public_books(
    q: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(LmsBook).where(LmsBook.is_published.is_(True), LmsBook.access_mode != "invite")
    if q and q.strip():
        pat = f"%{q.strip()}%"
        stmt = stmt.where(or_(LmsBook.title.ilike(pat), LmsBook.subtitle.ilike(pat), LmsBook.description.ilike(pat)))
    rows = (await db.execute(stmt.order_by(LmsBook.created_at.desc()))).scalars().all()
    return [await _book_catalog_out(b, enrolled=False, is_preview=False, progress=None) for b in rows]


@router.get("/lms/books/public/{book_id}", response_model=BookDetailOut)
async def get_public_book_detail(
    book_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    book = await db.get(LmsBook, book_id)
    if book is None or not book.is_published or book.access_mode == "invite":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")
    return await _book_detail_out(book, enrolled=False, is_preview=False, progress=None)


@router.get("/lms/books/public/{book_id}/cover-page")
async def get_book_cover_page(
    book_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Serve the book's extracted first/cover page HTML so every book renders its real cover by default."""
    book = await db.get(LmsBook, book_id)
    if book is None or not book.is_published or int(book.bundle_version or 0) <= 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book cover page not available")
    try:
        html_str = await get_book_cover_page_html(book)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book cover page not found")
    return Response(
        content=html_str,
        media_type="text/html; charset=utf-8",
        headers={
            "Cache-Control": "public, max-age=3600",
            "X-Content-Type-Options": "nosniff",
        },
    )


async def _resolve_slice_selection(
    db: AsyncSession,
    *,
    book: LmsBook,
    current: User,
    has_full: bool,
    slices: list[dict[str, Any]],
    edition_id: uuid.UUID | None,
    item_id: uuid.UUID | None,
) -> tuple[list[str] | None, uuid.UUID | None, str | None, str | None, bool]:
    """Resolve `(allowed_chapters, edition_id, edition_title, title_ar, locked_scope)`."""
    if not has_full:
        if not slices:
            return None, None, None, None, False
        chosen = None
        if edition_id is not None:
            chosen = next((s for s in slices if s.get("edition_id") == edition_id), None)
            if chosen is None:
                raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You do not have access to this book edition")
        elif item_id is not None:
            item = await db.get(LmsProgramItem, item_id)
            if item is not None and item.book_id == book.id:
                ch_keys, ed = await resolve_item_chapters(
                    db,
                    book,
                    book_chapters=getattr(item, "book_chapters", None),
                    book_edition_id=getattr(item, "book_edition_id", None),
                    book_chapter=item.book_chapter,
                    book_profile=item.book_profile,
                )
                ed_id = ed.id if ed else None
                chosen = next(
                    (s for s in slices if s.get("edition_id") == ed_id and s.get("chapter_keys") == (ch_keys or [])),
                    None,
                )
        if chosen is None:
            chosen = slices[0]
        return (
            chosen["chapter_keys"],
            chosen.get("edition_id"),
            chosen.get("title"),
            chosen.get("title_ar"),
            True,
        )

    # User has full book access — apply explicit preview edition / item filter if provided
    if edition_id is not None:
        ed = await db.get(LmsBookEdition, edition_id)
        if ed is None or ed.book_id != book.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book edition not found")
        if ed.organization_id is not None and not can_manage_master_books(current):
            org = await resolve_book_user_org(db, current)
            if org is None or ed.organization_id != org.id:
                raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You do not have access to this book edition")
        return list(ed.chapter_keys or []), ed.id, ed.title, ed.title_ar, True
    if item_id is not None:
        item = await db.get(LmsProgramItem, item_id)
        if item is not None and item.book_id == book.id:
            ch_keys, ed = await resolve_item_chapters(
                db,
                book,
                book_chapters=getattr(item, "book_chapters", None),
                book_edition_id=getattr(item, "book_edition_id", None),
                book_chapter=item.book_chapter,
                book_profile=item.book_profile,
            )
            if ed is not None and ed.organization_id is not None and not can_manage_master_books(current):
                org = await resolve_book_user_org(db, current)
                if org is None or ed.organization_id != org.id:
                    raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You do not have access to this book edition")
            if ch_keys:
                return (
                    ch_keys,
                    ed.id if ed else None,
                    ed.title if ed else item.title,
                    ed.title_ar if ed else None,
                    True,
                )
    return None, None, None, None, False


@router.get("/lms/books", response_model=list[BookCatalogOut])
async def list_student_books(
    q: str | None = None,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    is_staff_user = is_book_staff_preview(current)
    org = await resolve_book_user_org(db, current)
    stmt = select(LmsBook)
    if not is_staff_user:
        stmt = stmt.where(LmsBook.is_published.is_(True))
    if q and q.strip():
        pat = f"%{q.strip()}%"
        stmt = stmt.where(or_(LmsBook.title.ilike(pat), LmsBook.subtitle.ilike(pat), LmsBook.description.ilike(pat)))
    books = (await db.execute(stmt.order_by(LmsBook.created_at.desc()))).scalars().all()

    prog_rows = (
        await db.execute(select(LmsBookProgress).where(LmsBookProgress.user_id == current.id))
    ).scalars().all()
    prog_by_book = {p.book_id: p for p in prog_rows}

    enrolled_ids = set(
        (
            await db.execute(
                select(LmsBookEnrollment.book_id).where(
                    LmsBookEnrollment.user_id == current.id,
                    *book_enrollment_is_active(),
                )
            )
        ).scalars().all()
    )

    out: list[BookCatalogOut] = []
    for b in books:
        has_full, slices = await resolve_user_book_access(db, user=current, book=b)
        prog = prog_by_book.get(b.id)
        if slices and not has_full:
            for s in slices:
                out.append(
                    await _book_catalog_out(
                        b,
                        enrolled=True,
                        is_preview=False,
                        progress=prog,
                        edition_id=s.get("edition_id"),
                        item_id=s.get("item_id"),
                        edition_title=s.get("title"),
                        title_ar_override=s.get("title_ar"),
                        allowed_chapters=s["chapter_keys"],
                        locked_scope=True,
                    )
                )
            continue
        if not has_full and b.access_mode == "invite":
            continue
        if not has_full and org is not None:
            # Org accounts only see books explicitly permitted in their catalog or open marketplace
            if not await is_book_allowed_for_org(db, org, b) and b.access_mode == "invite":
                continue
        enrolled = b.id in enrolled_ids or (
            has_full and not is_staff_user and org is None
        )
        out.append(
            await _book_catalog_out(
                b,
                enrolled=enrolled,
                is_preview=(is_staff_user or (org is not None and await is_book_allowed_for_org(db, org, b)))
                and b.id not in enrolled_ids,
                progress=prog,
            )
        )
    return out


@router.get("/lms/books/{book_id}", response_model=BookDetailOut)
async def get_book_detail(
    book_id: uuid.UUID,
    edition_id: uuid.UUID | None = Query(default=None),
    item_id: uuid.UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    book = await db.get(LmsBook, book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")

    is_staff_user = is_book_staff_preview(current)
    has_full, slices = await resolve_user_book_access(db, user=current, book=book)

    if not is_staff_user:
        if not book.is_published:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")
        if book.access_mode == "invite" and not has_full and not slices:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")

    allowed_chapters, resolved_ed_id, resolved_ed_title, resolved_ar, locked_scope = await _resolve_slice_selection(
        db,
        book=book,
        current=current,
        has_full=has_full,
        slices=slices,
        edition_id=edition_id,
        item_id=item_id,
    )

    prog = (
        await db.execute(
            select(LmsBookProgress).where(
                LmsBookProgress.user_id == current.id,
                LmsBookProgress.book_id == book.id,
            )
        )
    ).scalars().first()

    org = await resolve_book_user_org(db, current)
    editions = (
        await visible_editions_for_book(db, book_id=book.id, current_user=current, org=org)
        if has_full
        else []
    )
    enrolled_row = await db.scalar(
        select(LmsBookEnrollment.id).where(
            LmsBookEnrollment.user_id == current.id,
            LmsBookEnrollment.book_id == book.id,
            *book_enrollment_is_active(),
        )
    )
    return await _book_detail_out(
        book,
        enrolled=bool(enrolled_row) or (has_full and not is_staff_user and org is None) or bool(slices),
        is_preview=(is_staff_user or org is not None) and not enrolled_row,
        progress=prog,
        edition_id=resolved_ed_id,
        edition_title=resolved_ed_title,
        title_ar_override=resolved_ar,
        allowed_chapters=allowed_chapters,
        locked_scope=locked_scope,
        editions=editions,
    )


@router.post("/lms/books/{book_id}/enroll", status_code=status.HTTP_200_OK)
async def enroll_in_book(
    book_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    book = await db.get(LmsBook, book_id)
    if book is None or not book.is_published:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")

    if await has_book_access(db, user=current, book=book):
        return {"enrolled": True}

    if book.access_mode == "invite":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="This book requires a program or invite code")
    if book.access_mode == "paid":
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, detail="Purchase required to access this book")

    await enroll_book(db, user_id=current.id, book_id=book.id, source="self")
    await db.commit()
    return {"enrolled": True}


# ── Reader Session, R2 Bundle Serving, Progress & Exercise Sync ──────────────

@router.post("/lms/books/{book_id}/reader-session", response_model=BookReaderSessionOut)
async def create_reader_session(
    book_id: uuid.UUID,
    profile: str | None = Query(default=None),
    chapter: str | None = Query(default=None),
    spread: str | None = Query(default=None),
    theme: str | None = Query(default=None),
    lang: str | None = Query(default=None),
    edition_id: uuid.UUID | None = Query(default=None),
    item_id: uuid.UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    book = await db.get(LmsBook, book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")
    if book.bundle_version <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Book bundle has not been uploaded yet")

    has_full, slices = await resolve_user_book_access(db, user=current, book=book)
    if not has_full and not slices:
        # Auto-enroll if open and published so opening "Read" on a free book feels effortless
        if book.is_published and book.access_mode == "open":
            await enroll_book(db, user_id=current.id, book_id=book.id, source="self")
            await db.commit()
            has_full = True
        else:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Enroll or purchase this book to read it")

    allowed_chapters, resolved_ed_id, resolved_ed_title, resolved_ar, locked_scope = await _resolve_slice_selection(
        db,
        book=book,
        current=current,
        has_full=has_full,
        slices=slices,
        edition_id=edition_id,
        item_id=item_id,
    )
    if allowed_chapters and chapter and chapter not in allowed_chapters:
        chapter = allowed_chapters[0]

    can_teacher = await user_has_teacher_mode(db, user=current, book=book)
    token = create_book_token(
        user_id=current.id,
        book_id=book.id,
        version=book.bundle_version,
        can_teacher=can_teacher,
        edition_id=resolved_ed_id,
        allowed_chapters=allowed_chapters,
    )
    prog = (
        await db.execute(
            select(LmsBookProgress).where(
                LmsBookProgress.user_id == current.id,
                LmsBookProgress.book_id == book.id,
            )
        )
    ).scalars().first()

    qs_dict: dict[str, str] = {}
    if profile and not locked_scope:
        qs_dict["profile"] = profile
    if chapter:
        qs_dict["chapter"] = chapter
    elif allowed_chapters:
        qs_dict["chapter"] = allowed_chapters[0]
    if spread and not locked_scope:
        qs_dict["spread"] = spread
    if theme in ("light", "dark"):
        qs_dict["theme"] = theme
    if lang in ("en", "ar"):
        qs_dict["lang"] = lang
    qs = f"?{urlencode(qs_dict)}" if qs_dict else ""

    bundle_url = f"/lms/books/read-bundle/{token}/{book.bundle_entry}{qs}"
    filtered_outline = filter_outline_by_chapters(book.outline, allowed_chapters)
    prog_out = _progress_out(prog)
    if prog_out is not None and allowed_chapters:
        prog_out.completion_pct = compute_book_slice_completion(book, prog, allowed_chapters)

    return BookReaderSessionOut(
        book_id=book.id,
        title=f"{book.title} — {resolved_ed_title}" if resolved_ed_title and resolved_ed_title != book.title else book.title,
        title_ar=resolved_ar or book.title_ar,
        bundle_version=book.bundle_version,
        token=token,
        bundle_url=bundle_url,
        can_teacher=can_teacher,
        default_profile=book.default_profile or "all",
        languages=list(book.languages or ["en"]),
        edition_id=resolved_ed_id,
        edition_title=resolved_ed_title,
        allowed_chapters=allowed_chapters,
        locked_scope=locked_scope,
        outline=filtered_outline,
        profiles=[] if locked_scope else (book.profiles or []),
        progress=prog_out,
    )


@router.get("/lms/books/read-bundle/{token}/{asset_path:path}")
async def serve_book_bundle_asset(
    token: str,
    asset_path: str,
    request: Request,
    profile: str | None = Query(default=None),
    chapter: str | None = Query(default=None),
    spread: str | None = Query(default=None),
    theme: str | None = Query(default=None),
    lang: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    try:
        claims = decode_book_token(token)
    except JWTError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Invalid or expired reader session")

    try:
        clean_asset = sanitize_relative_path(asset_path or "index.html")
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid asset path")

    # Serve shared SpacePoint runtime files (__sp_runtime__/reader.css, bridge.js, logo-white.png)
    if "__sp_runtime__/" in clean_asset:
        runtime_name = clean_asset.split("__sp_runtime__/", 1)[1]
        if runtime_name not in ("reader.css", "bridge.js", "logo-white.png"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Runtime asset not found")
        file_path = STATIC_BOOKS_DIR / runtime_name
        if not file_path.is_file():
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Runtime asset missing")
        data = file_path.read_bytes()
        ctype = (
            "text/css; charset=utf-8" if runtime_name.endswith(".css")
            else "application/javascript; charset=utf-8" if runtime_name.endswith(".js")
            else "image/png"
        )
        return Response(
            content=data,
            media_type=ctype,
            headers={"Cache-Control": "public, max-age=300"},
        )

    book_id = uuid.UUID(claims["book_id"])
    user_id = uuid.UUID(claims["sub"])
    version = int(claims["version"])
    can_teacher = bool(claims.get("can_teacher", False))

    book = await db.get(LmsBook, book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")

    try:
        raw_bytes = await books_storage.download_book_file(
            BOOK_BUNDLE_PREFIX,
            f"{book.id}/v{version}/{clean_asset}",
            backend=book.bundle_storage_backend,
        )
    except FileNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book asset not found")

    if clean_asset == book.bundle_entry or clean_asset.endswith("/" + book.bundle_entry):
        prog = (
            await db.execute(
                select(LmsBookProgress).where(
                    LmsBookProgress.user_id == user_id,
                    LmsBookProgress.book_id == book_id,
                )
            )
        ).scalars().first()
        allowed_chapters = claims.get("allowed_chapters")
        edition_id = claims.get("edition_id")
        edition_title = None
        if edition_id:
            try:
                ed = await db.get(LmsBookEdition, uuid.UUID(str(edition_id)))
                if ed is not None:
                    edition_title = ed.title
            except (ValueError, TypeError):
                pass
        initial_state = dict(prog.raw_state or {}) if prog else {}
        visited_spreads = list(prog.visited_spreads or []) if prog else []
        injected = inject_runtime_into_html(
            raw_bytes,
            book_id=str(book.id),
            user_id=str(user_id),
            version=version,
            can_teacher=can_teacher,
            initial_state=initial_state,
            visited_spreads=visited_spreads,
            start_spread=spread,
            start_chapter=chapter,
            start_profile=profile,
            start_theme=theme,
            start_lang=lang,
            allowed_chapters=allowed_chapters,
            locked_scope=bool(allowed_chapters),
            edition_id=edition_id,
            edition_title=edition_title,
        )
        return Response(
            content=injected,
            media_type="text/html; charset=utf-8",
            headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    ctype = mimetypes.guess_type(clean_asset)[0] or "application/octet-stream"
    if clean_asset.endswith(".html"):
        ctype = "text/html; charset=utf-8"
    elif clean_asset.endswith(".js"):
        ctype = "application/javascript; charset=utf-8"
    elif clean_asset.endswith(".css"):
        ctype = "text/css; charset=utf-8"

    etag = f'"{hashlib.sha256(raw_bytes).hexdigest()[:16]}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})

    return Response(
        content=raw_bytes,
        media_type=ctype,
        headers={
            "ETag": etag,
            "Cache-Control": "private, max-age=3600",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.put("/lms/books/{book_id}/progress", response_model=BookProgressOut)
async def put_book_progress(
    book_id: uuid.UUID,
    body: BookProgressSyncIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    book = await db.get(LmsBook, book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")
    if not await has_book_access(db, user=current, book=book):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Book access required")

    row = await sync_book_progress(db, user_id=current.id, book_id=book_id, body=body)
    await db.commit()
    return _progress_out(row)


@router.post("/lms/books/{book_id}/exercises", response_model=BookExerciseOut)
async def post_book_exercise(
    book_id: uuid.UUID,
    body: BookExerciseIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    book = await db.get(LmsBook, book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")
    if not await has_book_access(db, user=current, book=book):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Book access required")

    row = await upsert_book_exercise_response(db, user_id=current.id, book_id=book_id, body=body)
    await db.commit()
    return row


# ── Admin / Ops Book Authoring & Analytics ───────────────────────────────────

def _require_master_book_writer(current: User) -> None:
    if not can_manage_master_books(current):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Master book authoring is restricted to SpacePoint staff",
        )


async def _assert_admin_book_read(db: AsyncSession, current: User, book: LmsBook) -> Organization | None:
    if can_manage_master_books(current):
        return None
    org = await resolve_book_user_org(db, current)
    if org is None or not await is_book_allowed_for_org(db, org, book):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Book access is not enabled for your organization")
    return org


async def _assert_analytics_scope(
    db: AsyncSession,
    current: User,
    book: LmsBook,
    cohort_id: uuid.UUID | None,
) -> None:
    if can_manage_master_books(current):
        return
    await _assert_admin_book_read(db, current, book)
    if cohort_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Select one of your accessible cohorts to view book analytics",
        )
    from app.services.org_access import require_cohort_read_or_ops

    await require_cohort_read_or_ops(db, cohort_id, current)


async def _book_admin_out(
    db: AsyncSession,
    book: LmsBook,
    *,
    current_user: User,
    org: Organization | None = None,
) -> BookAdminOut:
    is_master = can_manage_master_books(current_user)
    enrollments_count = (
        int(
            await db.scalar(
                select(func.count(LmsBookEnrollment.id)).where(
                    LmsBookEnrollment.book_id == book.id,
                    LmsBookEnrollment.status == "active",
                )
            )
            or 0
        )
        if is_master
        else 0
    )
    prog_rows = (
        (await db.execute(select(LmsBookProgress).where(LmsBookProgress.book_id == book.id))).scalars().all()
        if is_master
        else []
    )
    active_readers = [p for p in prog_rows if (p.completion_pct or 0) > 0 or p.last_read_at is not None]
    avg_comp = round(sum(int(p.completion_pct or 0) for p in active_readers) / len(active_readers)) if active_readers else 0
    editions = await visible_editions_for_book(db, book_id=book.id, current_user=current_user, org=org)
    return BookAdminOut(
        id=book.id,
        slug=book.slug,
        title=book.title,
        title_ar=book.title_ar,
        subtitle=book.subtitle,
        description=book.description,
        author_name=book.author_name,
        cover_url=await books_storage.resolve_book_cover_url(book.cover_bucket, book.cover_path),
        cover_page_url=_cover_page_url(book),
        languages=list(book.languages or ["en"]),
        bundle_version=int(book.bundle_version or 0),
        bundle_entry=book.bundle_entry or "index.html",
        bundle_storage_backend=book.bundle_storage_backend,
        bundle_size_bytes=book.bundle_size_bytes,
        outline=book.outline or [],
        profiles=book.profiles or [],
        default_profile=book.default_profile or "all",
        access_mode=book.access_mode,
        access_days=book.access_days,
        price_cents=book.price_cents,
        currency=book.currency,
        is_published=book.is_published,
        can_manage_master=is_master,
        editions=editions,
        enrollments_count=enrollments_count,
        active_readers_count=len(active_readers),
        avg_completion_pct=avg_comp,
        created_at=book.created_at,
        updated_at=book.updated_at,
    )


@router.get("/lms/admin/books", response_model=list[BookAdminOut])
async def admin_list_books(
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    if can_manage_master_books(current):
        rows = (await db.execute(select(LmsBook).order_by(LmsBook.created_at.desc()))).scalars().all()
        return [await _book_admin_out(db, b, current_user=current) for b in rows]

    org = await resolve_book_user_org(db, current)
    if org is None:
        return []
    allowed_ids = await accessible_org_book_ids(db, org)
    stmt = select(LmsBook).where(LmsBook.is_published.is_(True))
    if allowed_ids is not None:
        if not allowed_ids:
            return []
        stmt = stmt.where(LmsBook.id.in_(allowed_ids))
    rows = (await db.execute(stmt.order_by(LmsBook.created_at.desc()))).scalars().all()
    return [await _book_admin_out(db, b, current_user=current, org=org) for b in rows]


@router.post("/lms/admin/books", response_model=BookAdminOut, status_code=status.HTTP_201_CREATED)
async def admin_create_book(
    body: BookCreateIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    _require_master_book_writer(current)
    slug = slugify_book(body.slug or body.title)
    existing = await db.scalar(select(LmsBook.id).where(LmsBook.slug == slug))
    if existing is not None:
        slug = f"{slug[:88]}-{uuid.uuid4().hex[:6]}"

    if body.access_mode == "paid" and (not body.price_cents or body.price_cents <= 0):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Paid books must specify a positive price")

    now = datetime.now(timezone.utc)
    book = LmsBook(
        id=uuid.uuid4(),
        slug=slug,
        title=body.title.strip(),
        title_ar=body.title_ar.strip() if body.title_ar else None,
        subtitle=body.subtitle.strip() if body.subtitle else None,
        description=body.description,
        author_name=body.author_name.strip() if body.author_name else None,
        languages=body.languages or ["en"],
        access_mode=body.access_mode,
        access_days=body.access_days,
        price_cents=body.price_cents,
        currency=(body.currency or "usd").lower(),
        default_profile=body.default_profile or "all",
        is_published=False,
        created_by=current.id,
        created_at=now,
        updated_at=now,
    )
    db.add(book)
    await db.commit()
    return await _book_admin_out(db, book, current_user=current)


@router.get("/lms/admin/books/{book_id}", response_model=BookAdminOut)
async def admin_get_book(
    book_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    book = await db.get(LmsBook, book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")
    org = await _assert_admin_book_read(db, current, book)
    return await _book_admin_out(db, book, current_user=current, org=org)


@router.patch("/lms/admin/books/{book_id}", response_model=BookAdminOut)
async def admin_update_book(
    book_id: uuid.UUID,
    body: BookUpdateIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    _require_master_book_writer(current)
    book = await db.get(LmsBook, book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")

    data = body.model_dump(exclude_unset=True)
    if "slug" in data and data["slug"]:
        clean_slug = slugify_book(data["slug"])
        clash = await db.scalar(select(LmsBook.id).where(LmsBook.slug == clean_slug, LmsBook.id != book.id))
        if clash is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Slug is already used by another book")
        data["slug"] = clean_slug
    if "currency" in data and data["currency"]:
        data["currency"] = data["currency"].lower()

    next_mode = data.get("access_mode", book.access_mode)
    next_price = data.get("price_cents", book.price_cents)
    if next_mode == "paid" and (not next_price or next_price <= 0):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Paid books must specify a positive price")

    for k, v in data.items():
        setattr(book, k, v)
    book.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return await _book_admin_out(db, book, current_user=current)


@router.post("/lms/admin/books/{book_id}/publish", response_model=BookAdminOut)
async def admin_publish_book(
    book_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    _require_master_book_writer(current)
    book = await db.get(LmsBook, book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")
    if int(book.bundle_version or 0) <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Upload a book bundle (.zip) before publishing")
    book.is_published = True
    book.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return await _book_admin_out(db, book, current_user=current)


@router.post("/lms/admin/books/{book_id}/unpublish", response_model=BookAdminOut)
async def admin_unpublish_book(
    book_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    _require_master_book_writer(current)
    book = await db.get(LmsBook, book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")
    book.is_published = False
    book.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return await _book_admin_out(db, book, current_user=current)


@router.delete("/lms/admin/books/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_book(
    book_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    _require_master_book_writer(current)
    book = await db.get(LmsBook, book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")
    in_program = await db.scalar(select(LmsProgramItem.id).where(LmsProgramItem.book_id == book.id).limit(1))
    if in_program is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Remove this book from LMS programs before deleting")
    await db.delete(book)
    await db.commit()


@router.post("/lms/admin/books/{book_id}/cover", response_model=BookAdminOut)
async def admin_upload_book_cover(
    book_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    _require_master_book_writer(current)
    book = await db.get(LmsBook, book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")
    ctype = (file.content_type or "").split(";")[0].strip().lower()
    if ctype not in _ALLOWED_COVER_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Cover must be PNG, JPEG, WebP, GIF, or SVG")
    data = await file.read()
    if not data or len(data) > _MAX_COVER_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Cover image must be between 1 byte and 10 MB")

    ext = mimetypes.guess_extension(ctype) or ".png"
    rel_path = f"{book.id}/cover-{uuid.uuid4().hex[:8]}{ext}"
    await books_storage.upload_book_file(BOOK_COVER_PREFIX, rel_path, data, ctype)
    book.cover_bucket = BOOK_COVER_PREFIX
    book.cover_path = rel_path
    book.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return await _book_admin_out(db, book, current_user=current)


@router.post("/lms/admin/books/{book_id}/bundle", response_model=BookBundleUploadOut)
async def admin_upload_book_bundle(
    book_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    _require_master_book_writer(current)
    book = await db.get(LmsBook, book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")
    data = await file.read()
    if len(data) > _MAX_BUNDLE_ZIP_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Zip archive exceeds 120 MB limit")

    result = await unpack_and_upload_book_zip(db, book=book, zip_bytes=data)
    await db.commit()
    return BookBundleUploadOut(**result)


# ── Book Custom Editions CRUD (SpacePoint Staff & Allowed Organizations) ─────

@router.get("/lms/admin/books/{book_id}/editions", response_model=list[BookEditionOut])
async def list_book_editions(
    book_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    book = await db.get(LmsBook, book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")
    org = await _assert_admin_book_read(db, current, book)
    return await visible_editions_for_book(db, book_id=book.id, current_user=current, org=org)


@router.post("/lms/admin/books/{book_id}/editions", response_model=BookEditionOut, status_code=status.HTTP_201_CREATED)
async def create_book_edition(
    book_id: uuid.UUID,
    body: BookEditionCreateIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    book = await db.get(LmsBook, book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")
    org = await _assert_admin_book_read(db, current, book)
    chapter_keys = validate_chapter_keys_for_book(book, body.chapter_keys)
    now = datetime.now(timezone.utc)
    edition = LmsBookEdition(
        id=uuid.uuid4(),
        book_id=book.id,
        organization_id=None if can_manage_master_books(current) else (org.id if org else None),
        created_by=current.id,
        title=body.title.strip(),
        title_ar=body.title_ar.strip() if body.title_ar else None,
        description=body.description.strip() if body.description else None,
        chapter_keys=chapter_keys,
        default_lang=body.default_lang.strip().lower() if body.default_lang else None,
        created_at=now,
        updated_at=now,
    )
    db.add(edition)
    await db.commit()
    await db.refresh(edition)
    return serialize_book_edition(edition, current_user=current, org=org, creator_name=current.full_name)


@router.patch("/lms/admin/books/{book_id}/editions/{edition_id}", response_model=BookEditionOut)
async def update_book_edition(
    book_id: uuid.UUID,
    edition_id: uuid.UUID,
    body: BookEditionUpdateIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    book = await db.get(LmsBook, book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")
    org = await _assert_admin_book_read(db, current, book)
    edition = await db.get(LmsBookEdition, edition_id)
    if edition is None or edition.book_id != book.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book edition not found")
    if not can_user_edit_edition(current, edition, org):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You do not have permission to edit this book edition")

    data = body.model_dump(exclude_unset=True)
    if "title" in data and data["title"] is not None:
        edition.title = data["title"].strip()
    if "title_ar" in data:
        edition.title_ar = data["title_ar"].strip() if data["title_ar"] else None
    if "description" in data:
        edition.description = data["description"].strip() if data["description"] else None
    if "chapter_keys" in data and data["chapter_keys"] is not None:
        edition.chapter_keys = validate_chapter_keys_for_book(book, data["chapter_keys"])
    if "default_lang" in data:
        edition.default_lang = data["default_lang"].strip().lower() if data["default_lang"] else None
    edition.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(edition)
    creator = await db.get(User, edition.created_by) if edition.created_by else None
    return serialize_book_edition(
        edition,
        current_user=current,
        org=org,
        creator_name=creator.full_name if creator else None,
    )


@router.delete("/lms/admin/books/{book_id}/editions/{edition_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_book_edition(
    book_id: uuid.UUID,
    edition_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    book = await db.get(LmsBook, book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")
    org = await _assert_admin_book_read(db, current, book)
    edition = await db.get(LmsBookEdition, edition_id)
    if edition is None or edition.book_id != book.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book edition not found")
    if not can_user_edit_edition(current, edition, org):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You do not have permission to delete this book edition")

    used_in_item = await db.scalar(
        select(LmsProgramItem.id).where(LmsProgramItem.book_edition_id == edition.id).limit(1)
    )
    if used_in_item is not None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Remove this edition from LMS program checklists before deleting it",
        )
    used_in_grant = await db.scalar(
        select(InvitationCodeGrant.id).where(InvitationCodeGrant.book_edition_id == edition.id).limit(1)
    )
    if used_in_grant is not None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Remove this edition from invite code grants before deleting it",
        )
    await db.delete(edition)
    await db.commit()


@router.get("/lms/admin/books/{book_id}/enrollments", response_model=list[BookEnrollmentOut])
async def admin_list_book_enrollments(
    book_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    _require_master_book_writer(current)
    book = await db.get(LmsBook, book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")
    rows = (
        await db.execute(
            select(LmsBookEnrollment, User)
            .join(User, User.id == LmsBookEnrollment.user_id)
            .where(LmsBookEnrollment.book_id == book_id)
            .order_by(LmsBookEnrollment.created_at.desc())
        )
    ).all()
    prog_rows = (
        await db.execute(select(LmsBookProgress).where(LmsBookProgress.book_id == book_id))
    ).scalars().all()
    prog_map = {p.user_id: p for p in prog_rows}

    return [
        BookEnrollmentOut(
            id=enr.id,
            user_id=u.id,
            full_name=u.full_name,
            email=u.email,
            source=enr.source,
            status=enr.status,
            expires_at=enr.expires_at,
            completion_pct=int(prog_map[u.id].completion_pct or 0) if u.id in prog_map else 0,
            stars_earned=int(prog_map[u.id].stars_earned or 0) if u.id in prog_map else 0,
            last_read_at=prog_map[u.id].last_read_at if u.id in prog_map else None,
            created_at=enr.created_at,
        )
        for enr, u in rows
    ]


@router.post("/lms/admin/books/{book_id}/enrollments", response_model=BookEnrollmentOut, status_code=status.HTTP_201_CREATED)
async def admin_grant_book_enrollment(
    book_id: uuid.UUID,
    body: BookEnrollmentGrantIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    _require_master_book_writer(current)
    book = await db.get(LmsBook, book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")

    user: User | None = None
    if body.user_id is not None:
        user = await db.get(User, body.user_id)
    elif body.email and body.email.strip():
        user = (
            await db.execute(select(User).where(func.lower(User.email) == body.email.strip().lower()))
        ).scalars().first()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")

    enr = await enroll_book(db, user_id=user.id, book_id=book.id, source="ops", granted_by=current.id)
    await db.commit()
    prog = (
        await db.execute(
            select(LmsBookProgress).where(LmsBookProgress.user_id == user.id, LmsBookProgress.book_id == book.id)
        )
    ).scalars().first()
    return BookEnrollmentOut(
        id=enr.id,
        user_id=user.id,
        full_name=user.full_name,
        email=user.email,
        source=enr.source,
        status=enr.status,
        expires_at=enr.expires_at,
        completion_pct=int(prog.completion_pct or 0) if prog else 0,
        stars_earned=int(prog.stars_earned or 0) if prog else 0,
        last_read_at=prog.last_read_at if prog else None,
        created_at=enr.created_at,
    )


@router.post("/lms/admin/books/{book_id}/enrollments/bulk", response_model=BookBulkGrantOut)
async def admin_bulk_grant_book_enrollment(
    book_id: uuid.UUID,
    body: BookBulkGrantIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    _require_master_book_writer(current)
    book = await db.get(LmsBook, book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")

    user_ids = list(
        (await db.execute(select(User.id).where(User.roles.any(body.role)))).scalars().all()
    )
    now = datetime.now(timezone.utc)
    granted = already_enrolled = 0
    for uid in user_ids:
        existing = (
            await db.execute(
                select(LmsBookEnrollment.id).where(
                    LmsBookEnrollment.book_id == book.id,
                    LmsBookEnrollment.user_id == uid,
                    LmsBookEnrollment.status == "active",
                    or_(LmsBookEnrollment.expires_at.is_(None), LmsBookEnrollment.expires_at > now),
                )
            )
        ).first()
        if existing is not None:
            already_enrolled += 1
            continue
        await enroll_book(db, user_id=uid, book_id=book.id, source="ops", granted_by=current.id)
        granted += 1

    await db.commit()
    return BookBulkGrantOut(granted=granted, already_enrolled=already_enrolled)


@router.delete("/lms/admin/books/{book_id}/enrollments/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_revoke_book_enrollment(
    book_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    _require_master_book_writer(current)
    enr = (
        await db.execute(
            select(LmsBookEnrollment).where(
                LmsBookEnrollment.book_id == book_id,
                LmsBookEnrollment.user_id == user_id,
            )
        )
    ).scalars().first()
    if enr is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Enrollment not found")
    enr.status = "inactive"
    await db.commit()


@router.get("/lms/admin/books/{book_id}/analytics", response_model=BookAnalyticsOut)
async def admin_get_book_analytics(
    book_id: uuid.UUID,
    cohort_id: uuid.UUID | None = Query(default=None),
    edition_id: uuid.UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    book = await db.get(LmsBook, book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")
    await _assert_analytics_scope(db, current, book, cohort_id)
    data = await book_analytics(db, book_id=book_id, cohort_id=cohort_id, edition_id=edition_id)
    return BookAnalyticsOut(**data)


@router.get("/lms/admin/books/{book_id}/analytics/export.csv")
async def admin_export_book_analytics_csv(
    book_id: uuid.UUID,
    cohort_id: uuid.UUID | None = Query(default=None),
    edition_id: uuid.UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    book = await db.get(LmsBook, book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")
    await _assert_analytics_scope(db, current, book, cohort_id)
    csv_text = await export_book_responses_csv(db, book_id=book_id, cohort_id=cohort_id, edition_id=edition_id)
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{book.slug}-responses.csv"',
        },
    )

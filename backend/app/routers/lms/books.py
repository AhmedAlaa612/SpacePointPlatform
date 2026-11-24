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
    LmsBookEnrollment,
    LmsBookExerciseResponse,
    LmsBookProgress,
)
from app.models.lms.program import LmsProgramItem
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
    book_analytics,
    book_enrollment_is_active,
    can_user_teacher_mode,
    enroll_book,
    export_book_responses_csv,
    get_book_cover_page_html,
    has_book_access,
    inject_runtime_into_html,
    instructor_program_book_ids,
    is_book_staff_preview,
    slugify_book,
    sync_book_progress,
    unpack_and_upload_book_zip,
    upsert_book_exercise_response,
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
) -> BookCatalogOut:
    return BookCatalogOut(
        id=book.id,
        slug=book.slug,
        title=book.title,
        title_ar=book.title_ar,
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
        completion_pct=int(progress.completion_pct or 0) if progress else 0,
        stars_earned=int(progress.stars_earned or 0) if progress else 0,
        stars_possible=int(progress.stars_possible or 0) if progress else 0,
        chapter_count=len(book.outline or []),
    )


async def _book_detail_out(
    book: LmsBook,
    *,
    enrolled: bool,
    is_preview: bool,
    progress: LmsBookProgress | None,
) -> BookDetailOut:
    cat = await _book_catalog_out(book, enrolled=enrolled, is_preview=is_preview, progress=progress)
    return BookDetailOut(
        **cat.model_dump(),
        description=book.description,
        access_days=book.access_days,
        bundle_version=int(book.bundle_version or 0),
        is_published=book.is_published,
        default_profile=book.default_profile or "all",
        outline=book.outline or [],
        profiles=book.profiles or [],
        progress=_progress_out(progress),
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


@router.get("/lms/books", response_model=list[BookCatalogOut])
async def list_student_books(
    q: str | None = None,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    is_staff_user = is_book_staff_preview(current)
    teaching_book_ids = await instructor_program_book_ids(db, user=current)
    stmt = select(LmsBook)
    if not is_staff_user:
        stmt = stmt.where(LmsBook.is_published.is_(True))
    if q and q.strip():
        pat = f"%{q.strip()}%"
        stmt = stmt.where(or_(LmsBook.title.ilike(pat), LmsBook.subtitle.ilike(pat), LmsBook.description.ilike(pat)))
    books = (await db.execute(stmt.order_by(LmsBook.created_at.desc()))).scalars().all()

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
    prog_rows = (
        await db.execute(select(LmsBookProgress).where(LmsBookProgress.user_id == current.id))
    ).scalars().all()
    prog_by_book = {p.book_id: p for p in prog_rows}

    out = []
    for b in books:
        enrolled = b.id in enrolled_ids
        in_teaching_cohort = b.id in teaching_book_ids
        if not is_staff_user and b.access_mode == "invite" and not enrolled and not in_teaching_cohort:
            continue
        out.append(
            await _book_catalog_out(
                b,
                enrolled=enrolled or in_teaching_cohort,
                is_preview=is_staff_user and not enrolled,
                progress=prog_by_book.get(b.id),
            )
        )
    return out


@router.get("/lms/books/{book_id}", response_model=BookDetailOut)
async def get_book_detail(
    book_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    book = await db.get(LmsBook, book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")

    is_staff_user = is_book_staff_preview(current)
    enrolled = bool(
        await db.scalar(
            select(LmsBookEnrollment.id).where(
                LmsBookEnrollment.user_id == current.id,
                LmsBookEnrollment.book_id == book.id,
                *book_enrollment_is_active(),
            )
        )
    )
    in_teaching_cohort = False
    if not is_staff_user and not enrolled:
        in_teaching_cohort = book.id in await instructor_program_book_ids(db, user=current)

    if not is_staff_user:
        if not book.is_published:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")
        if book.access_mode == "invite" and not enrolled and not in_teaching_cohort:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")

    prog = (
        await db.execute(
            select(LmsBookProgress).where(
                LmsBookProgress.user_id == current.id,
                LmsBookProgress.book_id == book.id,
            )
        )
    ).scalars().first()
    return await _book_detail_out(
        book,
        enrolled=enrolled or in_teaching_cohort,
        is_preview=is_staff_user and not enrolled,
        progress=prog,
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
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    book = await db.get(LmsBook, book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")
    if book.bundle_version <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Book bundle has not been uploaded yet")

    if not await has_book_access(db, user=current, book=book):
        # Auto-enroll if open and published so opening "Read" on a free book feels effortless
        if book.is_published and book.access_mode == "open":
            await enroll_book(db, user_id=current.id, book_id=book.id, source="self")
            await db.commit()
        else:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Enroll or purchase this book to read it")

    can_teacher = can_user_teacher_mode(current)
    token = create_book_token(
        user_id=current.id,
        book_id=book.id,
        version=book.bundle_version,
        can_teacher=can_teacher,
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
    if profile:
        qs_dict["profile"] = profile
    if chapter:
        qs_dict["chapter"] = chapter
    if spread:
        qs_dict["spread"] = spread
    if theme in ("light", "dark"):
        qs_dict["theme"] = theme
    if lang in ("en", "ar"):
        qs_dict["lang"] = lang
    qs = f"?{urlencode(qs_dict)}" if qs_dict else ""

    bundle_url = f"/lms/books/read-bundle/{token}/{book.bundle_entry}{qs}"

    return BookReaderSessionOut(
        book_id=book.id,
        title=book.title,
        title_ar=book.title_ar,
        bundle_version=book.bundle_version,
        token=token,
        bundle_url=bundle_url,
        can_teacher=can_teacher,
        default_profile=book.default_profile or "all",
        languages=list(book.languages or ["en"]),
        outline=book.outline or [],
        profiles=book.profiles or [],
        progress=_progress_out(prog),
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

async def _book_admin_out(db: AsyncSession, book: LmsBook) -> BookAdminOut:
    enrollments_count = int(
        await db.scalar(
            select(func.count(LmsBookEnrollment.id)).where(
                LmsBookEnrollment.book_id == book.id,
                LmsBookEnrollment.status == "active",
            )
        )
        or 0
    )
    prog_rows = (
        await db.execute(select(LmsBookProgress).where(LmsBookProgress.book_id == book.id))
    ).scalars().all()
    active_readers = [p for p in prog_rows if (p.completion_pct or 0) > 0 or p.last_read_at is not None]
    avg_comp = round(sum(int(p.completion_pct or 0) for p in active_readers) / len(active_readers)) if active_readers else 0
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
    rows = (await db.execute(select(LmsBook).order_by(LmsBook.created_at.desc()))).scalars().all()
    return [await _book_admin_out(db, b) for b in rows]


@router.post("/lms/admin/books", response_model=BookAdminOut, status_code=status.HTTP_201_CREATED)
async def admin_create_book(
    body: BookCreateIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
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
    return await _book_admin_out(db, book)


@router.get("/lms/admin/books/{book_id}", response_model=BookAdminOut)
async def admin_get_book(
    book_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    book = await db.get(LmsBook, book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")
    return await _book_admin_out(db, book)


@router.patch("/lms/admin/books/{book_id}", response_model=BookAdminOut)
async def admin_update_book(
    book_id: uuid.UUID,
    body: BookUpdateIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
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
    return await _book_admin_out(db, book)


@router.post("/lms/admin/books/{book_id}/publish", response_model=BookAdminOut)
async def admin_publish_book(
    book_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    book = await db.get(LmsBook, book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")
    if int(book.bundle_version or 0) <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Upload a book bundle (.zip) before publishing")
    book.is_published = True
    book.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return await _book_admin_out(db, book)


@router.post("/lms/admin/books/{book_id}/unpublish", response_model=BookAdminOut)
async def admin_unpublish_book(
    book_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    book = await db.get(LmsBook, book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")
    book.is_published = False
    book.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return await _book_admin_out(db, book)


@router.delete("/lms/admin/books/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_book(
    book_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
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
    return await _book_admin_out(db, book)


@router.post("/lms/admin/books/{book_id}/bundle", response_model=BookBundleUploadOut)
async def admin_upload_book_bundle(
    book_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    book = await db.get(LmsBook, book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")
    data = await file.read()
    if len(data) > _MAX_BUNDLE_ZIP_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Zip archive exceeds 120 MB limit")

    result = await unpack_and_upload_book_zip(db, book=book, zip_bytes=data)
    await db.commit()
    return BookBundleUploadOut(**result)


@router.get("/lms/admin/books/{book_id}/enrollments", response_model=list[BookEnrollmentOut])
async def admin_list_book_enrollments(
    book_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
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
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    book = await db.get(LmsBook, book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")
    data = await book_analytics(db, book_id=book_id, cohort_id=cohort_id)
    return BookAnalyticsOut(**data)


@router.get("/lms/admin/books/{book_id}/analytics/export.csv")
async def admin_export_book_analytics_csv(
    book_id: uuid.UUID,
    cohort_id: uuid.UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    book = await db.get(LmsBook, book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Book not found")
    csv_text = await export_book_responses_csv(db, book_id=book_id, cohort_id=cohort_id)
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{book.slug}-responses.csv"',
        },
    )

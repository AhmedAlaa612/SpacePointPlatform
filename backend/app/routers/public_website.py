"""Public website config endpoint — no auth required.

The marketing site (spacepoint-website) reads its global config here so
content editors never need a code deployment to update impact counters,
invite codes, contact info, or social links.
"""

import mimetypes
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.user import User
from app.models.website_config import WebsiteConfig
from app.models.website_program import WebsiteProgram
from app.schemas.website_config import WebsiteConfigOut
from app.schemas.website_program import WebsiteProgramOut

router = APIRouter(prefix="/public/website", tags=["public-website"])

_ALLOWED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".ico", ".avif",
    ".pdf", ".doc", ".docx", ".pptx", ".txt", ".csv", ".zip",
}
_MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB


def _uploads_dir() -> Path:
    d = Path(settings.STORAGE_ROOT).resolve() / "website_uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


async def _get_or_seed(db: AsyncSession) -> WebsiteConfig:
    row = (await db.execute(select(WebsiteConfig).where(WebsiteConfig.id == 1))).scalars().first()
    if row is None:
        row = WebsiteConfig(id=1)
        db.add(row)
        await db.commit()
        await db.refresh(row)
    elif row.contact_phone == "+971 4 000 0000" and not row.social_linkedin:
        row.students_count = "2,700+"
        row.workshops_count = "40+"
        row.partners_count = "25"
        row.contact_phone = "+971 56 298 7005"
        row.contact_whatsapp = "+971 56 298 7005"
        row.office_address = "Sharjah Research, Technology and Innovation Park (SRTIP), Block B – Office B22-120, Sharjah, United Arab Emirates"
        row.social_linkedin = "https://www.linkedin.com/company/spacepointae/posts/?feedView=all"
        row.social_x = "https://www.tiktok.com/@spacepoint.ae"
        row.social_instagram = "https://www.instagram.com/spacepoint.ae"
        row.social_youtube = row.social_youtube or ""
        await db.commit()
        await db.refresh(row)
    return row


@router.get("/config", response_model=WebsiteConfigOut)
async def get_public_website_config(db: AsyncSession = Depends(get_db)):
    row = await _get_or_seed(db)
    return row


@router.get("/programs", response_model=list[WebsiteProgramOut])
async def list_public_website_programs(db: AsyncSession = Depends(get_db)):
    """Published flagship programs ordered for display — no auth. Unseeded
    (fresh table, migration not yet run) reads as an empty list rather than
    a 500 so the marketing site's fallback content stays in charge."""
    try:
        rows = (
            await db.execute(
                select(WebsiteProgram)
                .where(WebsiteProgram.is_published.is_(True))
                .order_by(WebsiteProgram.display_order, WebsiteProgram.title)
            )
        ).scalars().all()
    except Exception:
        return []
    return rows


@router.post("/upload")
async def upload_website_asset(
    request: Request,
    file: UploadFile = File(...),
    _user: User = Depends(get_current_active_user),
):
    """Upload an image, icon, logo, or document (PDF/DOCX) for the public website
    and return a permanent public URL."""
    orig_name = file.filename or "upload"
    ext = Path(orig_name).suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext or 'unknown'}'. Allowed: images (PNG, JPG, WEBP, SVG, GIF) and documents (PDF, DOCX).",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 25 MB limit")

    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(orig_name).stem).strip("._-")[:40] or "asset"
    stored_name = f"{uuid.uuid4().hex[:12]}-{stem}{ext}"
    dest = _uploads_dir() / stored_name
    dest.write_bytes(data)

    cfg_base = (settings.BASE_URL or "").rstrip("/")
    base = cfg_base if cfg_base and cfg_base != "http://localhost:8000" else str(request.base_url).rstrip("/")
    return {
        "url": f"{base}/public/website/uploads/{stored_name}",
        "filename": orig_name,
    }


@router.get("/uploads/{filename}")
async def serve_website_upload(filename: str):
    """Serve an uploaded website asset publicly with long-lived caching."""
    if "/" in filename or "\\" in filename or filename in (".", ".."):
        raise HTTPException(status_code=404, detail="File not found")
    uploads_root = _uploads_dir()
    target = (uploads_root / filename).resolve()
    if not target.is_relative_to(uploads_root) or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return FileResponse(
        path=target,
        media_type=media_type,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=31536000, immutable",
        },
    )


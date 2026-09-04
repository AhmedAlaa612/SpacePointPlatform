"""LMS video routes (LM1-6) — upload (authoring) + token-gated stream (student).

Thin wrapper over the standardized `services/video_service.py`
(owner_type="module_item", owner_id=item_id) — this router owns the one
thing the shared service deliberately doesn't: the course-enrollment access
check, exactly as before.

Two surfaces:
- `POST /lms/admin/items/{item_id}/video` — `require_lms_content`, multipart
  upload of the source MP4, enqueues the transcode job.
- `GET /lms/items/{item_id}/video/token` — enrolled (P1-6/D2 — role no longer
  gates this) + ready, issues a short-lived token
  (core/security.py's `create_video_token`, now scoped to a `video_id`).
- `GET /lms/videos/{item_id}/playlist|segment/{name}|key` — token in the
  query string (the HLS-player convention; hls.js can't attach headers to
  segment/key fetches it makes itself). **Never a static URL** (D2): the
  playlist route rewrites the stored (token-agnostic) `.m3u8` so every
  segment/key line carries the same short-lived token, and every route
  re-validates the token AND the enrollment on every request.
"""

import re
import uuid
from datetime import timedelta
from pathlib import Path

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, require_lms_content
from app.core.security import create_video_token, decode_video_token
from app.db.session import get_db
from app.models.lms import CourseModule, ModuleItem
from app.models.user import User
from app.models.videos import Video
from app.routers.lms.student import _assert_enrolled
from app.services import storage
from app.services.video_service import HLS_BUCKET, attach_upload, enqueue_transcode, get_video_for_owner
from app.workers.settings import get_arq_redis

router = APIRouter(tags=["lms-video"])

MAX_UPLOAD_BYTES = 4 * 1024 * 1024 * 1024  # 4GB — platform-wide upload cap (PR #41)
# Must cover the longest lecture plus a mid-lesson pause — see create_video_token.
# Passed to create_video_token explicitly rather than relying on its default:
# this constant is what the client is *told* the expiry is, so if the two drift
# the player's refresh timing silently disagrees with reality.
_VIDEO_TOKEN_MINUTES = 4 * 60
# `%03d` in video_service.py is a *minimum* width — segment 1000 writes as
# "segment_1000.ts". A fixed \d{3} 404s on anything past segment 999 (66m36s
# at the 4s segment length), a hard mid-playback stop indistinguishable from a
# network failure (B1). The literal prefix/suffix/anchors are what block path
# traversal; the digit count was never carrying that weight.
_SEGMENT_NAME_RE = re.compile(r"^segment_\d{3,}\.ts$")


# ── admin: upload ────────────────────────────────────────────────────────

@router.post("/lms/admin/items/{item_id}/video", status_code=status.HTTP_202_ACCEPTED)
async def upload_video(
    item_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    arq_redis: ArqRedis | None = Depends(get_arq_redis),
    current: User = Depends(require_lms_content),
):
    item = await db.get(ModuleItem, item_id)
    if item is None or item.kind != "video":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Video item not found")

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Video exceeds the 4GB limit")
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Empty upload")

    video = await attach_upload(
        db, owner_type="module_item", owner_id=item_id, file_bytes=data, filename=file.filename or "video.mp4",
        content_type=file.content_type, mode="hls_encrypted", created_by=current.id,
    )
    dispatch = await enqueue_transcode(arq_redis, video.id)
    return {"item_id": str(item_id), "transcode_status": video.status, "dispatch": dispatch}


# ── student: token issuance ─────────────────────────────────────────────

@router.get("/lms/items/{item_id}/video/token")
async def issue_video_token(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    item = await db.get(ModuleItem, item_id)
    if item is None or item.kind != "video":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Video not found")
    course_module = await db.get(CourseModule, item.module_id)
    if course_module is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Video not found")
    await _assert_enrolled(db, current.id, course_module.course_id)

    video = await get_video_for_owner(db, owner_type="module_item", owner_id=item_id)
    if video is None or video.status != "ready":
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Video is not ready yet")

    token = create_video_token(
        current.id, video.id, expires_delta=timedelta(minutes=_VIDEO_TOKEN_MINUTES)
    )
    return {"token": token, "expires_in_seconds": _VIDEO_TOKEN_MINUTES * 60}


# ── stream: playlist / segment / key, token in query string ────────────

async def _video_from_token(db: AsyncSession, item_id: uuid.UUID, token: str) -> Video:
    try:
        user_id, video_id = decode_video_token(token)
    except JWTError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Invalid or expired token")

    item = await db.get(ModuleItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Video not found")
    course_module = await db.get(CourseModule, item.module_id)
    if course_module is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Video not found")
    await _assert_enrolled(db, uuid.UUID(user_id), course_module.course_id)

    video = await db.get(Video, uuid.UUID(video_id))
    if video is None or video.owner_type != "module_item":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Video not found")
    # A well-formed, unexpired token minted for a *different* item's video —
    # distinct from "no video at all" (404) so a valid token never leaks
    # which of the two is actually true.
    if video.owner_id != item_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Token does not match this video")
    if video.status != "ready":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Video not found")
    return video


def _rewrite_playlist(raw: bytes, item_id: uuid.UUID, token: str) -> bytes:
    """Stored playlists carry plain relative filenames (token-agnostic — one
    file serves every viewer). Rewritten per-request so every segment/key
    reference carries *this* request's short-lived token (D2: never a static
    URL).

    URLs here are relative (no leading slash) rather than absolute paths —
    the browser resolves them against wherever it fetched *this* playlist
    from, so whatever reverse-proxy prefix got it there (e.g. nginx's
    `/api/`, present in production, absent in local dev where the backend is
    hit directly) carries through automatically. An absolute `/lms/videos/…`
    path bypasses that prefix entirely — invisible in dev, breaks every
    segment/key fetch in prod (they resolve to the site root, land in the
    SPA's catch-all route, and hls.js fails trying to parse HTML as media)."""
    key_line = re.compile(r'URI="[^"]*"')
    lines = raw.decode("utf-8").splitlines()
    out = []
    for line in lines:
        if line.startswith("#EXT-X-KEY"):
            out.append(key_line.sub(f'URI="key?token={token}"', line))
        elif line and not line.startswith("#"):
            out.append(f"segment/{line}?token={token}")
        else:
            out.append(line)
    return ("\n".join(out) + "\n").encode("utf-8")


@router.get("/lms/videos/{item_id}/playlist")
async def get_playlist(
    item_id: uuid.UUID, token: str = Query(...), db: AsyncSession = Depends(get_db),
):
    video = await _video_from_token(db, item_id, token)
    raw = await storage.download_file(HLS_BUCKET, video.playlist_path)
    return Response(content=_rewrite_playlist(raw, item_id, token), media_type="application/vnd.apple.mpegurl")


@router.get("/lms/videos/{item_id}/segment/{segment_name}")
async def get_segment(
    item_id: uuid.UUID, segment_name: str, token: str = Query(...), db: AsyncSession = Depends(get_db),
):
    if not _SEGMENT_NAME_RE.match(segment_name):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Segment not found")
    video = await _video_from_token(db, item_id, token)
    # Derived from playlist_path's own directory, not video.id — a video
    # backfilled from the old ModuleVideo table keeps its original
    # item_id-prefixed storage layout (playlist_path/key_path copied
    # verbatim by the migration), which doesn't equal this row's new,
    # freshly-generated id. A video transcoded post-migration has
    # playlist_path == f"{video.id}/playlist.m3u8", so this still resolves
    # correctly there too.
    prefix = video.playlist_path.rsplit("/", 1)[0]
    data = await storage.download_file(HLS_BUCKET, f"{prefix}/{segment_name}")
    return Response(content=data, media_type="video/mp2t")


@router.get("/lms/videos/{item_id}/key")
async def get_key(
    item_id: uuid.UUID, token: str = Query(...), db: AsyncSession = Depends(get_db),
):
    video = await _video_from_token(db, item_id, token)
    data = await storage.download_file(HLS_BUCKET, video.key_path)
    return Response(content=data, media_type="application/octet-stream")

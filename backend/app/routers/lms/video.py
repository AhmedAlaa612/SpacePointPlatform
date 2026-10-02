"""LMS video upload (LM1-6, authoring only).

Thin wrapper over the standardized `services/video_service.py`
(owner_type="module_item", owner_id=item_id) — enqueues the transcode job
after attaching the upload.

Playback (token issuance + playlist/segment/key streaming) has moved to
`routers/video.py`'s generic, owner-type-agnostic surface — that router's
mechanics were always identical across every feature; only the access check
varied, and it now lives there as `_check_module_item`. See that module's
docstring. The frontend must call `/videos/{video_id}/token` and
`/videos/{video_id}/playlist|segment/{name}|key` instead of the old
`/lms/items/{item_id}/video/token` and `/lms/videos/{item_id}/...` paths.
"""

import uuid

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_lms_content
from app.db.session import get_db
from app.models.lms import ModuleItem
from app.models.user import User
from app.services.lms.author_access import check_item_access
from app.services.video_service import attach_upload, enqueue_transcode
from app.workers.settings import get_arq_redis

router = APIRouter(tags=["lms-video"])

MAX_UPLOAD_BYTES = 4 * 1024 * 1024 * 1024  # 4GB — platform-wide upload cap (PR #41)


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
    await check_item_access(db, current, item)

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

"""The standardized video service's ARQ job — replaces the LMS-only
`transcode_lms_video` (see `services/video_service.py`'s own docstring for
why the pipeline moved out of `services/lms/`)."""

import uuid

from app.db.session import AsyncSessionLocal
from app.services.video_service import run_encrypted_transcode


async def transcode_video(ctx, video_id: str, target_backend: str | None = None) -> dict:
    async with AsyncSessionLocal() as db:
        await run_encrypted_transcode(db, uuid.UUID(video_id), target_backend=target_backend)
    return {"video_id": video_id}

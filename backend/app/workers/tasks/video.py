"""The standardized video service's ARQ job — replaces the LMS-only
`transcode_lms_video` (see `services/video_service.py`'s own docstring for
why the pipeline moved out of `services/lms/`)."""

import uuid

from app.db.session import AsyncSessionLocal
from app.services.video_service import run_encrypted_transcode


async def transcode_video(ctx, video_id: str, target_backend: str | None = None) -> dict:
    """`target_backend` is where the HLS output should be written. The row is
    repointed there only after the encode succeeds, so a video that is already
    serving keeps serving from its current backend for the whole encode and
    swaps atomically at the end — or, if the encode fails, never swaps at all.
    Defaults to None, i.e. the VPS; pass "r2" to migrate a video as part of
    re-encoding it, which beats copying the old output across since that output
    is being replaced anyway."""
    async with AsyncSessionLocal() as db:
        await run_encrypted_transcode(db, uuid.UUID(video_id), target_backend=target_backend)
    return {"video_id": video_id, "target_backend": target_backend}

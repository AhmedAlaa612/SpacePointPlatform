"""LMS video transcode job (LM1-6) — enqueued from the upload route
(routers/lms/video.py) via `safe_enqueue(..., "transcode_lms_video", item_id)`.
"""

import uuid

from app.db.session import AsyncSessionLocal
from app.services.lms.video import run_transcode


async def transcode_lms_video(ctx, item_id: str) -> dict:
    async with AsyncSessionLocal() as db:
        await run_transcode(db, uuid.UUID(item_id))
    return {"item_id": item_id}

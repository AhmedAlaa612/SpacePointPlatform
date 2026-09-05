import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.dependencies import require_instructor
from app.db.session import get_db
from app.models.instructors.training import TrainingModule, TrainingVideo, UserTrainingProgress
from app.models.user import User
from app.models.videos import Video
from app.schemas.instructors.training import TrainingModuleOut, TrainingVideoOut
from app.services import storage
from app.services.video_service import get_playback_info

router = APIRouter(prefix="/training", tags=["instructors-training"])


@router.get("/modules", response_model=list[TrainingModuleOut])
async def list_training(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_instructor)):
    modules = (await db.execute(select(TrainingModule).order_by(TrainingModule.sort_order))).scalars().all()
    videos = (await db.execute(
        select(TrainingVideo).where(TrainingVideo.module_id.in_([m.id for m in modules])).order_by(TrainingVideo.sort_order)
    )).scalars().all()
    progress = (await db.execute(
        select(UserTrainingProgress).where(
            UserTrainingProgress.user_id == current_user.id,
            UserTrainingProgress.video_id.in_([v.id for v in videos]),
        )
    )).scalars().all()
    completed_ids = {p.video_id for p in progress if p.is_completed}
    uploaded_video_rows = (await db.execute(
        select(Video.owner_id).where(
            Video.owner_type == "training_video", Video.owner_id.in_([v.id for v in videos]), Video.provider == "upload",
        )
    )).scalars().all()
    uploaded_ids = set(uploaded_video_rows)

    videos_by_module: dict[uuid.UUID, list] = {}
    for v in videos:
        videos_by_module.setdefault(v.module_id, []).append(v)

    return [
        TrainingModuleOut(
            id=m.id, title=m.title, description=m.description, sort_order=m.sort_order,
            videos=[
                TrainingVideoOut.from_orm_video(v, is_completed=v.id in completed_ids, video_uploaded=v.id in uploaded_ids)
                for v in videos_by_module.get(m.id, [])
            ],
        )
        for m in modules
    ]


@router.get("/videos/{video_id}/stream")
async def stream_video(
    video_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_instructor)
):
    video = (await db.execute(select(TrainingVideo).where(TrainingVideo.id == video_id))).scalars().first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    uploaded = (await db.execute(
        select(Video).where(Video.owner_type == "training_video", Video.owner_id == video_id, Video.provider == "upload")
    )).scalars().first()
    if uploaded is not None:
        info = await get_playback_info(db, uploaded)
        # video_info mirrors get_playback_info()'s shape exactly and is what
        # the frontend's shared <VideoPlayer> needs — `url` alone can't
        # represent an hls_encrypted video (there is no plain URL for one;
        # playback needs a token, fetched by the player off video_info.video_id).
        return {"url": info.get("url") or "", "video_info": info}
    return {"url": video.video_path, "video_info": None}


@router.get("/videos/{video_id}/pdf/url")
async def get_training_pdf_url(
    video_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_instructor)
):
    """Resolve-fresh, same posture as the facilitator-side authoring
    endpoint of the same name — never a baked-in signed URL on the row or in
    a list response."""
    video = (await db.execute(select(TrainingVideo).where(TrainingVideo.id == video_id))).scalars().first()
    if video is None or video.format != "PDF" or not video.pdf_path:
        raise HTTPException(status_code=404, detail="No PDF uploaded for this item yet")
    return {"url": await storage.get_signed_url("library-resources", video.pdf_path, expires_in=86400)}


@router.post("/videos/{video_id}/complete")
async def mark_video_complete(
    video_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_instructor)
):
    progress = (await db.execute(
        select(UserTrainingProgress).where(
            UserTrainingProgress.user_id == current_user.id, UserTrainingProgress.video_id == video_id
        )
    )).scalars().first()
    if not progress:
        progress = UserTrainingProgress(user_id=current_user.id, video_id=video_id)
        db.add(progress)
    progress.is_completed = True
    progress.completed_at = datetime.now(timezone.utc)
    await db.commit()
    return {"video_id": str(video_id), "is_completed": True}

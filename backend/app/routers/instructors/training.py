import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.dependencies import require_instructor
from app.db.session import get_db
from app.models.instructors.training import TrainingModule, TrainingVideo, UserTrainingProgress
from app.models.user import User
from app.schemas.instructors.training import TrainingModuleOut, TrainingVideoOut
from app.services import storage

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

    videos_by_module: dict[uuid.UUID, list] = {}
    for v in videos:
        videos_by_module.setdefault(v.module_id, []).append(v)

    return [
        TrainingModuleOut(
            id=m.id, title=m.title, description=m.description, sort_order=m.sort_order,
            videos=[
                TrainingVideoOut(
                    id=v.id, title=v.title, description=v.description, notes=v.notes,
                    sort_order=v.sort_order, is_completed=v.id in completed_ids,
                )
                for v in videos_by_module.get(m.id, [])
            ],
        )
        for m in modules
    ]


@router.get("/videos/{video_id}/stream")
async def stream_video(
    video_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_instructor)
):
    """Returns a short-lived signed URL — training-videos is a private bucket
    (PLAN gotcha #10), never a permanent/public link."""
    video = (await db.execute(select(TrainingVideo).where(TrainingVideo.id == video_id))).scalars().first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    try:
        signed_url = await storage.get_signed_url("training-videos", video.video_path, expires_in=3600)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Video file not found in storage") from exc
    return {"url": signed_url}


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

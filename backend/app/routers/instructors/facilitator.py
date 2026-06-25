import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.dependencies import require_facilitator
from app.db.session import get_db
from app.models.instructors.library import LibraryModule, LibraryResource
from app.models.instructors.training import TrainingModule, TrainingVideo
from app.models.user import User
from app.schemas.instructors.training import (
    LibraryModuleCreate,
    LibraryModuleOut,
    LibraryResourceOut,
    TrainingModuleCreate,
    TrainingModuleOut,
    TrainingVideoOut,
)
from app.services import storage

router = APIRouter(prefix="/facilitator", tags=["instructors-facilitator"])

# Reuses the training_modules/training_videos/library_modules/library_resources
# models from the instructor portal (3.3) — this is purely the write side,
# guarded by require_facilitator (not the source app's inline
# `if role not in [...]` pattern — see instructors/HANDOFF.md known bugs).


@router.get("/training/modules", response_model=list[TrainingModuleOut])
async def list_training(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_facilitator)):
    modules = (await db.execute(select(TrainingModule).order_by(TrainingModule.sort_order))).scalars().all()
    videos = (await db.execute(
        select(TrainingVideo).where(TrainingVideo.module_id.in_([m.id for m in modules])).order_by(TrainingVideo.sort_order)
    )).scalars().all()
    by_module: dict[uuid.UUID, list] = {}
    for v in videos:
        by_module.setdefault(v.module_id, []).append(v)
    return [
        TrainingModuleOut(
            id=m.id, title=m.title, description=m.description, sort_order=m.sort_order,
            videos=[TrainingVideoOut(id=v.id, title=v.title, description=v.description, notes=v.notes, sort_order=v.sort_order)
                    for v in by_module.get(m.id, [])],
        )
        for m in modules
    ]


@router.post("/training/modules", response_model=TrainingModuleOut, status_code=201)
async def create_training_module(
    body: TrainingModuleCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_facilitator)
):
    module = TrainingModule(**body.model_dump())
    db.add(module)
    await db.commit()
    await db.refresh(module)
    return TrainingModuleOut(id=module.id, title=module.title, description=module.description, sort_order=module.sort_order, videos=[])


@router.delete("/training/modules/{module_id}")
async def delete_training_module(
    module_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_facilitator)
):
    module = (await db.execute(select(TrainingModule).where(TrainingModule.id == module_id))).scalars().first()
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    videos = (await db.execute(select(TrainingVideo).where(TrainingVideo.module_id == module_id))).scalars().all()
    for v in videos:
        await storage.delete_file("training-videos", v.video_path)
    await db.delete(module)  # cascades to training_videos/user_training_progress
    await db.commit()
    return {"status": "deleted"}


@router.post("/training/videos", response_model=TrainingVideoOut, status_code=201)
async def upload_training_video(
    module_id: uuid.UUID,
    title: str,
    file: UploadFile,
    description: str | None = None,
    notes: str | None = None,
    sort_order: int = 1,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_facilitator),
):
    data = await file.read()
    path = f"{module_id}/{int(time.time())}_{file.filename}"
    await storage.upload_file("training-videos", path, data, file.content_type or "video/mp4")
    video = TrainingVideo(
        module_id=module_id, title=title, description=description, notes=notes,
        video_path=path, sort_order=sort_order,
    )
    db.add(video)
    await db.commit()
    await db.refresh(video)
    return TrainingVideoOut(
        id=video.id, title=video.title, description=video.description, notes=video.notes, sort_order=video.sort_order,
    )


@router.delete("/training/videos/{video_id}")
async def delete_training_video(
    video_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_facilitator)
):
    video = (await db.execute(select(TrainingVideo).where(TrainingVideo.id == video_id))).scalars().first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    await storage.delete_file("training-videos", video.video_path)
    await db.delete(video)
    await db.commit()
    return {"status": "deleted"}


@router.get("/library/modules", response_model=list[LibraryModuleOut])
async def list_library(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_facilitator)):
    modules = (await db.execute(select(LibraryModule).order_by(LibraryModule.created_at))).scalars().all()
    resources = (await db.execute(
        select(LibraryResource).where(LibraryResource.module_id.in_([m.id for m in modules]))
    )).scalars().all()
    by_module: dict[uuid.UUID, list] = {}
    for r in resources:
        by_module.setdefault(r.module_id, []).append(r)
    return [
        LibraryModuleOut(
            id=m.id, name=m.name, description=m.description,
            resources=[LibraryResourceOut(id=r.id, title=r.title, description=r.description, format=r.format, file_url=r.file_url)
                       for r in by_module.get(m.id, [])],
        )
        for m in modules
    ]


@router.post("/library/modules", response_model=LibraryModuleOut, status_code=201)
async def create_library_module(
    body: LibraryModuleCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_facilitator)
):
    module = LibraryModule(**body.model_dump())
    db.add(module)
    await db.commit()
    await db.refresh(module)
    return LibraryModuleOut(id=module.id, name=module.name, description=module.description, resources=[])


@router.delete("/library/modules/{module_id}")
async def delete_library_module(
    module_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_facilitator)
):
    module = (await db.execute(select(LibraryModule).where(LibraryModule.id == module_id))).scalars().first()
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    resources = (await db.execute(select(LibraryResource).where(LibraryResource.module_id == module_id))).scalars().all()
    for r in resources:
        await storage.delete_file("library-resources", r.file_url.split("library-resources/")[-1].split("?")[0])
    await db.delete(module)
    await db.commit()
    return {"status": "deleted"}


@router.post("/library", response_model=LibraryResourceOut, status_code=201)
async def upload_library_resource(
    module_id: uuid.UUID,
    title: str,
    file: UploadFile,
    description: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_facilitator),
):
    data = await file.read()
    fmt = (file.filename or "").rsplit(".", 1)[-1].upper() if "." in (file.filename or "") else "FILE"
    path = f"{int(time.time())}_{file.filename}"
    file_url = await storage.upload_file("library-resources", path, data, file.content_type or "application/octet-stream")
    resource = LibraryResource(title=title, description=description, format=fmt, file_url=file_url, module_id=module_id)
    db.add(resource)
    await db.commit()
    await db.refresh(resource)
    return LibraryResourceOut(id=resource.id, title=resource.title, description=resource.description, format=resource.format, file_url=resource.file_url)


@router.delete("/library/{resource_id}")
async def delete_library_resource(
    resource_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_facilitator)
):
    resource = (await db.execute(select(LibraryResource).where(LibraryResource.id == resource_id))).scalars().first()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    await db.delete(resource)
    await db.commit()
    return {"status": "deleted"}

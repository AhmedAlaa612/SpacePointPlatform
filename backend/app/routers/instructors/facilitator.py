import time
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.dependencies import require_facilitator
from app.db.session import get_db
from app.models.instructors.checklist import ChecklistItem, ChecklistModule
from app.models.instructors.library import LibraryModule, LibraryResource
from app.models.instructors.payment import PortalSetting
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
from pydantic import BaseModel


class TrainingVideoCreate(BaseModel):
    module_id: uuid.UUID
    title: str
    url: str
    description: str | None = None
    notes: str | None = None
    sort_order: int = 1


# ── Application content ────────────────────────────────────────

_DEFAULT_VIDEO_URLS = [
    "https://youtu.be/6KcV1C1Ui5s",
    "https://youtu.be/qr1AvisQcV8",
    "https://youtu.be/5voQfQOTem8",
]
_DEFAULT_VIDEO_TITLES = ["Video 1", "Video 2", "Video 3"]


class AppVideoConfig(BaseModel):
    video_no: int
    title: str
    url: str


class AppVideosUpdate(BaseModel):
    videos: list[AppVideoConfig]


class AppModuleCreate(BaseModel):
    title: str
    sort_order: int = 1


class AppModuleUpdate(BaseModel):
    title: str | None = None
    sort_order: int | None = None


class AppItemCreate(BaseModel):
    title: str
    item_code: str
    description: str | None = None
    is_required: bool = True
    sort_order: int = 1


class AppItemUpdate(BaseModel):
    title: str | None = None
    item_code: str | None = None
    description: str | None = None
    is_required: bool | None = None
    sort_order: int | None = None


class AppItemOut(BaseModel):
    id: uuid.UUID
    module_id: uuid.UUID
    section_id: uuid.UUID | None
    item_code: str
    title: str
    description: str | None
    sort_order: int
    is_required: bool

    class Config:
        from_attributes = True


class AppModuleOut(BaseModel):
    id: uuid.UUID
    title: str
    sort_order: int
    created_at: datetime | None = None
    items: list[AppItemOut] = []

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
            videos=[TrainingVideoOut.from_orm_video(v) for v in by_module.get(m.id, [])],
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
    await db.delete(module)  # cascades to training_videos/user_training_progress
    await db.commit()
    return {"status": "deleted"}


@router.post("/training/videos", response_model=TrainingVideoOut, status_code=201)
async def add_training_video(
    body: TrainingVideoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_facilitator),
):
    video = TrainingVideo(
        module_id=body.module_id, title=body.title, description=body.description,
        notes=body.notes, video_path=body.url, sort_order=body.sort_order,
    )
    db.add(video)
    await db.commit()
    await db.refresh(video)
    return TrainingVideoOut.from_orm_video(video)


@router.patch("/training/videos/{video_id}", response_model=TrainingVideoOut)
async def update_training_video(
    video_id: uuid.UUID,
    title: str | None = None,
    url: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_facilitator),
):
    video = (await db.execute(select(TrainingVideo).where(TrainingVideo.id == video_id))).scalars().first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if title is not None:
        video.title = title
    if url is not None:
        video.video_path = url
    await db.commit()
    await db.refresh(video)
    return TrainingVideoOut.from_orm_video(video)


@router.delete("/training/videos/{video_id}")
async def delete_training_video(
    video_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_facilitator)
):
    video = (await db.execute(select(TrainingVideo).where(TrainingVideo.id == video_id))).scalars().first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    await db.delete(video)
    await db.commit()
    return {"status": "deleted"}


def _lib_storage_path(file_url: str) -> str:
    """Extract storage path from either a legacy full URL or a bare path."""
    if file_url.startswith("http"):
        return file_url.split("library-resources/")[-1].split("?")[0]
    return file_url


async def _lib_resolve_url(r: LibraryResource) -> str:
    """Return the URL to expose in API responses: signed URL for file resources, raw URL for links.
    NULL resource_type means a legacy row created before the column existed — treat as file."""
    if r.resource_type != "link":
        path = _lib_storage_path(r.file_url)
        if not path.startswith("http"):
            return await storage.get_signed_url("library-resources", path, expires_in=86400)
    return r.file_url


@router.get("/library/modules", response_model=list[LibraryModuleOut])
async def list_library(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_facilitator)):
    modules = (await db.execute(select(LibraryModule).order_by(LibraryModule.created_at))).scalars().all()
    resources = (await db.execute(
        select(LibraryResource).where(LibraryResource.module_id.in_([m.id for m in modules]))
    )).scalars().all()
    by_module: dict[uuid.UUID, list] = {}
    for r in resources:
        by_module.setdefault(r.module_id, []).append(r)
    result = []
    for m in modules:
        module_resources = []
        for r in by_module.get(m.id, []):
            module_resources.append(LibraryResourceOut(
                id=r.id, title=r.title, description=r.description, format=r.format,
                file_url=await _lib_resolve_url(r), resource_type=r.resource_type,
            ))
        result.append(LibraryModuleOut(id=m.id, name=m.name, description=m.description, resources=module_resources))
    return result


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
        if r.resource_type == "file":
            await storage.delete_file("library-resources", _lib_storage_path(r.file_url))
    await db.delete(module)
    await db.commit()
    return {"status": "deleted"}


@router.post("/library/link", response_model=LibraryResourceOut, status_code=201)
async def add_library_link(
    module_id: uuid.UUID,
    title: str,
    url: str,
    description: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_facilitator),
):
    resource = LibraryResource(
        title=title, description=description, format="LINK", file_url=url,
        module_id=module_id, resource_type="link",
    )
    db.add(resource)
    await db.commit()
    await db.refresh(resource)
    return LibraryResourceOut(id=resource.id, title=resource.title, description=resource.description,
                              format=resource.format, file_url=resource.file_url,
                              resource_type=resource.resource_type)


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
    stored_path = await storage.upload_to_path("library-resources", path, data, file.content_type or "application/octet-stream")
    resource = LibraryResource(
        title=title, description=description, format=fmt, file_url=stored_path,
        module_id=module_id, resource_type="file",
    )
    db.add(resource)
    await db.commit()
    await db.refresh(resource)
    signed_url = await storage.get_signed_url("library-resources", stored_path, expires_in=86400)
    return LibraryResourceOut(id=resource.id, title=resource.title, description=resource.description,
                              format=resource.format, file_url=signed_url,
                              resource_type=resource.resource_type)


@router.patch("/library/{resource_id}", response_model=LibraryResourceOut)
async def update_library_resource(
    resource_id: uuid.UUID,
    title: str | None = None,
    url: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_facilitator),
):
    resource = (await db.execute(select(LibraryResource).where(LibraryResource.id == resource_id))).scalars().first()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    if title is not None:
        resource.title = title
    if url is not None and resource.resource_type == "link":
        resource.file_url = url
    await db.commit()
    await db.refresh(resource)
    resolved = await _lib_resolve_url(resource)
    return LibraryResourceOut(id=resource.id, title=resource.title, description=resource.description,
                              format=resource.format, file_url=resolved, resource_type=resource.resource_type)


@router.put("/library/{resource_id}/file", response_model=LibraryResourceOut)
async def replace_library_file(
    resource_id: uuid.UUID,
    file: UploadFile,
    title: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_facilitator),
):
    resource = (await db.execute(select(LibraryResource).where(LibraryResource.id == resource_id))).scalars().first()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    if resource.resource_type != "file":
        raise HTTPException(status_code=400, detail="Resource is not a file")
    old_path = _lib_storage_path(resource.file_url)
    data = await file.read()
    fmt = (file.filename or "").rsplit(".", 1)[-1].upper() if "." in (file.filename or "") else resource.format
    new_path = f"{int(time.time())}_{file.filename}"
    stored_path = await storage.upload_to_path("library-resources", new_path, data, file.content_type or "application/octet-stream")
    if old_path and not old_path.startswith("http"):
        await storage.delete_file("library-resources", old_path)
    resource.file_url = stored_path
    resource.format = fmt
    if title is not None:
        resource.title = title
    await db.commit()
    await db.refresh(resource)
    signed_url = await storage.get_signed_url("library-resources", stored_path, expires_in=86400)
    return LibraryResourceOut(id=resource.id, title=resource.title, description=resource.description,
                              format=resource.format, file_url=signed_url, resource_type=resource.resource_type)


@router.delete("/library/{resource_id}")
async def delete_library_resource(
    resource_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_facilitator)
):
    resource = (await db.execute(select(LibraryResource).where(LibraryResource.id == resource_id))).scalars().first()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    if resource.resource_type == "file":
        await storage.delete_file("library-resources", _lib_storage_path(resource.file_url))
    await db.delete(resource)
    await db.commit()
    return {"status": "deleted"}


# ── Application content: videos ────────────────────────────────

@router.get("/application/videos")
async def get_application_videos(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(require_facilitator)
):
    settings = {
        s.key: s.value
        for s in (await db.execute(
            select(PortalSetting).where(PortalSetting.key.like("app_video_%"))
        )).scalars().all()
    }
    return [
        {
            "video_no": n,
            "url": settings.get(f"app_video_{n}_url") or _DEFAULT_VIDEO_URLS[n - 1],
            "title": settings.get(f"app_video_{n}_title") or _DEFAULT_VIDEO_TITLES[n - 1],
        }
        for n in range(1, 4)
    ]


@router.put("/application/videos")
async def update_application_videos(
    body: AppVideosUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_facilitator),
):
    for v in body.videos:
        n = v.video_no
        for key, val in [(f"app_video_{n}_url", v.url), (f"app_video_{n}_title", v.title)]:
            existing = (await db.execute(select(PortalSetting).where(PortalSetting.key == key))).scalars().first()
            if existing:
                existing.value = val
            else:
                db.add(PortalSetting(key=key, value=val))
    await db.commit()
    return {"status": "updated"}


# ── Application content: checklist modules ─────────────────────

@router.get("/application/modules", response_model=list[AppModuleOut])
async def list_application_modules(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(require_facilitator)
):
    modules = (await db.execute(select(ChecklistModule).order_by(ChecklistModule.sort_order))).scalars().all()
    module_ids = [m.id for m in modules]
    items = (await db.execute(
        select(ChecklistItem).where(ChecklistItem.module_id.in_(module_ids)).order_by(ChecklistItem.sort_order)
    )).scalars().all()
    by_module: dict[uuid.UUID, list] = {}
    for it in items:
        by_module.setdefault(it.module_id, []).append(it)
    return [
        AppModuleOut(
            id=m.id,
            title=m.title,
            sort_order=m.sort_order,
            created_at=getattr(m, "created_at", None),
            items=[
                AppItemOut(
                    id=it.id, module_id=it.module_id, section_id=it.section_id,
                    item_code=it.item_code, title=it.title, description=it.description,
                    sort_order=it.sort_order, is_required=it.is_required,
                )
                for it in by_module.get(m.id, [])
            ],
        )
        for m in modules
    ]


@router.post("/application/modules", response_model=AppModuleOut, status_code=201)
async def create_application_module(
    body: AppModuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_facilitator),
):
    module = ChecklistModule(title=body.title, sort_order=body.sort_order)
    db.add(module)
    await db.commit()
    await db.refresh(module)
    return AppModuleOut(id=module.id, title=module.title, sort_order=module.sort_order, created_at=getattr(module, "created_at", None), items=[])


@router.put("/application/modules/{module_id}", response_model=AppModuleOut)
async def update_application_module(
    module_id: uuid.UUID,
    body: AppModuleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_facilitator),
):
    module = (await db.execute(select(ChecklistModule).where(ChecklistModule.id == module_id))).scalars().first()
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    if body.title is not None:
        module.title = body.title
    if body.sort_order is not None:
        module.sort_order = body.sort_order
    await db.commit()
    await db.refresh(module)
    return AppModuleOut(id=module.id, title=module.title, sort_order=module.sort_order, created_at=getattr(module, "created_at", None), items=[])


@router.delete("/application/modules/{module_id}")
async def delete_application_module(
    module_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_facilitator),
):
    module = (await db.execute(select(ChecklistModule).where(ChecklistModule.id == module_id))).scalars().first()
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    await db.delete(module)
    await db.commit()
    return {"status": "deleted"}


@router.post("/application/modules/{module_id}/items", response_model=AppItemOut, status_code=201)
async def create_application_item(
    module_id: uuid.UUID,
    body: AppItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_facilitator),
):
    module = (await db.execute(select(ChecklistModule).where(ChecklistModule.id == module_id))).scalars().first()
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    item = ChecklistItem(
        module_id=module_id, title=body.title, item_code=body.item_code,
        description=body.description, is_required=body.is_required, sort_order=body.sort_order,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return AppItemOut(
        id=item.id, module_id=item.module_id, section_id=item.section_id,
        item_code=item.item_code, title=item.title, description=item.description,
        sort_order=item.sort_order, is_required=item.is_required,
    )


@router.put("/application/items/{item_id}", response_model=AppItemOut)
async def update_application_item(
    item_id: uuid.UUID,
    body: AppItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_facilitator),
):
    item = (await db.execute(select(ChecklistItem).where(ChecklistItem.id == item_id))).scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(item, field, val)
    await db.commit()
    await db.refresh(item)
    return AppItemOut(
        id=item.id, module_id=item.module_id, section_id=item.section_id,
        item_code=item.item_code, title=item.title, description=item.description,
        sort_order=item.sort_order, is_required=item.is_required,
    )


@router.delete("/application/items/{item_id}")
async def delete_application_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_facilitator),
):
    item = (await db.execute(select(ChecklistItem).where(ChecklistItem.id == item_id))).scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    await db.delete(item)
    await db.commit()
    return {"status": "deleted"}

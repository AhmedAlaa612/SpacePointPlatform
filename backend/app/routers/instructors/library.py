import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.dependencies import require_instructor
from app.db.session import get_db
from app.models.instructors.library import LibraryModule, LibraryResource
from app.models.user import User
from app.schemas.instructors.training import LibraryModuleOut, LibraryResourceOut

router = APIRouter(prefix="/library", tags=["instructors-library"])


@router.get("", response_model=list[LibraryModuleOut])
async def list_library(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_instructor)):
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
            resources=[
                LibraryResourceOut(id=r.id, title=r.title, description=r.description, format=r.format, file_url=r.file_url)
                for r in by_module.get(m.id, [])
            ],
        )
        for m in modules
    ]

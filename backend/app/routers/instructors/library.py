import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.dependencies import require_instructor
from app.db.session import get_db
from app.models.instructors.library import LibraryModule, LibraryResource
from app.models.user import User
from app.schemas.instructors.training import LibraryModuleOut, LibraryResourceOut
from app.services import storage

router = APIRouter(prefix="/library", tags=["instructors-library"])


def _lib_storage_path(file_url: str) -> str:
    if file_url.startswith("http"):
        return file_url.split("library-resources/")[-1].split("?")[0]
    return file_url


@router.get("", response_model=list[LibraryModuleOut])
async def list_library(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_instructor)):
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
            path = _lib_storage_path(r.file_url)
            url = (await storage.get_signed_url("library-resources", path, expires_in=86400)
                   if (r.resource_type != "link" and not path.startswith("http")) else r.file_url)
            module_resources.append(LibraryResourceOut(
                id=r.id, title=r.title, description=r.description,
                format=r.format, file_url=url, resource_type=r.resource_type,
            ))
        result.append(LibraryModuleOut(id=m.id, name=m.name, description=m.description, resources=module_resources))
    return result

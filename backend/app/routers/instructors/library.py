import uuid

from fastapi import APIRouter, Depends, HTTPException, status
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


def _is_inline_pdf(resource: LibraryResource) -> bool:
    """A hosted (not linked-out) file whose format is PDF — the only shape
    `PdfViewer` on the frontend can actually render. Everything else (PPTX,
    other file formats, or a `link`-type resource pointing somewhere we
    don't host) still needs its real URL to be openable at all."""
    return resource.resource_type == "file" and resource.format.upper() == "PDF"


@router.get("", response_model=list[LibraryModuleOut])
async def list_library(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_instructor)):
    """Every hosted PDF's `file_url` comes back blank here — deliberately.
    Same posture as the LMS attachment viewer's signed URL (see
    `routers/lms/student.py::attachment_url`): never bake a downloadable
    link into a list payload an instructor's browser holds onto for the
    whole page visit. The frontend calls `GET /resources/{id}/url` instead,
    only once someone actually opens that document, and renders it through
    the same no-download canvas viewer rather than a clickable link.
    """
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
            if _is_inline_pdf(r):
                url = ""
            else:
                path = _lib_storage_path(r.file_url)
                url = (await storage.get_signed_url("library-resources", path, expires_in=86400)
                       if (r.resource_type != "link" and not path.startswith("http")) else r.file_url)
            module_resources.append(LibraryResourceOut(
                id=r.id, title=r.title, description=r.description,
                format=r.format, file_url=url, resource_type=r.resource_type,
            ))
        result.append(LibraryModuleOut(id=m.id, name=m.name, description=m.description, resources=module_resources))
    return result


@router.get("/resources/{resource_id}/url")
async def get_library_resource_url(
    resource_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_instructor),
) -> dict[str, str]:
    """Resolved only when someone actually opens a document — same posture
    as `streamVideoApi`/the LMS attachment viewer, never embedded in the
    list above for a hosted PDF."""
    resource = (await db.execute(select(LibraryResource).where(LibraryResource.id == resource_id))).scalars().first()
    if resource is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Resource not found")

    if resource.resource_type == "link" or resource.file_url.startswith("http"):
        return {"url": resource.file_url}

    path = _lib_storage_path(resource.file_url)
    url = await storage.get_signed_url("library-resources", path, expires_in=3600)
    return {"url": url}

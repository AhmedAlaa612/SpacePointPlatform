"""The shared CubeSat component library, editable (Design v2, 7D-7) —
`/missions/library/*`.

Madar had a full library manager: add, edit, retire, bulk-import from Excel
and upload images, all from the browser. The port shipped a read-only
`GET /missions/design/library` and nothing else, so adding or correcting a
component meant a developer editing `scripts/missions_seed_design.py` and
re-running it (`MISSIONS_MADAR_GAP.md` §2.2). That is a workflow
regression, not just a missing screen.

**Why this is not under `/missions/admin`.** That router carries a
router-level `require_lms_content` dependency — staff only. Under D7 a
design-mission manager may edit the library too, which is a different
population, so the check lives per-route here via
`require_design_library_editor`.

**Why this is not per-mission admin either.** `design_component_library`
has no `mission_id`; it is one global catalog every design mission reads.
It is reference data, like inventory — which is why it gets its own
`/lms-authoring` section rather than living inside one mission's page.

Two safeguards bound the risk D7 accepts:

1. **Retire, never delete.** There is no DELETE route at all. The RESTRICT
   FK from `design_components` already made deletion impossible for any
   component that has ever been used; this makes it a rule rather than a
   foreign-key error.
2. **Every write is attributed.** `updated_by`/`updated_at` are set on
   every mutation and returned in the list, so a bad edit is visible and
   reversible instead of anonymous.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.missions.design import DesignComponent, DesignComponentLibrary
from app.models.user import User
from app.schemas.missions_design import (
    LibraryBulkImportIn,
    LibraryBulkImportOut,
    LibraryComponentAdminOut,
    LibraryComponentCreateIn,
    LibraryComponentUpdateIn,
)
from app.services import storage
from app.services.missions.authorization import require_design_library_editor

router = APIRouter(prefix="/missions/library", tags=["missions-library"])

IMAGE_BUCKET = "mission-assets"


async def _out(db: AsyncSession, row: DesignComponentLibrary) -> LibraryComponentAdminOut:
    editor = await db.get(User, row.updated_by) if row.updated_by else None
    used_by = await db.scalar(
        select(func.count()).select_from(DesignComponent)
        .where(DesignComponent.library_component_id == row.id)
    )
    return LibraryComponentAdminOut(
        id=row.id, component_name=row.component_name, subsystem=row.subsystem, tag=row.tag,
        example_role=row.example_role, scaled_description=row.scaled_description,
        length_mm=row.length_mm, width_mm=row.width_mm, height_mm=row.height_mm,
        scaled_mass_g=row.scaled_mass_g, voltage_v=row.voltage_v, current_ma=row.current_ma,
        data_size=row.data_size, assumed_cost_usd=row.assumed_cost_usd,
        temperature_range=row.temperature_range, key_specs=row.key_specs,
        component_code=row.component_code, datasheet_url=row.datasheet_url, notes=row.notes,
        is_active=row.is_active,
        image_url=await storage.resolve_url(row.image_bucket, row.image_path),
        updated_at=row.updated_at, updated_by_name=editor.full_name if editor else None,
        used_in_designs=int(used_by or 0),
    )


def _touch(row: DesignComponentLibrary, user: User) -> None:
    row.updated_by = user.id
    row.updated_at = datetime.now(timezone.utc)


@router.get("", response_model=list[LibraryComponentAdminOut])
async def list_library(
    subsystem: str | None = None, search: str | None = None, include_retired: bool = True,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    """Unlike the student-facing `/missions/design/library`, this returns
    retired components too — you cannot un-retire something you cannot see."""
    await require_design_library_editor(db, user=current)
    query = select(DesignComponentLibrary)
    if not include_retired:
        query = query.where(DesignComponentLibrary.is_active.is_(True))
    if subsystem:
        query = query.where(DesignComponentLibrary.subsystem == subsystem)
    if search:
        like = f"%{search}%"
        query = query.where(or_(
            DesignComponentLibrary.component_name.ilike(like),
            DesignComponentLibrary.component_code.ilike(like),
        ))
    rows = (await db.execute(
        query.order_by(DesignComponentLibrary.subsystem, DesignComponentLibrary.component_name)
    )).scalars().all()
    return [await _out(db, r) for r in rows]


@router.post("", response_model=LibraryComponentAdminOut, status_code=status.HTTP_201_CREATED)
async def create_component(
    body: LibraryComponentCreateIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    await require_design_library_editor(db, user=current)
    row = DesignComponentLibrary(id=uuid.uuid4(), **body.model_dump(exclude_unset=True))
    _touch(row, current)
    db.add(row)
    await db.flush()
    result = await _out(db, row)
    await db.commit()
    return result


@router.patch("/{component_id}", response_model=LibraryComponentAdminOut)
async def update_component(
    component_id: uuid.UUID, body: LibraryComponentUpdateIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    """Edits are visible to every design mission — see the module docstring.
    Designs that already added this component keep their frozen snapshot
    (F2); a live in-progress design picks up the new value for any field
    its student has not overridden."""
    await require_design_library_editor(db, user=current)
    row = await db.get(DesignComponentLibrary, component_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Component not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    _touch(row, current)
    await db.flush()
    result = await _out(db, row)
    await db.commit()
    return result


@router.post("/{component_id}/retire", response_model=LibraryComponentAdminOut)
async def set_retired(
    component_id: uuid.UUID, retired: bool = True,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    """The only way to remove a component from the picker.

    There is deliberately no DELETE route. Madar had one, and it cascaded:
    deleting a component removed it from every student's design along with
    their budget entries (F1, rated Critical). Retiring hides it from new
    designs and touches nothing that already exists."""
    await require_design_library_editor(db, user=current)
    row = await db.get(DesignComponentLibrary, component_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Component not found")
    row.is_active = not retired
    _touch(row, current)
    await db.flush()
    result = await _out(db, row)
    await db.commit()
    return result


@router.post("/{component_id}/image", response_model=LibraryComponentAdminOut)
async def upload_component_image(
    component_id: uuid.UUID, file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    await require_design_library_editor(db, user=current)
    row = await db.get(DesignComponentLibrary, component_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Component not found")

    data = await file.read()
    if len(data) > 4 * 1024 * 1024:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Image must be under 4 MB")
    suffix = (file.filename or "img.png").rsplit(".", 1)[-1].lower()
    if suffix not in {"png", "jpg", "jpeg", "webp"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Image must be PNG, JPG or WebP")

    path = f"design-library/{component_id}.{suffix}"
    await storage.upload_to_path(IMAGE_BUCKET, path, data, file.content_type or "image/png")
    row.image_bucket, row.image_path = IMAGE_BUCKET, path
    _touch(row, current)
    await db.flush()
    result = await _out(db, row)
    await db.commit()
    return result


@router.post("/bulk", response_model=LibraryBulkImportOut)
async def bulk_import(
    body: LibraryBulkImportIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    """Bulk import, matched on `component_code` — Madar's Excel import,
    with the parsing moved to the browser.

    The frontend already ships `xlsx`, so it reads the spreadsheet and
    posts rows as JSON. That keeps a whole file-format dependency out of
    the backend and means a malformed sheet fails in the uploader's own
    browser, where they can see it, rather than as a 500.

    Rows without a `component_code` are inserted; rows whose code already
    exists are updated. Nothing is ever deleted by an import.
    """
    await require_design_library_editor(db, user=current)
    created = updated = 0
    errors: list[str] = []

    for i, item in enumerate(body.components, start=1):
        if not item.component_name or not item.subsystem:
            errors.append(f"Row {i}: component_name and subsystem are required")
            continue
        existing = None
        if item.component_code:
            existing = (await db.execute(select(DesignComponentLibrary).where(
                DesignComponentLibrary.component_code == item.component_code
            ))).scalars().first()
        if existing is not None:
            for field, value in item.model_dump(exclude_unset=True).items():
                setattr(existing, field, value)
            _touch(existing, current)
            updated += 1
        else:
            row = DesignComponentLibrary(id=uuid.uuid4(), **item.model_dump(exclude_unset=True))
            _touch(row, current)
            db.add(row)
            created += 1

    await db.flush()
    await db.commit()
    return LibraryBulkImportOut(created=created, updated=updated, errors=errors)

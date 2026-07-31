"""Materials, responsibilities and the payment bridge (I5-5 … I5-8).

    GET/POST/DELETE /sessions/materials…            program/cohort/session files+links
    GET            /sessions/{id}/materials         what resolves to this session
    GET/PUT        /sessions/responsibilities       the text ops maintains
    POST           /sessions/{id}/responsibilities/accept
    GET            /sessions/billable/{user_id}     unbilled completed sessions

**Materials are managed by ops, facilitators and admin** (operator's call), so
they use `require_materials_manager`. Reading what resolves to a session is
`require_session_delivery` — the instructor teaching it needs the files.
"""

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    require_materials_manager,
    require_operations,
    require_session_delivery,
)
from app.db.session import get_db
from app.models.sessions.instructor_interest import InstructorInterest
from app.models.sessions.material import Material
from app.models.user import User
from app.schemas.sessions.journey import (
    AcceptResponsibilitiesIn,
    MaterialLinkIn,
    MaterialOut,
    ResponsibilitiesIn,
    ResponsibilitiesOut,
    SessionMaterialsOut,
    UnbilledSessionOut,
)
from app.services.sessions import journey as svc
from app.services.sessions import materials as mat
from app.services.sessions.delivery import _get_deliverable_session

router = APIRouter(prefix="/sessions", tags=["sessions-journey"])


async def _out(material: Material) -> MaterialOut:
    return MaterialOut(
        id=material.id,
        program_id=material.program_id, cohort_id=material.cohort_id,
        session_id=material.session_id,
        title=material.title, notes=material.notes,
        url=await mat.material_url(material),
        filename=mat.display_filename(material.file_path) if material.file_path else None,
        sort_order=material.sort_order, created_at=material.created_at,
    )


# ── materials ───────────────────────────────────────────────────────────────

@router.get("/materials", response_model=list[MaterialOut])
async def list_materials(
    program_id: uuid.UUID | None = None,
    cohort_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_materials_manager),
):
    """Rows attached at exactly one level, with no inheritance applied — the
    management view. Ops editing a program must see the program's own rows."""
    rows = await mat.list_materials(
        db, program_id=program_id, cohort_id=cohort_id, session_id=session_id
    )
    return [await _out(m) for m in rows]


@router.post("/materials/link", response_model=MaterialOut, status_code=status.HTTP_201_CREATED)
async def add_material_link(
    body: MaterialLinkIn,
    program_id: uuid.UUID | None = None,
    cohort_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_materials_manager),
):
    material = await mat.add_material(
        db, user=current_user, title=body.title, url=body.url, notes=body.notes,
        program_id=program_id, cohort_id=cohort_id, session_id=session_id,
    )
    await db.commit()
    await db.refresh(material)
    return await _out(material)


@router.post("/materials/file", response_model=MaterialOut, status_code=status.HTTP_201_CREATED)
async def add_material_file(
    title: str = Form(...),
    notes: str | None = Form(None),
    program_id: uuid.UUID | None = Form(None),
    cohort_id: uuid.UUID | None = Form(None),
    session_id: uuid.UUID | None = Form(None),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_materials_manager),
):
    material = await mat.add_material(
        db, user=current_user, title=title, notes=notes,
        program_id=program_id, cohort_id=cohort_id, session_id=session_id,
        file_bytes=await file.read(), filename=file.filename,
        content_type=file.content_type,
    )
    await db.commit()
    await db.refresh(material)
    return await _out(material)


@router.delete("/materials/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_material(
    material_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_materials_manager),
):
    material = await db.get(Material, material_id)
    if material is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Material not found")
    await mat.delete_material(db, material)
    await db.commit()


@router.get("/{session_id}/materials", response_model=SessionMaterialsOut)
async def session_materials(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """Session's own materials, else the cohort's, else the program's —
    override, not merge. `level` says which, so "inherited from the program"
    is distinguishable from "this session has none"."""
    session = await _get_deliverable_session(db, session_id, current_user)
    rows, level = await mat.resolve_for_session(db, session)
    return SessionMaterialsOut(level=level, materials=[await _out(m) for m in rows])


# ── responsibilities ────────────────────────────────────────────────────────

@router.get("/responsibilities", response_model=ResponsibilitiesOut)
async def get_responsibilities(
    role_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_session_delivery),
):
    """The general text alone when `role_id` is omitted (the admin editor,
    and sessions with no configured openings). With `role_id`, the combined
    block an instructor actually reads and agrees to for that specific role."""
    if role_id is not None:
        text, version, role_name = await svc.get_responsibilities_for_role(db, role_id)
        return ResponsibilitiesOut(text=text, version=version, role_name=role_name)
    text, version = await svc.get_responsibilities(db)
    return ResponsibilitiesOut(text=text, version=version)


@router.put("/responsibilities", response_model=ResponsibilitiesOut)
async def put_responsibilities(
    body: ResponsibilitiesIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    text, version = await svc.set_responsibilities(db, body.text)
    await db.commit()
    return ResponsibilitiesOut(text=text, version=version)


@router.post("/{session_id}/responsibilities/accept", status_code=status.HTTP_204_NO_CONTENT)
async def accept_responsibilities(
    session_id: uuid.UUID,
    body: AcceptResponsibilitiesIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """Ticked when registering interest. Recorded against the version that was
    on screen — a stale one is refused, because otherwise somebody agrees to
    wording they never read."""
    interest = (await db.execute(
        select(InstructorInterest).where(
            InstructorInterest.session_id == session_id,
            InstructorInterest.user_id == current_user.id,
        )
    )).scalars().first()
    if interest is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Register interest in this session first"
        )
    await svc.accept_responsibilities(db, interest=interest, version=body.version)
    await db.commit()


# ── payment bridge ──────────────────────────────────────────────────────────

@router.get("/billable/{instructor_user_id}", response_model=list[UnbilledSessionOut])
async def billable_sessions(
    instructor_user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    """Completed sessions with no payment line yet, prefilled from real data.
    The amount is still typed — nothing here invents money."""
    return [UnbilledSessionOut(**row) for row in await svc.unbilled_sessions(db, instructor_user_id)]

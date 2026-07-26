"""Programs CRUD (V2 R2-3 — registration desk). No dedicated service module —
straightforward CRUD lives directly in the router, matching the established
convention for simple CRUD elsewhere (e.g. routers/instructors/admin.py's
invitation-code endpoints). Every route is gated by require_operations
(admin passes automatically — see core/dependencies.py's RequireRole).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_operations
from app.db.session import get_db
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.user import User
from app.schemas.sessions.programs import ProgramCreate, ProgramOut, ProgramUpdate

router = APIRouter(prefix="/sessions", tags=["sessions-programs"])


@router.get("/programs", response_model=list[ProgramOut])
async def list_programs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    rows = (await db.execute(select(Program).order_by(Program.created_at.desc()))).scalars().all()
    return rows


@router.post("/programs", response_model=ProgramOut, status_code=status.HTTP_201_CREATED)
async def create_program(
    body: ProgramCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    existing = (await db.execute(select(Program.id).where(Program.code == body.code))).first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="A program with this code already exists")

    program = Program(id=uuid.uuid4(), **body.model_dump())
    db.add(program)
    await db.commit()
    await db.refresh(program)
    return program


@router.get("/programs/{program_id}", response_model=ProgramOut)
async def get_program(
    program_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    program = await db.get(Program, program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program not found")
    return program


@router.patch("/programs/{program_id}", response_model=ProgramOut)
async def update_program(
    program_id: uuid.UUID,
    body: ProgramUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    program = await db.get(Program, program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program not found")

    changes = body.model_dump(exclude_unset=True)
    if "code" in changes and changes["code"] != program.code:
        existing = (await db.execute(select(Program.id).where(Program.code == changes["code"]))).first()
        if existing:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="A program with this code already exists")

    for field, value in changes.items():
        setattr(program, field, value)
    await db.commit()
    await db.refresh(program)
    return program


@router.delete("/programs/{program_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_program(
    program_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Only ever deletes an empty program.

    cohorts.program_id cascades, so an unguarded delete here would silently
    take every cohort, session, registration and attendance record with it.
    A program that has been run is history, not a mistake — deactivate it
    (PATCH active=false) instead, which keeps it out of the pickers.
    """
    program = await db.get(Program, program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program not found")

    cohort_count = await db.scalar(
        select(func.count()).select_from(Cohort).where(Cohort.program_id == program_id)
    )
    if cohort_count:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                f"This program has {cohort_count} cohort(s) and can't be deleted. "
                "Delete those first, or set the program to inactive to hide it."
            ),
        )

    await db.delete(program)
    await db.commit()

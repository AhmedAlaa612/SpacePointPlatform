from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi import HTTPException, status
from uuid import UUID

from app.models.interns.module import Module
from app.schemas.interns.module import ModuleCreate, ModuleUpdate


async def create_module(db: AsyncSession, epic_id: UUID, module_in: ModuleCreate, user_id: UUID) -> Module:
    module = Module(
        epic_id=epic_id,
        title=module_in.title,
        description=module_in.description,
        created_by=user_id,
    )
    db.add(module)
    await db.commit()
    await db.refresh(module)
    return module


async def get_module_by_id(db: AsyncSession, module_id: UUID) -> Module:
    result = await db.execute(select(Module).where(Module.id == module_id))
    module = result.scalars().first()
    if not module:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found")
    return module


async def update_module(db: AsyncSession, module_id: UUID, module_in: ModuleUpdate) -> Module:
    module = await get_module_by_id(db, module_id)
    for field, value in module_in.dict(exclude_unset=True).items():
        setattr(module, field, value)
    await db.commit()
    await db.refresh(module)
    return module


async def delete_module(db: AsyncSession, module_id: UUID):
    module = await get_module_by_id(db, module_id)
    await db.delete(module)
    await db.commit()
    return {"detail": "Module deleted"}

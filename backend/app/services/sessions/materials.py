"""Teaching materials across program → cohort → session (I5-6).

Operator decision, 2026-07-30: a program has materials, a cohort can override
them, and they can also be assigned to a single session. Managed by ops,
facilitators and admin; readable by whoever is assigned to deliver.

**Override, not merge.** The nearest level that has any rows wins outright.
Merging would make it impossible to *remove* a program-level file for one
cohort, which is exactly what "overridable" has to mean — the same reason
`Session.price` replaces `Program.price` rather than adding to it.
"""

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sessions.cohort import Cohort
from app.models.sessions.material import Material
from app.models.sessions.session import Session
from app.models.user import User
from app.services import storage

MATERIALS_BUCKET = "library-resources"


def display_filename(stored_path: str) -> str:
    """Stored as "{uuid4().hex}_{original}" — uuid4().hex is 32 hex chars with
    no underscore, so split recovers the original name intact."""
    return stored_path.split("_", 1)[1] if "_" in stored_path else stored_path


async def _rows(db: AsyncSession, **owner) -> list[Material]:
    field, value = next(iter(owner.items()))
    return (await db.execute(
        select(Material)
        .where(getattr(Material, field) == value)
        .order_by(Material.sort_order, Material.created_at)
    )).scalars().all()


async def list_materials(
    db: AsyncSession, *,
    program_id: uuid.UUID | None = None,
    cohort_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
) -> list[Material]:
    """Materials attached at exactly one level — no inheritance applied.
    This is the management view: ops editing a program's materials must see
    the program's own rows, not whatever a cohort inherited."""
    if program_id:
        return await _rows(db, program_id=program_id)
    if cohort_id:
        return await _rows(db, cohort_id=cohort_id)
    if session_id:
        return await _rows(db, session_id=session_id)
    return []


async def resolve_for_session(db: AsyncSession, session: Session) -> tuple[list[Material], str]:
    """What this session's instructor actually sees, and where it came from.

    Session's own rows if it has any, else the cohort's, else the program's.
    Returns the level too, so the UI can say "inherited from the program"
    rather than leaving ops guessing why editing the cohort changed nothing.
    """
    own = await _rows(db, session_id=session.id)
    if own:
        return own, "session"

    cohort = await db.get(Cohort, session.cohort_id)
    if cohort is None:
        return [], "none"

    at_cohort = await _rows(db, cohort_id=cohort.id)
    if at_cohort:
        return at_cohort, "cohort"

    at_program = await _rows(db, program_id=cohort.program_id)
    return (at_program, "program") if at_program else ([], "none")


async def add_material(
    db: AsyncSession,
    *,
    user: User,
    title: str,
    program_id: uuid.UUID | None = None,
    cohort_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    url: str | None = None,
    file_bytes: bytes | None = None,
    filename: str | None = None,
    content_type: str | None = None,
    notes: str | None = None,
) -> Material:
    """Attach a file or a link at one level. Never both — a row that is
    somehow both would leave every reader guessing which to open."""
    owners = [x for x in (program_id, cohort_id, session_id) if x is not None]
    if len(owners) != 1:
        raise HTTPException(400, detail="Attach a material to exactly one of program, cohort or session")

    title = (title or "").strip()
    if not title:
        raise HTTPException(400, detail="A material needs a title")

    if bool(url) == bool(file_bytes):
        raise HTTPException(400, detail="Give either a file or a link, not both")

    bucket = stored_path = None
    if file_bytes is not None:
        stored_path = f"{uuid.uuid4().hex}_{filename or 'material'}"
        bucket = MATERIALS_BUCKET
        await storage.upload_to_path(
            bucket, stored_path, file_bytes, content_type or "application/octet-stream"
        )

    material = Material(
        id=uuid.uuid4(),
        program_id=program_id, cohort_id=cohort_id, session_id=session_id,
        title=title, notes=notes,
        bucket=bucket, file_path=stored_path, url=url or None,
        uploaded_by=user.id,
    )
    db.add(material)
    await db.flush()
    return material


async def delete_material(db: AsyncSession, material: Material) -> None:
    """The storage object is deliberately left in place — the same choice
    `session_reports` makes. Orphaned bytes are cheap; a delete that half
    fails and loses a file is not."""
    await db.delete(material)
    await db.flush()


async def material_url(material: Material) -> str | None:
    if material.url:
        return material.url
    if material.file_path:
        return await storage.resolve_url(material.bucket or MATERIALS_BUCKET, material.file_path, None)
    return None

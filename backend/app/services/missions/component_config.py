"""Service layer for LMS Program and Cohort CubeSat component configuration."""

import uuid
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lms.program import LmsProgram
from app.models.missions.component_config import DesignComponentConfig
from app.models.missions.design import DesignComponentLibrary
from app.models.sessions.cohort import Cohort
from app.schemas.missions_component_config import ComponentConfigOut, ComponentItemSummary
from app.services import storage


async def get_raw_component_config(
    db: AsyncSession, owner_type: str, owner_id: UUID
) -> DesignComponentConfig | None:
    """Fetch raw DesignComponentConfig row for an owner ('program' or 'cohort')."""
    return (
        await db.execute(
            select(DesignComponentConfig).where(
                DesignComponentConfig.owner_type == owner_type,
                DesignComponentConfig.owner_id == owner_id,
            )
        )
    ).scalars().first()


async def resolve_effective_component_config(
    db: AsyncSession, *, cohort_id: UUID | None = None, lms_program_id: UUID | None = None
) -> tuple[dict, bool, bool]:
    """Resolve effective component configuration:
    Returns (config_dict, is_inherited, has_override).

    - If cohort_id is provided:
      1. Check cohort override in design_component_configs.
         If found -> return with is_inherited=False, has_override=True.
      2. If not found -> find cohort's LmsProgram -> check program config in design_component_configs.
         If found -> return with is_inherited=True, has_override=False.
      3. If neither has config -> return empty disabled lists with is_inherited=True, has_override=False.

    - If lms_program_id is provided:
      1. Check program config in design_component_configs.
         If found -> return with is_inherited=False, has_override=True.
      2. If not found -> return empty disabled lists with is_inherited=False, has_override=False.
    """
    if cohort_id is not None:
        cohort_cfg = await get_raw_component_config(db, "cohort", cohort_id)
        if cohort_cfg is not None:
            return (
                {
                    "disabled_subsystems": list(cohort_cfg.disabled_subsystems or []),
                    "disabled_tags": list(cohort_cfg.disabled_tags or []),
                    "disabled_component_ids": [UUID(str(x)) for x in (cohort_cfg.disabled_component_ids or [])],
                    "updated_at": cohort_cfg.updated_at,
                    "updated_by": cohort_cfg.updated_by,
                },
                False,
                True,
            )

        # Look up parent program
        cohort = await db.get(Cohort, cohort_id)
        prog_cfg = None
        if cohort and cohort.program_id:
            lms_prog = (
                await db.execute(
                    select(LmsProgram).where(LmsProgram.program_id == cohort.program_id)
                )
            ).scalars().first()
            if lms_prog is not None:
                prog_cfg = await get_raw_component_config(db, "program", lms_prog.id)

        if prog_cfg is not None:
            return (
                {
                    "disabled_subsystems": list(prog_cfg.disabled_subsystems or []),
                    "disabled_tags": list(prog_cfg.disabled_tags or []),
                    "disabled_component_ids": [UUID(str(x)) for x in (prog_cfg.disabled_component_ids or [])],
                    "updated_at": prog_cfg.updated_at,
                    "updated_by": prog_cfg.updated_by,
                },
                True,
                False,
            )

        return (
            {
                "disabled_subsystems": [],
                "disabled_tags": [],
                "disabled_component_ids": [],
                "updated_at": None,
                "updated_by": None,
            },
            True,
            False,
        )

    if lms_program_id is not None:
        prog_cfg = await get_raw_component_config(db, "program", lms_program_id)
        if prog_cfg is not None:
            return (
                {
                    "disabled_subsystems": list(prog_cfg.disabled_subsystems or []),
                    "disabled_tags": list(prog_cfg.disabled_tags or []),
                    "disabled_component_ids": [UUID(str(x)) for x in (prog_cfg.disabled_component_ids or [])],
                    "updated_at": prog_cfg.updated_at,
                    "updated_by": prog_cfg.updated_by,
                },
                False,
                True,
            )

        return (
            {
                "disabled_subsystems": [],
                "disabled_tags": [],
                "disabled_component_ids": [],
                "updated_at": None,
                "updated_by": None,
            },
            False,
            False,
        )

    return (
        {
            "disabled_subsystems": [],
            "disabled_tags": [],
            "disabled_component_ids": [],
            "updated_at": None,
            "updated_by": None,
        },
        False,
        False,
    )


async def save_component_config(
    db: AsyncSession,
    *,
    owner_type: str,
    owner_id: UUID,
    disabled_subsystems: list[str],
    disabled_tags: list[str],
    disabled_component_ids: list[UUID],
    user_id: UUID | None = None,
) -> DesignComponentConfig:
    """Create or update component config for a program or cohort."""
    cfg = await get_raw_component_config(db, owner_type, owner_id)
    subsystems_clean = sorted(list({s.strip() for s in disabled_subsystems if s.strip()}))
    tags_clean = sorted(list({t.strip() for t in disabled_tags if t.strip()}))
    cids_clean = sorted(list({str(cid) for cid in disabled_component_ids}))

    if cfg is None:
        cfg = DesignComponentConfig(
            id=uuid.uuid4(),
            owner_type=owner_type,
            owner_id=owner_id,
            disabled_subsystems=subsystems_clean,
            disabled_tags=tags_clean,
            disabled_component_ids=cids_clean,
            updated_by=user_id,
            updated_at=datetime.now(timezone.utc),
        )
        db.add(cfg)
    else:
        cfg.disabled_subsystems = subsystems_clean
        cfg.disabled_tags = tags_clean
        cfg.disabled_component_ids = cids_clean
        cfg.updated_by = user_id
        cfg.updated_at = datetime.now(timezone.utc)

    await db.flush()
    return cfg


async def reset_component_config(
    db: AsyncSession, *, owner_type: str, owner_id: UUID
) -> bool:
    """Delete component config row for an owner, restoring default or inherited state."""
    cfg = await get_raw_component_config(db, owner_type, owner_id)
    if cfg is not None:
        await db.delete(cfg)
        await db.flush()
        return True
    return False


async def build_component_config_out(
    db: AsyncSession, *, owner_type: str, owner_id: UUID
) -> ComponentConfigOut:
    """Build full ComponentConfigOut view model for authoring UI."""
    if owner_type == "cohort":
        config_dict, is_inherited, has_override = await resolve_effective_component_config(
            db, cohort_id=owner_id
        )
    else:
        config_dict, is_inherited, has_override = await resolve_effective_component_config(
            db, lms_program_id=owner_id
        )

    # Fetch all active library components
    query = select(DesignComponentLibrary).where(DesignComponentLibrary.is_active == True)  # noqa: E712
    rows = (
        await db.execute(
            query.order_by(DesignComponentLibrary.subsystem, DesignComponentLibrary.component_name)
        )
    ).scalars().all()

    subsystems_set = {c.subsystem for c in rows if c.subsystem}
    tags_set = {c.tag for c in rows if c.tag}

    disabled_subs = set(config_dict.get("disabled_subsystems", []))
    disabled_tags = set(config_dict.get("disabled_tags", []))
    disabled_cids = {UUID(str(x)) for x in config_dict.get("disabled_component_ids", [])}

    components: list[ComponentItemSummary] = []
    enabled_count = 0
    for c in rows:
        sub_disabled = c.subsystem in disabled_subs
        tag_disabled = bool(c.tag and c.tag in disabled_tags)
        cid_disabled = c.id in disabled_cids
        is_enabled = not (sub_disabled or tag_disabled or cid_disabled)
        if is_enabled:
            enabled_count += 1

        components.append(
            ComponentItemSummary(
                id=c.id,
                component_name=c.component_name,
                subsystem=c.subsystem,
                tag=c.tag,
                component_code=c.component_code,
                example_role=c.example_role,
                scaled_mass_g=c.scaled_mass_g,
                voltage_v=c.voltage_v,
                current_ma=c.current_ma,
                assumed_cost_usd=c.assumed_cost_usd,
                image_url=await storage.resolve_url(c.image_bucket, c.image_path),
                is_active=c.is_active,
                is_enabled=is_enabled,
            )
        )

    return ComponentConfigOut(
        owner_type=owner_type,
        owner_id=owner_id,
        is_inherited=is_inherited,
        has_override=has_override,
        disabled_subsystems=sorted(list(disabled_subs)),
        disabled_tags=sorted(list(disabled_tags)),
        disabled_component_ids=sorted(list(disabled_cids)),
        available_subsystems=sorted(list(subsystems_set)),
        available_tags=sorted(list(tags_set)),
        total_components=len(rows),
        enabled_components=enabled_count,
        components=components,
        updated_at=config_dict.get("updated_at"),
        updated_by=config_dict.get("updated_by"),
    )


async def is_component_allowed_for_cohort(
    db: AsyncSession, *, cohort_id: UUID | None, library_component_id: UUID
) -> bool:
    """Validate whether a component is permitted in the cohort."""
    if cohort_id is None:
        return True

    component = await db.get(DesignComponentLibrary, library_component_id)
    if component is None or not component.is_active:
        return False

    config_dict, _, _ = await resolve_effective_component_config(db, cohort_id=cohort_id)

    if component.subsystem in config_dict.get("disabled_subsystems", []):
        return False
    if component.tag and component.tag in config_dict.get("disabled_tags", []):
        return False
    if component.id in config_dict.get("disabled_component_ids", []):
        return False

    return True

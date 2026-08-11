"""Design mission routes (P7-5) — `/missions/design/*`. Registered before
`/missions/{mission_id}` in `routers/missions/__init__.py`: 'design' is a
static path that would otherwise be swallowed by the dynamic mission_id
segment (same routing-order lesson as `/missions/admin`, `/missions/graph`,
`/missions/teams`).

One `GET .../attempts/{attempt_id}` returns the whole nine-step wizard's
state in one fetch — design fields, components with every budget
override, the CONOPS matrix, the link entry, and the computed dashboard.
Write endpoints stay one-per-action (add a component, save CONOPS, save
one component's data-budget entry, ...), matching what the UI actually
does step by step.

Authorization: the caller must be an "own attempt" per
`routers/missions/student.py::_own_attempt` — the solo student, or any
member of a team attempt's frozen roster. Design-kind attempts are
solo-or-team like any other mission (`team_policy`), nothing here is
design-specific about who may act on it.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.missions.design import (
    Design,
    DesignComponent,
    DesignComponentModeState,
    DesignCostBudgetEntry,
    DesignDataBudgetEntry,
    DesignLinkBudgetEntry,
    DesignMassBudgetEntry,
    DesignMode,
    DesignPowerBudgetEntry,
)
from app.models.missions.mission import Mission, MissionAttempt, MissionVariant
from app.models.user import User
from app.schemas.missions_design import (
    ConopsSaveIn,
    ConopsSummaryOut,
    CostBudgetSummaryOut,
    CostEntrySaveIn,
    CubeSatPresetOut,
    DashboardOut,
    DataBudgetSummaryOut,
    DataEntrySaveIn,
    DesignComponentAddIn,
    DesignComponentOut,
    DesignCostEntryOut,
    DesignDataEntryOut,
    DesignLibraryComponentOut,
    DesignMassEntryOut,
    DesignModeOut,
    DesignPowerEntryOut,
    DesignStateOut,
    DesignUpdateIn,
    LinkBudgetSummaryOut,
    LinkEntryOut,
    LinkEntrySaveIn,
    MassBudgetSummaryOut,
    MassEntrySaveIn,
    PowerBudgetSummaryOut,
    PowerEntrySaveIn,
    StepStatusOut,
)
from app.services import storage
from app.services.missions.design import service as design_service
from app.services.missions.design.calculators import CUBESAT_PRESETS
from app.services.missions.design.gating import GATED_STEPS, assert_step_unlocked, is_step_unlocked
from app.services.missions.design.rf_calc import BAND_PRESETS
from app.services.missions.verifiers.design import ensure_design, mark_design_complete
from app.routers.missions.student import _own_attempt

router = APIRouter(prefix="/missions/design", tags=["missions-design"])


async def _own_design_attempt(db: AsyncSession, attempt_id: uuid.UUID, user: User) -> MissionAttempt:
    attempt = await _own_attempt(db, attempt_id, user)
    mission = await db.get(Mission, attempt.mission_id)
    if mission is None or mission.kind != "design":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Attempt not found")
    return attempt


async def _design_state_out(db: AsyncSession, *, attempt: MissionAttempt, design: Design) -> DesignStateOut:
    mission = await db.get(Mission, attempt.mission_id)
    variant = await db.get(MissionVariant, attempt.variant_id)

    components = await design_service.list_components(db, design_id=design.id)
    component_ids = [c.id for c in components]
    mode_states = await design_service.get_mode_states(db, design_id=design.id)

    data_by_component = {
        e.design_component_id: e for e in (await db.execute(
            select(DesignDataBudgetEntry).where(DesignDataBudgetEntry.design_component_id.in_(component_ids))
        )).scalars().all()
    } if component_ids else {}
    power_by_component = {
        e.design_component_id: e for e in (await db.execute(
            select(DesignPowerBudgetEntry).where(DesignPowerBudgetEntry.design_component_id.in_(component_ids))
        )).scalars().all()
    } if component_ids else {}
    mass_by_component = {
        e.design_component_id: e for e in (await db.execute(
            select(DesignMassBudgetEntry).where(DesignMassBudgetEntry.design_component_id.in_(component_ids))
        )).scalars().all()
    } if component_ids else {}
    cost_by_component = {
        e.design_component_id: e for e in (await db.execute(
            select(DesignCostBudgetEntry).where(DesignCostBudgetEntry.design_component_id.in_(component_ids))
        )).scalars().all()
    } if component_ids else {}

    component_out = []
    for c in components:
        image_url = await storage.resolve_url(c.image_bucket, c.image_path)
        data_e = data_by_component.get(c.id)
        power_e = power_by_component.get(c.id)
        mass_e = mass_by_component.get(c.id)
        cost_e = cost_by_component.get(c.id)
        component_out.append(DesignComponentOut(
            id=c.id, library_component_id=c.library_component_id,
            component_name=c.component_name, subsystem=c.subsystem, image_url=image_url,
            quantity=c.quantity, mass_per_unit_g=c.mass_per_unit_g,
            length_mm=c.length_mm, width_mm=c.width_mm, height_mm=c.height_mm,
            voltage_v=c.voltage_v, current_ma=c.current_ma, cost_per_unit_aed=c.cost_per_unit_aed,
            on_mode_ids=list(mode_states.get(c.id, set())),
            data_entry=DesignDataEntryOut(
                data_type=data_e.data_type, data_size_per_measurement_kb=data_e.data_size_per_measurement_kb,
                measurements_per_minute=data_e.measurements_per_minute, priority=data_e.priority,
                storage_mode=data_e.storage_mode, notes=data_e.notes,
            ) if data_e else None,
            power_entry=DesignPowerEntryOut(voltage_v=power_e.voltage_v, current_ma=power_e.current_ma, notes=power_e.notes) if power_e else None,
            mass_entry=DesignMassEntryOut(
                quantity=mass_e.quantity, mass_per_unit_g=mass_e.mass_per_unit_g,
                length_mm=mass_e.length_mm, width_mm=mass_e.width_mm, height_mm=mass_e.height_mm, notes=mass_e.notes,
            ) if mass_e else None,
            cost_entry=DesignCostEntryOut(
                quantity=cost_e.quantity, cost_per_unit_aed=cost_e.cost_per_unit_aed, vendor=cost_e.vendor,
                priority=cost_e.priority, purchase_link=cost_e.purchase_link, notes=cost_e.notes,
            ) if cost_e else None,
        ))

    modes = await design_service.ensure_default_modes(db, design_id=design.id)
    mode_out = [DesignModeOut(id=m.id, mode_name=m.mode_name, position=m.position, duration_min=m.duration_min, description=m.description) for m in modes]

    link_entry = (await db.execute(select(DesignLinkBudgetEntry).where(DesignLinkBudgetEntry.design_id == design.id))).scalars().first()
    link_out = None
    if link_entry:
        link_out = LinkEntryOut(
            band_profile=link_entry.band_profile, downlink_frequency_mhz=link_entry.downlink_frequency_mhz,
            uplink_frequency_mhz=link_entry.uplink_frequency_mhz, satellite_antenna_gain_dbi=link_entry.satellite_antenna_gain_dbi,
            data_rate_kbps=link_entry.data_rate_kbps, required_signal_quality_db=link_entry.required_signal_quality_db,
            notes=link_entry.notes, is_saved=link_entry.is_saved,
        )

    locked_steps = [s for s in GATED_STEPS if not await is_step_unlocked(db, cohort_id=design.cohort_id, step_key=s)]

    dash = await design_service.compute_dashboard(db, design=design, variant_config=variant.config or {})
    thresholds = dash["thresholds"]
    limits = dash["cubesat_limits"]
    dashboard_out = DashboardOut(
        all_valid=dash["all_valid"],
        steps={k: StepStatusOut(**v) for k, v in dash["steps"].items()},
        conops=ConopsSummaryOut(
            total_mode_duration_min=dash["conops"].total_mode_duration_min,
            duration_difference_min=dash["conops"].duration_difference_min,
        ),
        data=DataBudgetSummaryOut(
            total_per_orbit_kb=dash["data"].total_per_orbit_kb, total_per_day_kb=dash["data"].total_per_day_kb,
            total_stored_per_day_kb=dash["data"].total_stored_per_day_kb, total_sent_per_day_kb=dash["data"].total_sent_per_day_kb,
            storage_remaining_kb=dash["data"].storage_remaining_kb, max_storage_kb=thresholds["max_storage_kb"],
            required_storage_margin_kb=thresholds["required_storage_margin_kb"],
        ),
        power=PowerBudgetSummaryOut(
            total_power_mw=dash["power"].total_power_mw, total_energy_per_orbit_mwh=dash["power"].total_energy_per_orbit_mwh,
            total_energy_per_day_mwh=dash["power"].total_energy_per_day_mwh, power_margin_mw=dash["power"].power_margin_mw,
            required_solar_cells=dash["power"].required_solar_cells, generated_power_mw=dash["power"].generated_power_mw,
            selected_solar_cells=design.selected_solar_cells, power_per_solar_cell_w=thresholds["power_per_solar_cell_w"],
        ),
        mass=MassBudgetSummaryOut(
            total_mass_kg=dash["mass"].total_mass_kg, mass_margin_kg=dash["mass"].mass_margin_kg,
            total_volume_cm3=dash["mass"].total_volume_cm3, volume_margin_cm3=dash["mass"].volume_margin_cm3,
            max_allowed_mass_kg=limits["max_mass_kg"], available_internal_volume_cm3=limits["available_volume_cm3"],
        ),
        cost=CostBudgetSummaryOut(
            total_cost_aed=dash["cost"].total_cost_aed, cost_margin_aed=dash["cost"].cost_margin_aed,
            maximum_budget_aed=thresholds["maximum_budget_aed"],
        ),
        link=LinkBudgetSummaryOut(margin_db=dash["link"].margin_db, status=dash["link"].status),
    )

    return DesignStateOut(
        id=design.id, attempt_id=attempt.id, mission_id=mission.id, variant_id=variant.id,
        variant_label=variant.label, attempt_status=attempt.status,
        design_name=design.design_name, design_objective=design.design_objective,
        orbit_type=design.orbit_type, orbit_duration_min=design.orbit_duration_min, orbits_per_day=design.orbits_per_day,
        selected_cubesat_size=design.selected_cubesat_size, selected_solar_cells=design.selected_solar_cells,
        created_at=design.created_at,
        components=component_out, modes=mode_out, link_entry=link_out,
        cubesat_presets=[CubeSatPresetOut(size=k, **v) for k, v in CUBESAT_PRESETS.items()],
        band_presets=BAND_PRESETS,
        dashboard=dashboard_out,
        locked_steps=locked_steps,
    )


@router.get("/library", response_model=list[DesignLibraryComponentOut])
async def list_library(
    subsystem: str | None = None, search: str | None = None,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    from app.models.missions.design import DesignComponentLibrary
    query = select(DesignComponentLibrary).where(DesignComponentLibrary.is_active == True)  # noqa: E712
    if subsystem:
        query = query.where(DesignComponentLibrary.subsystem == subsystem)
    if search:
        query = query.where(DesignComponentLibrary.component_name.ilike(f"%{search}%"))
    rows = (await db.execute(query.order_by(DesignComponentLibrary.subsystem, DesignComponentLibrary.component_name))).scalars().all()
    out = []
    for c in rows:
        out.append(DesignLibraryComponentOut(
            id=c.id, component_name=c.component_name, subsystem=c.subsystem, tag=c.tag,
            example_role=c.example_role, scaled_description=c.scaled_description,
            length_mm=c.length_mm, width_mm=c.width_mm, height_mm=c.height_mm,
            scaled_mass_g=c.scaled_mass_g, voltage_v=c.voltage_v, current_ma=c.current_ma,
            data_size=c.data_size, assumed_cost_usd=c.assumed_cost_usd, temperature_range=c.temperature_range,
            key_specs=c.key_specs, image_url=await storage.resolve_url(c.image_bucket, c.image_path),
            component_code=c.component_code, datasheet_url=c.datasheet_url,
        ))
    return out


@router.get("/attempts/{attempt_id}", response_model=DesignStateOut)
async def get_design_state(
    attempt_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    attempt = await _own_design_attempt(db, attempt_id, current)
    design = await ensure_design(db, attempt=attempt)
    await db.commit()
    return await _design_state_out(db, attempt=attempt, design=design)


@router.patch("/attempts/{attempt_id}", response_model=DesignStateOut)
async def update_design(
    attempt_id: uuid.UUID, body: DesignUpdateIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    attempt = await _own_design_attempt(db, attempt_id, current)
    design = await ensure_design(db, attempt=attempt)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(design, field, value)
    await db.commit()
    return await _design_state_out(db, attempt=attempt, design=design)


@router.post("/attempts/{attempt_id}/components", response_model=DesignStateOut, status_code=status.HTTP_201_CREATED)
async def add_design_component(
    attempt_id: uuid.UUID, body: DesignComponentAddIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    attempt = await _own_design_attempt(db, attempt_id, current)
    design = await ensure_design(db, attempt=attempt)
    await design_service.add_component(db, design_id=design.id, library_component_id=body.library_component_id, quantity=body.quantity)
    await db.commit()
    return await _design_state_out(db, attempt=attempt, design=design)


@router.delete("/attempts/{attempt_id}/components/{design_component_id}", response_model=DesignStateOut)
async def remove_design_component(
    attempt_id: uuid.UUID, design_component_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    attempt = await _own_design_attempt(db, attempt_id, current)
    design = await ensure_design(db, attempt=attempt)
    await design_service.remove_component(db, design_id=design.id, design_component_id=design_component_id)
    await db.commit()
    return await _design_state_out(db, attempt=attempt, design=design)


@router.post("/attempts/{attempt_id}/conops", response_model=DesignStateOut)
async def save_conops(
    attempt_id: uuid.UUID, body: ConopsSaveIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    attempt = await _own_design_attempt(db, attempt_id, current)
    design = await ensure_design(db, attempt=attempt)
    for mode_id, duration in body.mode_durations.items():
        await design_service.save_mode_duration(db, design_mode_id=mode_id, duration_min=duration)
    for component_id, states in body.cell_states.items():
        for mode_id, is_on in states.items():
            await design_service.set_mode_state(db, design_component_id=component_id, design_mode_id=mode_id, is_on=is_on)
    await db.commit()
    return await _design_state_out(db, attempt=attempt, design=design)


@router.post("/attempts/{attempt_id}/components/{design_component_id}/data-budget", response_model=DesignStateOut)
async def save_data_budget(
    attempt_id: uuid.UUID, design_component_id: uuid.UUID, body: DataEntrySaveIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    attempt = await _own_design_attempt(db, attempt_id, current)
    design = await ensure_design(db, attempt=attempt)
    await assert_step_unlocked(db, design=design, step_key="data_budget")
    await design_service.save_data_entry(db, design_component_id=design_component_id, **body.model_dump())
    await db.commit()
    return await _design_state_out(db, attempt=attempt, design=design)


@router.post("/attempts/{attempt_id}/components/{design_component_id}/power-budget", response_model=DesignStateOut)
async def save_power_budget(
    attempt_id: uuid.UUID, design_component_id: uuid.UUID, body: PowerEntrySaveIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    attempt = await _own_design_attempt(db, attempt_id, current)
    design = await ensure_design(db, attempt=attempt)
    await assert_step_unlocked(db, design=design, step_key="power_budget")
    await design_service.save_power_entry(db, design_component_id=design_component_id, **body.model_dump())
    await db.commit()
    return await _design_state_out(db, attempt=attempt, design=design)


@router.post("/attempts/{attempt_id}/components/{design_component_id}/mass-budget", response_model=DesignStateOut)
async def save_mass_budget(
    attempt_id: uuid.UUID, design_component_id: uuid.UUID, body: MassEntrySaveIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    attempt = await _own_design_attempt(db, attempt_id, current)
    design = await ensure_design(db, attempt=attempt)
    await assert_step_unlocked(db, design=design, step_key="mass_budget")
    await design_service.save_mass_entry(db, design_component_id=design_component_id, **body.model_dump())
    await db.commit()
    return await _design_state_out(db, attempt=attempt, design=design)


@router.post("/attempts/{attempt_id}/components/{design_component_id}/cost-budget", response_model=DesignStateOut)
async def save_cost_budget(
    attempt_id: uuid.UUID, design_component_id: uuid.UUID, body: CostEntrySaveIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    attempt = await _own_design_attempt(db, attempt_id, current)
    design = await ensure_design(db, attempt=attempt)
    await assert_step_unlocked(db, design=design, step_key="cost_budget")
    await design_service.save_cost_entry(db, design_component_id=design_component_id, **body.model_dump())
    await db.commit()
    return await _design_state_out(db, attempt=attempt, design=design)


@router.post("/attempts/{attempt_id}/link-budget", response_model=DesignStateOut)
async def save_link_budget(
    attempt_id: uuid.UUID, body: LinkEntrySaveIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    attempt = await _own_design_attempt(db, attempt_id, current)
    design = await ensure_design(db, attempt=attempt)
    await assert_step_unlocked(db, design=design, step_key="link_budget")
    await design_service.save_link_entry(db, design_id=design.id, **body.model_dump())
    await db.commit()
    return await _design_state_out(db, attempt=attempt, design=design)


@router.post("/attempts/{attempt_id}/complete", response_model=DesignStateOut)
async def complete_design(
    attempt_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    """Raises 400 with `{message, steps}` when the design isn't ready yet
    — the frontend reads `detail.steps` to show exactly what's missing,
    same shape `mark_design_complete` already builds. A 400 here never
    touches the attempt's status (still `in_progress`); only a 200 means
    the design passed."""
    attempt = await _own_design_attempt(db, attempt_id, current)
    design = await ensure_design(db, attempt=attempt)
    await mark_design_complete(db, attempt=attempt)
    await db.commit()
    return await _design_state_out(db, attempt=attempt, design=design)

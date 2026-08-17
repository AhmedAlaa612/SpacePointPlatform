"""Design mission service layer (P7-4/P7-6, Phase 2 Stage 7, 2026-08-11) —
bridges the DB (`models/missions/design.py`) to the pure calculators
(`calculators.py`). One function per Madar page's data needs: components,
CONOPS, and the five budgets, plus `compute_dashboard` which composes all
six into the single `all_valid` completion check
(PHASE2_EXECUTION_PLAN.md Stage 7: "a single completion check (all_valid),
points award once on validity").

P7-6: every threshold (`max_storage_kb`, `max_allowed_mass_kg`, etc.) comes
from `variant.config`, read-only to the student — never a column the
student can write to (F4). `Design.selected_cubesat_size` is the one
student-owned choice that determines a limit, resolved through
`CUBESAT_PRESETS`, itself never student-editable.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.models.missions.mission import MissionAttempt

from app.models.missions.design import (
    Design,
    DesignComponent,
    DesignComponentLibrary,
    DesignComponentModeState,
    DesignCostBudgetEntry,
    DesignDataBudgetEntry,
    DesignLinkBudgetEntry,
    DesignMassBudgetEntry,
    DesignMode,
    DesignPowerBudgetEntry,
)
from app.services import storage
from app.services.missions.design import rf_calc
from app.services.missions.design.calculators import (
    calc_downlink_budget,
    calc_energy_budget,
    CUBESAT_PRESETS,
    ComponentInput,
    ModeInput,
    calc_conops,
    calc_cost_budget,
    calc_data_budget,
    calc_link_budget_status,
    calc_mass_budget,
    calc_power_budget,
)

USD_TO_AED_RATE = 3.67  # same conversion constant Madar used, applied once at snapshot time now

DEFAULT_MODES = [
    {"mode_name": "Sun Pointing", "position": 0, "description": "Satellite pointing solar panels toward the sun"},
    {"mode_name": "Nadir/Payload Pointing", "position": 1, "description": "Satellite pointing payload toward Earth"},
    {"mode_name": "Ground Station", "position": 2, "description": "Communicating with ground station for downlink/uplink"},
    {"mode_name": "Safe/Eclipse Mode", "position": 3, "description": "Low-power survival mode during anomaly or eclipse"},
]


# ── Design + variant config ─────────────────────────────────────────────

async def get_or_404(db: AsyncSession, design_id: uuid.UUID) -> Design:
    design = await db.get(Design, design_id)
    if design is None:
        raise HTTPException(404, detail="Design not found")
    return design


def variant_thresholds(config: dict) -> dict:
    """The read-only pass/fail thresholds for this design's variant —
    every design-mission variant's config carries these keys (P7-6)."""
    return {
        "max_storage_kb": config.get("max_storage_kb", 1_048_576.0),
        "required_storage_margin_kb": config.get("required_storage_margin_kb", 104_857.6),
        "power_per_solar_cell_w": config.get("power_per_solar_cell_w", 1.1),
        "maximum_budget_aed": config.get("maximum_budget_aed", 2000.0),
        "assumed_distance_km": config.get("assumed_distance_km", 500.0),
        "transmit_power_dbm": config.get("transmit_power_dbm", 30.0),
        "good_link_margin_threshold_db": config.get("good_link_margin_threshold_db", 3.0),
        "weak_link_margin_threshold_db": config.get("weak_link_margin_threshold_db", 0.0),
        # Design v2 (7D-2) — F8 and F7 thresholds. Variant-owned like every
        # other limit here, never a student-editable column.
        "max_depth_of_discharge_pct": config.get("max_depth_of_discharge_pct", 30.0),
        "required_downlink_margin_fraction": config.get("required_downlink_margin_fraction", 0.10),
    }


def cubesat_limits(selected_cubesat_size: str) -> dict:
    return CUBESAT_PRESETS.get(selected_cubesat_size, CUBESAT_PRESETS["1U"])


# ── Components (library -> frozen snapshot, F1/F2/F3 fix) ─────────────────

async def add_component(
    db: AsyncSession, *, design_id: uuid.UUID, library_component_id: uuid.UUID, quantity: int = 1,
) -> DesignComponent:
    library = await db.get(DesignComponentLibrary, library_component_id)
    if library is None or not library.is_active:
        raise HTTPException(404, detail="Component not found")
    dc = DesignComponent(
        id=uuid.uuid4(), design_id=design_id, library_component_id=library.id, quantity=quantity,
        component_name=library.component_name, subsystem=library.subsystem,
        image_bucket=library.image_bucket, image_path=library.image_path,
        mass_per_unit_g=library.scaled_mass_g,
        length_mm=library.length_mm, width_mm=library.width_mm, height_mm=library.height_mm,
        voltage_v=library.voltage_v, current_ma=library.current_ma,
        cost_per_unit_aed=(library.assumed_cost_usd * USD_TO_AED_RATE) if library.assumed_cost_usd is not None else None,
    )
    db.add(dc)
    await db.flush()
    return dc


async def remove_component(db: AsyncSession, *, design_id: uuid.UUID, design_component_id: uuid.UUID) -> None:
    dc = await db.get(DesignComponent, design_component_id)
    if dc is None or dc.design_id != design_id:
        raise HTTPException(404, detail="Design component not found")
    await db.delete(dc)
    await db.flush()


async def list_components(db: AsyncSession, *, design_id: uuid.UUID) -> list[DesignComponent]:
    return list((await db.execute(
        select(DesignComponent).where(DesignComponent.design_id == design_id).order_by(DesignComponent.created_at)
    )).scalars().all())


# ── CONOPS (modes + component x mode matrix) ────────────────────────────

async def ensure_default_modes(db: AsyncSession, *, design_id: uuid.UUID) -> list[DesignMode]:
    existing = (await db.execute(
        select(DesignMode).where(DesignMode.design_id == design_id).order_by(DesignMode.position)
    )).scalars().all()
    if existing:
        return list(existing)
    modes = [DesignMode(id=uuid.uuid4(), design_id=design_id, **d) for d in DEFAULT_MODES]
    db.add_all(modes)
    await db.flush()
    return modes


async def get_mode_states(db: AsyncSession, *, design_id: uuid.UUID) -> dict[uuid.UUID, set[uuid.UUID]]:
    """design_component_id -> the set of design_mode_ids it's ON in."""
    components = await list_components(db, design_id=design_id)
    component_ids = [c.id for c in components]
    if not component_ids:
        return {}
    states = (await db.execute(
        select(DesignComponentModeState).where(
            DesignComponentModeState.design_component_id.in_(component_ids), DesignComponentModeState.is_on == True,  # noqa: E712
        )
    )).scalars().all()
    result: dict[uuid.UUID, set[uuid.UUID]] = {cid: set() for cid in component_ids}
    for s in states:
        result[s.design_component_id].add(s.design_mode_id)
    return result


async def set_mode_state(
    db: AsyncSession, *, design_component_id: uuid.UUID, design_mode_id: uuid.UUID, is_on: bool,
) -> None:
    state = await db.get(DesignComponentModeState, (design_component_id, design_mode_id))
    if state is None:
        db.add(DesignComponentModeState(design_component_id=design_component_id, design_mode_id=design_mode_id, is_on=is_on))
    else:
        state.is_on = is_on
    await db.flush()


async def save_mode_duration(db: AsyncSession, *, design_mode_id: uuid.UUID, duration_min: float) -> None:
    mode = await db.get(DesignMode, design_mode_id)
    if mode is None:
        raise HTTPException(404, detail="Mode not found")
    mode.duration_min = duration_min
    mode.updated_at = datetime.now(timezone.utc)
    await db.flush()


# ── Budget entry saves (student overrides of the frozen snapshot) ──────

async def save_data_entry(db: AsyncSession, *, design_component_id: uuid.UUID, **fields) -> DesignDataBudgetEntry:
    entry = (await db.execute(
        select(DesignDataBudgetEntry).where(DesignDataBudgetEntry.design_component_id == design_component_id)
    )).scalars().first()
    if entry is None:
        entry = DesignDataBudgetEntry(id=uuid.uuid4(), design_component_id=design_component_id)
        db.add(entry)
    for k, v in fields.items():
        setattr(entry, k, v)
    entry.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return entry


async def save_power_entry(db: AsyncSession, *, design_component_id: uuid.UUID, **fields) -> DesignPowerBudgetEntry:
    entry = (await db.execute(
        select(DesignPowerBudgetEntry).where(DesignPowerBudgetEntry.design_component_id == design_component_id)
    )).scalars().first()
    if entry is None:
        entry = DesignPowerBudgetEntry(id=uuid.uuid4(), design_component_id=design_component_id)
        db.add(entry)
    for k, v in fields.items():
        setattr(entry, k, v)
    entry.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return entry


async def save_mass_entry(db: AsyncSession, *, design_component_id: uuid.UUID, **fields) -> DesignMassBudgetEntry:
    entry = (await db.execute(
        select(DesignMassBudgetEntry).where(DesignMassBudgetEntry.design_component_id == design_component_id)
    )).scalars().first()
    if entry is None:
        entry = DesignMassBudgetEntry(id=uuid.uuid4(), design_component_id=design_component_id)
        db.add(entry)
    for k, v in fields.items():
        setattr(entry, k, v)
    entry.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return entry


async def save_cost_entry(db: AsyncSession, *, design_component_id: uuid.UUID, **fields) -> DesignCostBudgetEntry:
    entry = (await db.execute(
        select(DesignCostBudgetEntry).where(DesignCostBudgetEntry.design_component_id == design_component_id)
    )).scalars().first()
    if entry is None:
        entry = DesignCostBudgetEntry(id=uuid.uuid4(), design_component_id=design_component_id)
        db.add(entry)
    for k, v in fields.items():
        setattr(entry, k, v)
    entry.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return entry


async def save_link_entry(db: AsyncSession, *, design_id: uuid.UUID, **fields) -> DesignLinkBudgetEntry:
    entry = (await db.execute(
        select(DesignLinkBudgetEntry).where(DesignLinkBudgetEntry.design_id == design_id)
    )).scalars().first()
    if entry is None:
        entry = DesignLinkBudgetEntry(id=uuid.uuid4(), design_id=design_id)
        db.add(entry)
    for k, v in fields.items():
        setattr(entry, k, v)
    entry.is_saved = True  # F6 fix — a real recorded fact, set exactly once the save endpoint runs
    entry.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return entry


# ── Gathering DB rows into the pure calculators' input shape ───────────

async def _component_inputs(db: AsyncSession, *, design_id: uuid.UUID) -> list[ComponentInput]:
    components = await list_components(db, design_id=design_id)
    if not components:
        return []
    component_ids = [c.id for c in components]
    mode_states = await get_mode_states(db, design_id=design_id)

    data_entries = {
        e.design_component_id: e for e in (await db.execute(
            select(DesignDataBudgetEntry).where(DesignDataBudgetEntry.design_component_id.in_(component_ids))
        )).scalars().all()
    }
    power_entries = {
        e.design_component_id: e for e in (await db.execute(
            select(DesignPowerBudgetEntry).where(DesignPowerBudgetEntry.design_component_id.in_(component_ids))
        )).scalars().all()
    }
    mass_entries = {
        e.design_component_id: e for e in (await db.execute(
            select(DesignMassBudgetEntry).where(DesignMassBudgetEntry.design_component_id.in_(component_ids))
        )).scalars().all()
    }
    cost_entries = {
        e.design_component_id: e for e in (await db.execute(
            select(DesignCostBudgetEntry).where(DesignCostBudgetEntry.design_component_id.in_(component_ids))
        )).scalars().all()
    }

    inputs = []
    for c in components:
        data = data_entries.get(c.id)
        power = power_entries.get(c.id)
        mass = mass_entries.get(c.id)
        cost = cost_entries.get(c.id)
        inputs.append(ComponentInput(
            subsystem=c.subsystem,
            quantity=(mass.quantity if mass and mass.quantity is not None else c.quantity),
            on_mode_ids={str(mid) for mid in mode_states.get(c.id, set())},
            mass_per_unit_g=(mass.mass_per_unit_g if mass and mass.mass_per_unit_g is not None else c.mass_per_unit_g),
            length_mm=(mass.length_mm if mass and mass.length_mm is not None else c.length_mm),
            width_mm=(mass.width_mm if mass and mass.width_mm is not None else c.width_mm),
            height_mm=(mass.height_mm if mass and mass.height_mm is not None else c.height_mm),
            voltage_v=(power.voltage_v if power and power.voltage_v is not None else c.voltage_v),
            current_ma=(power.current_ma if power and power.current_ma is not None else c.current_ma),
            cost_per_unit_aed=(cost.cost_per_unit_aed if cost and cost.cost_per_unit_aed is not None else c.cost_per_unit_aed),
            data_size_per_measurement_kb=data.data_size_per_measurement_kb if data else None,
            measurements_per_minute=data.measurements_per_minute if data else None,
            storage_mode=data.storage_mode if data else "Stored",
        ))
    return inputs


async def _mode_inputs(db: AsyncSession, *, design_id: uuid.UUID) -> list[ModeInput]:
    modes = await ensure_default_modes(db, design_id=design_id)
    return [ModeInput(id=str(m.id), duration_min=m.duration_min, position=m.position) for m in modes]


# ── The dashboard: composes all six calculators + step status ──────────

async def compute_dashboard(
    db: AsyncSession, *, design: Design, variant_config: dict,
    attempt: MissionAttempt | None = None,
) -> dict:
    thresholds = variant_thresholds(variant_config)
    limits = cubesat_limits(design.selected_cubesat_size)

    modes = await _mode_inputs(db, design_id=design.id)
    components = await _component_inputs(db, design_id=design.id)

    conops = calc_conops(orbit_duration_min=design.orbit_duration_min or 0.0, modes=modes)
    data = calc_data_budget(
        components=components, modes=modes, orbits_per_day=design.orbits_per_day or 1.0,
        max_storage_kb=thresholds["max_storage_kb"], required_storage_margin_kb=thresholds["required_storage_margin_kb"],
    )
    power = calc_power_budget(
        components=components, modes=modes, orbits_per_day=design.orbits_per_day or 1.0,
        power_per_solar_cell_w=thresholds["power_per_solar_cell_w"], selected_solar_cells=design.selected_solar_cells,
    )
    mass = calc_mass_budget(
        components=components, max_allowed_mass_kg=limits["max_mass_kg"],
        available_internal_volume_cm3=limits["available_volume_cm3"],
    )
    cost = calc_cost_budget(components=components, maximum_budget_aed=thresholds["maximum_budget_aed"])

    link_entry = (await db.execute(
        select(DesignLinkBudgetEntry).where(DesignLinkBudgetEntry.design_id == design.id)
    )).scalars().first()
    link_status_str = None
    link_margin = None
    if link_entry and link_entry.is_saved:
        calc = rf_calc.calculate_link_budget(
            downlink_frequency_mhz=link_entry.downlink_frequency_mhz,
            satellite_antenna_gain_dbi=link_entry.satellite_antenna_gain_dbi,
            data_rate_kbps=link_entry.data_rate_kbps,
            required_signal_quality_db=link_entry.required_signal_quality_db,
            transmit_power_dbm=thresholds["transmit_power_dbm"],
            distance_km=thresholds["assumed_distance_km"],
            good_threshold_db=thresholds["good_link_margin_threshold_db"],
            weak_threshold_db=thresholds["weak_link_margin_threshold_db"],
        )
        link_status_str = calc.link_status
        link_margin = calc.system_link_margin_db
    link = calc_link_budget_status(
        is_saved=bool(link_entry and link_entry.is_saved), link_status=link_status_str, margin_db=link_margin,
    )

    # Design v2 (7D-2) — the two cross-checks Madar left open. Both read the
    # CONOPS matrix rather than one budget's own inputs, which is what makes
    # that matrix load-bearing for four budgets instead of two.
    downlink = calc_downlink_budget(
        total_sent_per_day_kb=data.total_sent_per_day_kb,
        orbits_per_day=design.orbits_per_day or 1.0,
        modes=modes,
        data_rate_kbps=(link_entry.data_rate_kbps if link_entry else None),
        link_is_saved=bool(link_entry and link_entry.is_saved),
        required_margin_fraction=thresholds["required_downlink_margin_fraction"],
    )
    energy = calc_energy_budget(
        components=components, modes=modes,
        orbit_duration_min=design.orbit_duration_min or 0.0,
        generated_power_mw=power.generated_power_mw,
        battery_capacity_wh=design.battery_capacity_wh,
        max_depth_of_discharge_pct=thresholds["max_depth_of_discharge_pct"],
    )

    steps = {
        "components": {"has_data": len(components) > 0, "is_valid": len(components) > 0},
        "conops": {"has_data": conops.has_data, "is_valid": conops.is_valid},
        "data_budget": {"has_data": data.has_data, "is_valid": data.is_valid},
        "power_budget": {"has_data": power.has_data, "is_valid": power.is_valid},
        "energy_budget": {"has_data": energy.has_data, "is_valid": energy.is_valid},
        "link_budget": {"has_data": link.has_data, "is_valid": link.is_valid},
        # Not a tab of its own — a constraint that spans Data, Link and
        # CONOPS. The dashboard's alerts say which of the three to change.
        "downlink": {"has_data": downlink.has_data, "is_valid": downlink.is_valid},
        "mass_budget": {"has_data": mass.has_data, "is_valid": mass.is_valid},
        "cost_budget": {"has_data": cost.has_data, "is_valid": cost.is_valid},
    }

    # Cohort-scoped step selection (2026-08-17) — compositional, distinct
    # from step *gating*. `steps` above always reports every step's real
    # math validity regardless of scope (admin/diagnostic views rely on
    # that); only which keys count toward `all_valid` changes here.
    if attempt is not None and attempt.cohort_id is not None:
        from app.services.lms.admin_progress import DOWNLINK_STEP_DEPS
        from app.services.missions.step_selection import selected_steps_for_cohort_mission

        included = await selected_steps_for_cohort_mission(
            db, cohort_id=attempt.cohort_id, mission_id=attempt.mission_id,
        )
    else:
        from app.services.lms.admin_progress import DOWNLINK_STEP_DEPS, SELECTABLE_STEP_KEYS

        included = set(SELECTABLE_STEP_KEYS)

    downlink_included = DOWNLINK_STEP_DEPS <= included
    effective_keys = included | ({"downlink"} if downlink_included else set())
    all_valid = all(steps[k]["has_data"] and steps[k]["is_valid"] for k in effective_keys)

    return {
        "conops": conops, "data": data, "power": power, "link": link, "mass": mass, "cost": cost,
        "downlink": downlink, "energy": energy,
        "steps": steps, "all_valid": all_valid,
        "included_steps": included, "downlink_included": downlink_included,
        "cubesat_limits": limits, "thresholds": thresholds,
    }

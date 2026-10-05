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

import logging
import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
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
    AlertOut,
    DataBudgetSummaryOut,
    DesignBriefingOut,
    DesignCustomComponentCreateIn,
    DesignCustomComponentOut,
    DesignCustomComponentUpdateIn,
    DesignHandbookOut,
    DownlinkBudgetSummaryOut,
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
    MarginRowOut,
    ModuleCardOut,
    OverallStatusOut,
    RecommendationOut,
    LinkEntryOut,
    LinkEntrySaveIn,
    MassBudgetSummaryOut,
    MassEntrySaveIn,
    PowerBudgetSummaryOut,
    PowerEntrySaveIn,
    StepStatusOut,
)
from app.services import storage
from app.services.missions.design import content as design_content
from app.services.missions.design import report as design_report
from app.services.missions.design import service as design_service
from app.services.missions.design.calculators import CUBESAT_PRESETS
from app.services.missions.design.rf_calc import BAND_PRESETS
from app.services.missions.verifiers.design import ensure_design, mark_design_complete
from app.services.lms.admin_progress import DESIGN_STEP_LABELS
from app.services.missions.gating import gate_map_for_attempt, require_step_unlocked
from app.services.lms.program import team_final_locked_for_attempt, team_frozen_step_keys_for_attempt
from app.routers.missions.student import _own_attempt

router = APIRouter(prefix="/missions/design", tags=["missions-design"])
logger = logging.getLogger(__name__)

# Step keys the student can explicitly self-check (2026-09) — `setup` (no
# `DESIGN_STEP_LABELS` row of its own, see design_state_out's own
# `included_steps` comment) plus every selectable design-phase tab except
# `downlink` (not a tab) and `report` (stays purely validity-driven —
# matches DesignMissionPage.tsx's own exclusion of the Report tab from the
# Complete-button flow).
CONFIRMABLE_STEP_KEYS = {"setup"} | {key for key, _ in DESIGN_STEP_LABELS if key not in ("downlink", "poster")}


async def _own_design_attempt(db: AsyncSession, attempt_id: uuid.UUID, user: User) -> MissionAttempt:
    attempt = await _own_attempt(db, attempt_id, user)
    mission = await db.get(Mission, attempt.mission_id)
    if mission is None or mission.kind != "design":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Attempt not found")
    return attempt


async def _require_team_not_final_locked(db: AsyncSession, *, attempt: MissionAttempt) -> None:
    """Call at the top of every mutating endpoint below, right after
    `_own_design_attempt` — same "call explicitly, per write endpoint"
    convention `require_step_unlocked` already uses in this file. Only
    matters for a team-scoped `mission_run` checklist item's shared
    attempt (`team_final_locked_for_attempt`); an individual attempt is
    never blocked. Without this, a locked team's checklist could still
    change via the design wizard even though `student.py`'s own write
    endpoints already 409 (found in code review, 2026-09-18)."""
    if await team_final_locked_for_attempt(db, attempt_id=attempt.id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Your team's final submission is locked — ask an ops staff member to reopen it",
        )


async def design_state_out(db: AsyncSession, *, attempt: MissionAttempt, design: Design) -> DesignStateOut:
    """Callers must build this BEFORE `db.commit()`, not after — this
    function's `ensure_default_modes()` call lazily creates the 4
    `DesignMode` rows on first read, and only flushes them (never
    commits). Committing first, then calling this, let those rows
    survive just long enough to serialize into that one response before
    the session closed and rolled them back — the next request's
    `db.get()` on those now-nonexistent IDs 404'd with "Mode not found".

    Public (2026-08-22) — the real "what did they name it and what did
    they pick" component/mode/margin detail this builds is exactly what
    the staff-facing design-run detail routes (`routers/missions/instructor.py`,
    `routers/missions/admin.py`) need too, keyed off any attempt, not just
    the caller's own. `margins`/`module_cards` still follow the attempt's
    own cohort step-selection scope (same as the student's own view) —
    only the raw `components`/`modes` lists, which are never scoped, are
    the actual "what they selected" detail those routes are really after."""
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
            custom_component_id=c.custom_component_id, is_custom=c.is_custom,
            component_name=c.component_name, subsystem=c.subsystem, image_url=image_url,
            quantity=c.quantity, mass_per_unit_g=c.mass_per_unit_g,
            length_mm=c.length_mm, width_mm=c.width_mm, height_mm=c.height_mm,
            voltage_v=c.voltage_v, current_ma=c.current_ma, cost_per_unit_aed=c.cost_per_unit_aed,
            purpose_function=c.purpose_function, pins_used=c.pins_used,
            measurement_output=c.measurement_output, measurement_range=c.measurement_range,
            power_computed_mw=c.power_computed_mw, datasheet_reference=c.datasheet_reference,
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


    dash = await design_service.compute_dashboard(db, design=design, variant_config=variant.config or {}, attempt=attempt)
    thresholds = dash["thresholds"]
    limits = dash["cubesat_limits"]
    # The exact key set that already decides `dash["all_valid"]` — a step
    # this cohort's run never selected gets no margin row, no module card,
    # and no alert either, not just an ignored pass/fail (2026-08-22).
    effective_keys = dash["included_steps"] | ({"downlink"} if dash["downlink_included"] else set())
    margins = design_report.build_margins(dash, thresholds, limits, effective_keys)
    alerts, recommendations = design_report.build_advice(dash, margins, effective_keys)
    dashboard_out = DashboardOut(
        all_valid=dash["all_valid"],
        steps={k: StepStatusOut(**v) for k, v in dash["steps"].items()},
        downlink_included=dash["downlink_included"],
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
        link=LinkBudgetSummaryOut(
            margin_db=dash["link"].margin_db, status=dash["link"].status,
            good_threshold_db=thresholds["good_link_margin_threshold_db"],
            weak_threshold_db=thresholds["weak_link_margin_threshold_db"],
            assumed_distance_km=thresholds["assumed_distance_km"],
            transmit_power_dbm=thresholds["transmit_power_dbm"],
        ),
        downlink=DownlinkBudgetSummaryOut(
            data_to_downlink_per_orbit_kb=dash["downlink"].data_to_downlink_per_orbit_kb,
            downlink_capacity_per_orbit_kb=dash["downlink"].downlink_capacity_per_orbit_kb,
            downlink_margin_kb=dash["downlink"].downlink_margin_kb,
            contact_minutes=dash["downlink"].contact_minutes,
            utilisation_pct=dash["downlink"].utilisation_pct,
        ),
        overall=OverallStatusOut(**design_report.overall_status(dash, margins)),
        kpis=design_report.build_kpis(dash, len(component_out), len(mode_out)),
        margins=[MarginRowOut(**m) for m in margins],
        module_cards=[ModuleCardOut(**c) for c in design_report.build_module_cards(
            dash, thresholds, len(component_out), effective_keys)],
        charts=design_report.build_charts(component_out, mode_out),
        alerts=[AlertOut(**a) for a in alerts],
        recommendations=[RecommendationOut(**r) for r in recommendations],
    )

    step_gates = await gate_map_for_attempt(db, attempt=attempt)
    included_step_set = dash["included_steps"]  # same resolved set compute_dashboard already fetched
    included_steps = {key: (key in included_step_set) for key, _ in DESIGN_STEP_LABELS if key != "downlink"}

    poster_template_url = None
    if attempt.cohort_id is not None:
        cohort = await db.get(Cohort, attempt.cohort_id)
        if cohort is not None:
            poster_template_url = cohort.poster_template_url
            if not poster_template_url and cohort.program_id is not None:
                program = await db.get(Program, cohort.program_id)
                if program is not None:
                    poster_template_url = program.poster_template_url

    return DesignStateOut(
        id=design.id, attempt_id=attempt.id, mission_id=mission.id, variant_id=variant.id,
        variant_label=variant.label, attempt_status=attempt.status,
        design_name=design.design_name, design_objective=design.design_objective,
        orbit_type=design.orbit_type, orbit_duration_min=design.orbit_duration_min, orbits_per_day=design.orbits_per_day,
        selected_cubesat_size=design.selected_cubesat_size, selected_solar_cells=design.selected_solar_cells,
        battery_capacity_wh=design.battery_capacity_wh,
        created_at=design.created_at,
        poster_template_url=poster_template_url, poster_url=design.poster_url,
        components=component_out, modes=mode_out, link_entry=link_out,
        cubesat_presets=[CubeSatPresetOut(size=k, **v) for k, v in CUBESAT_PRESETS.items()],
        band_presets=BAND_PRESETS,
        dashboard=dashboard_out,
        assumptions=design_content.ASSUMPTIONS,
        step_gates=step_gates,
        included_steps=included_steps,
        confirmed_steps=list(design.confirmed_steps or []),
    )


@router.get("/briefing/{mission_id}", response_model=DesignBriefingOut)
async def get_design_briefing(
    mission_id: uuid.UUID, variant_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    """Pre-design briefing (7D-4). No attempt is created — a student can
    read this as often as they like without spending a retry, which is why
    it lives on its own route rather than inside the wizard."""
    mission = await db.get(Mission, mission_id)
    if mission is None or mission.kind != "design":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Mission not found")

    if variant_id is not None:
        variant = await db.get(MissionVariant, variant_id)
        if variant is None or variant.mission_id != mission.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Variant not found")
    else:
        variant = (await db.execute(
            select(MissionVariant).where(MissionVariant.mission_id == mission.id)
            .order_by(MissionVariant.position)
        )).scalars().first()
        if variant is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="This mission has no difficulty variants")

    return DesignBriefingOut(
        mission_id=mission.id,
        **design_content.apply_overrides(
            design_content.briefing(variant, mission_title=mission.title, mission_summary=mission.summary),
            mission.content or {},
        ),
    )


@router.get("/attempts/{attempt_id}/handbook", response_model=DesignHandbookOut)
async def get_design_handbook(
    attempt_id: uuid.UUID, db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """The Design Handbook (7D-5) — available *while* designing at every
    difficulty. What the variant controls is how much of the fix is written
    down, via `config.handbook_disclosure`, the same knob the operate
    mission uses."""
    attempt = await _own_design_attempt(db, attempt_id, current)
    variant = await db.get(MissionVariant, attempt.variant_id)
    mission = await db.get(Mission, attempt.mission_id)
    config = (variant.config or {}) if variant else {}
    # D8 — the mission's own authored copy wins over the code defaults.
    return DesignHandbookOut(**design_content.apply_overrides(
        design_content.handbook(disclosure=str(config.get("handbook_disclosure", "full"))),
        (mission.content or {}) if mission else {},
    ))


@router.get("/library", response_model=list[DesignLibraryComponentOut])
async def list_library(
    subsystem: str | None = None, search: str | None = None,
    attempt_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    from app.models.missions.design import DesignComponentLibrary
    from app.services.missions.component_config import resolve_effective_component_config

    query = select(DesignComponentLibrary).where(DesignComponentLibrary.is_active == True)  # noqa: E712
    if subsystem:
        query = query.where(DesignComponentLibrary.subsystem == subsystem)
    if search:
        query = query.where(DesignComponentLibrary.component_name.ilike(f"%{search}%"))

    if attempt_id is not None:
        attempt = await db.get(MissionAttempt, attempt_id)
        if attempt is not None and attempt.cohort_id is not None:
            config_dict, _, _ = await resolve_effective_component_config(db, cohort_id=attempt.cohort_id)
            disabled_subs = config_dict.get("disabled_subsystems", [])
            if disabled_subs:
                query = query.where(~DesignComponentLibrary.subsystem.in_(disabled_subs))
            disabled_tags = config_dict.get("disabled_tags", [])
            if disabled_tags:
                query = query.where(or_(DesignComponentLibrary.tag.is_(None), ~DesignComponentLibrary.tag.in_(disabled_tags)))
            disabled_cids = config_dict.get("disabled_component_ids", [])
            if disabled_cids:
                query = query.where(~DesignComponentLibrary.id.in_(disabled_cids))
    rows = (await db.execute(query.order_by(DesignComponentLibrary.subsystem, DesignComponentLibrary.component_name))).scalars().all()
    out = []
    for c in rows:
        has_file = bool(c.datasheet_bucket and c.datasheet_path)
        out.append(DesignLibraryComponentOut(
            id=c.id, component_name=c.component_name, subsystem=c.subsystem, tag=c.tag,
            example_role=c.example_role, scaled_description=c.scaled_description,
            length_mm=c.length_mm, width_mm=c.width_mm, height_mm=c.height_mm,
            scaled_mass_g=c.scaled_mass_g, voltage_v=c.voltage_v, current_ma=c.current_ma,
            data_size=c.data_size, assumed_cost_usd=c.assumed_cost_usd, temperature_range=c.temperature_range,
            key_specs=c.key_specs, image_url=await storage.resolve_url(c.image_bucket, c.image_path),
            component_code=c.component_code,
            # Never both: an uploaded file's URL is resolved on demand (see
            # /library/{id}/datasheet-url), not embedded in this list.
            datasheet_url=None if has_file else c.datasheet_url,
            has_datasheet_file=has_file,
        ))
    return out


@router.get("/library/{component_id}/datasheet-url")
async def get_library_datasheet_url(
    component_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
) -> dict[str, str]:
    """Resolved only when someone actually opens the viewer — same posture
    as the LMS attachment viewer and the instructor library's own datasheet
    fix (routers/instructors/library.py), never embedded in the list above.
    """
    from app.models.missions.design import DesignComponentLibrary
    component = await db.get(DesignComponentLibrary, component_id)
    if component is None or not (component.datasheet_bucket and component.datasheet_path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No datasheet file on this component")
    url = await storage.get_signed_url(component.datasheet_bucket, component.datasheet_path, expires_in=3600)
    return {"url": url}


@router.get("/attempts/{attempt_id}", response_model=DesignStateOut)
async def get_design_state(
    attempt_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    attempt = await _own_design_attempt(db, attempt_id, current)
    design = await ensure_design(db, attempt=attempt)
    result = await design_state_out(db, attempt=attempt, design=design)
    await db.commit()
    return result


@router.patch("/attempts/{attempt_id}", response_model=DesignStateOut)
async def update_design(
    attempt_id: uuid.UUID, body: DesignUpdateIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    attempt = await _own_design_attempt(db, attempt_id, current)
    await _require_team_not_final_locked(db, attempt=attempt)
    design = await ensure_design(db, attempt=attempt)
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(design, field, value)
    result = await design_state_out(db, attempt=attempt, design=design)
    await db.commit()
    return result


@router.post("/attempts/{attempt_id}/components", response_model=DesignStateOut, status_code=status.HTTP_201_CREATED)
async def add_design_component(
    attempt_id: uuid.UUID, body: DesignComponentAddIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    attempt = await _own_design_attempt(db, attempt_id, current)
    await _require_team_not_final_locked(db, attempt=attempt)
    await require_step_unlocked(db, attempt=attempt, step_key="components")
    design = await ensure_design(db, attempt=attempt)
    if body.custom_component_id is not None:
        if attempt.cohort_id is not None:
            from app.services.missions.component_config import is_custom_component_allowed_for_cohort

            if not await is_custom_component_allowed_for_cohort(db, cohort_id=attempt.cohort_id):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail="Custom components are disabled for your cohort's mission design.",
                )
        await design_service.add_custom_to_design(
            db, design_id=design.id, attempt_id=attempt.id,
            custom_component_id=body.custom_component_id, quantity=body.quantity,
        )
    else:
        # XOR validator guarantees library_component_id is set on this branch.
        assert body.library_component_id is not None
        if attempt.cohort_id is not None:
            from app.services.missions.component_config import is_component_allowed_for_cohort

            allowed = await is_component_allowed_for_cohort(
                db, cohort_id=attempt.cohort_id, library_component_id=body.library_component_id
            )
            if not allowed:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail="This component is not available for your cohort's mission design.",
                )
        await design_service.add_component(db, design_id=design.id, library_component_id=body.library_component_id, quantity=body.quantity)
    result = await design_state_out(db, attempt=attempt, design=design)
    await db.commit()
    return result


CUSTOM_IMAGE_BUCKET = "mission-assets"


async def _custom_out(c) -> DesignCustomComponentOut:
    from app.services.missions.design.service import custom_power_mw
    image_url = (await storage.resolve_url(c.image_bucket, c.image_path)) if (c.image_bucket and c.image_path) else None
    return DesignCustomComponentOut(
        id=c.id, attempt_id=c.attempt_id, component_name=c.component_name, subsystem=c.subsystem,
        purpose_function=c.purpose_function, voltage_v=c.voltage_v, current_ma=c.current_ma,
        power_computed_mw=custom_power_mw(voltage_v=c.voltage_v, current_ma=c.current_ma),
        pins_used=c.pins_used, measurement_output=c.measurement_output,
        measurement_range=c.measurement_range, datasheet_reference=c.datasheet_reference,
        mass_g=c.mass_g, length_mm=c.length_mm, width_mm=c.width_mm, height_mm=c.height_mm,
        cost_aed=c.cost_aed, is_active=c.is_active,
        image_url=image_url,
        created_at=c.created_at, updated_at=c.updated_at,
    )


@router.post("/attempts/{attempt_id}/custom-components/upload-image")
async def upload_custom_component_temp_image(
    attempt_id: uuid.UUID, file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    await _own_design_attempt(db, attempt_id, current)
    data = await file.read()
    if len(data) > 4 * 1024 * 1024:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Image must be under 4 MB")
    suffix = (file.filename or "img.png").rsplit(".", 1)[-1].lower()
    if suffix not in {"png", "jpg", "jpeg", "webp"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Image must be PNG, JPG or WebP")

    img_id = uuid.uuid4().hex
    path = f"custom-components/{attempt_id}/{img_id}.{suffix}"
    await storage.upload_to_path(CUSTOM_IMAGE_BUCKET, path, data, file.content_type or "image/png")
    image_url = await storage.resolve_url(CUSTOM_IMAGE_BUCKET, path)
    return {"image_bucket": CUSTOM_IMAGE_BUCKET, "image_path": path, "image_url": image_url}


@router.post("/attempts/{attempt_id}/custom-components/{custom_component_id}/image", response_model=DesignCustomComponentOut)
async def upload_custom_component_image(
    attempt_id: uuid.UUID, custom_component_id: uuid.UUID, file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    attempt = await _own_design_attempt(db, attempt_id, current)
    await _require_team_not_final_locked(db, attempt=attempt)
    await require_step_unlocked(db, attempt=attempt, step_key="components")

    data = await file.read()
    if len(data) > 4 * 1024 * 1024:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Image must be under 4 MB")
    suffix = (file.filename or "img.png").rsplit(".", 1)[-1].lower()
    if suffix not in {"png", "jpg", "jpeg", "webp"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Image must be PNG, JPG or WebP")

    img_id = uuid.uuid4().hex
    path = f"custom-components/{attempt_id}/{custom_component_id}_{img_id}.{suffix}"
    await storage.upload_to_path(CUSTOM_IMAGE_BUCKET, path, data, file.content_type or "image/png")
    custom = await design_service.update_custom_component(
        db, attempt_id=attempt.id, custom_component_id=custom_component_id,
        fields={"image_bucket": CUSTOM_IMAGE_BUCKET, "image_path": path},
    )
    await db.commit()
    await db.refresh(custom)
    return await _custom_out(custom)


@router.post("/attempts/{attempt_id}/custom-components", response_model=DesignStateOut, status_code=status.HTTP_201_CREATED)
async def create_custom_component(
    attempt_id: uuid.UUID, body: DesignCustomComponentCreateIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    """Define a student-owned custom part and place it in the design in one
    step (quantity comes from the same body). The part is visible only to
    this attempt (+ ops via design-detail/explorer) — never to other
    students, never to sibling attempts/retries."""
    attempt = await _own_design_attempt(db, attempt_id, current)
    await _require_team_not_final_locked(db, attempt=attempt)
    await require_step_unlocked(db, attempt=attempt, step_key="components")
    if attempt.cohort_id is not None:
        from app.services.missions.component_config import is_custom_component_allowed_for_cohort

        if not await is_custom_component_allowed_for_cohort(db, cohort_id=attempt.cohort_id):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Custom components are disabled for your cohort's mission design.",
            )
    design = await ensure_design(db, attempt=attempt)
    fields = body.model_dump(exclude={"quantity"})
    custom = await design_service.create_custom_component(
        db, attempt=attempt, user_id=current.id, fields=fields,
    )
    await design_service.add_custom_to_design(
        db, design_id=design.id, attempt_id=attempt.id,
        custom_component_id=custom.id, quantity=body.quantity,
    )
    result = await design_state_out(db, attempt=attempt, design=design)
    await db.commit()
    return result


@router.get("/attempts/{attempt_id}/custom-components", response_model=list[DesignCustomComponentOut])
async def list_custom_components(
    attempt_id: uuid.UUID, db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    attempt = await _own_design_attempt(db, attempt_id, current)
    rows = await design_service.list_custom_components(db, attempt_id=attempt.id)
    return [await _custom_out(c) for c in rows]


@router.patch("/attempts/{attempt_id}/custom-components/{custom_component_id}", response_model=DesignCustomComponentOut)
async def update_custom_component(
    attempt_id: uuid.UUID, custom_component_id: uuid.UUID, body: DesignCustomComponentUpdateIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    attempt = await _own_design_attempt(db, attempt_id, current)
    await _require_team_not_final_locked(db, attempt=attempt)
    await require_step_unlocked(db, attempt=attempt, step_key="components")
    custom = await design_service.update_custom_component(
        db, attempt_id=attempt.id, custom_component_id=custom_component_id,
        fields=body.model_dump(exclude_unset=True),
    )
    await db.commit()
    await db.refresh(custom)
    return await _custom_out(custom)


@router.delete("/attempts/{attempt_id}/custom-components/{custom_component_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_custom_component(
    attempt_id: uuid.UUID, custom_component_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    attempt = await _own_design_attempt(db, attempt_id, current)
    await _require_team_not_final_locked(db, attempt=attempt)
    await require_step_unlocked(db, attempt=attempt, step_key="components")
    await design_service.deactivate_custom_component(
        db, attempt_id=attempt.id, custom_component_id=custom_component_id,
    )
    await db.commit()


@router.delete("/attempts/{attempt_id}/components/{design_component_id}", response_model=DesignStateOut)
async def remove_design_component(
    attempt_id: uuid.UUID, design_component_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    attempt = await _own_design_attempt(db, attempt_id, current)
    await _require_team_not_final_locked(db, attempt=attempt)
    design = await ensure_design(db, attempt=attempt)
    await design_service.remove_component(db, design_id=design.id, design_component_id=design_component_id)
    result = await design_state_out(db, attempt=attempt, design=design)
    await db.commit()
    return result


@router.post("/attempts/{attempt_id}/conops", response_model=DesignStateOut)
async def save_conops(
    attempt_id: uuid.UUID, body: ConopsSaveIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    attempt = await _own_design_attempt(db, attempt_id, current)
    await _require_team_not_final_locked(db, attempt=attempt)
    await require_step_unlocked(db, attempt=attempt, step_key="conops")
    design = await ensure_design(db, attempt=attempt)
    for mode_id, duration in body.mode_durations.items():
        await design_service.save_mode_duration(db, design_mode_id=mode_id, duration_min=duration)
    for component_id, states in body.cell_states.items():
        for mode_id, is_on in states.items():
            await design_service.set_mode_state(db, design_component_id=component_id, design_mode_id=mode_id, is_on=is_on)
    result = await design_state_out(db, attempt=attempt, design=design)
    await db.commit()
    return result


@router.post("/attempts/{attempt_id}/components/{design_component_id}/data-budget", response_model=DesignStateOut)
async def save_data_budget(
    attempt_id: uuid.UUID, design_component_id: uuid.UUID, body: DataEntrySaveIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    attempt = await _own_design_attempt(db, attempt_id, current)
    await _require_team_not_final_locked(db, attempt=attempt)
    await require_step_unlocked(db, attempt=attempt, step_key="data_budget")
    design = await ensure_design(db, attempt=attempt)
    await design_service.save_data_entry(
        db, design_id=design.id, design_component_id=design_component_id, **body.model_dump()
    )
    result = await design_state_out(db, attempt=attempt, design=design)
    await db.commit()
    return result


@router.post("/attempts/{attempt_id}/components/{design_component_id}/power-budget", response_model=DesignStateOut)
async def save_power_budget(
    attempt_id: uuid.UUID, design_component_id: uuid.UUID, body: PowerEntrySaveIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    attempt = await _own_design_attempt(db, attempt_id, current)
    await _require_team_not_final_locked(db, attempt=attempt)
    await require_step_unlocked(db, attempt=attempt, step_key="power_budget")
    design = await ensure_design(db, attempt=attempt)
    await design_service.save_power_entry(
        db, design_id=design.id, design_component_id=design_component_id, **body.model_dump()
    )
    result = await design_state_out(db, attempt=attempt, design=design)
    await db.commit()
    return result


@router.post("/attempts/{attempt_id}/components/{design_component_id}/mass-budget", response_model=DesignStateOut)
async def save_mass_budget(
    attempt_id: uuid.UUID, design_component_id: uuid.UUID, body: MassEntrySaveIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    attempt = await _own_design_attempt(db, attempt_id, current)
    await _require_team_not_final_locked(db, attempt=attempt)
    await require_step_unlocked(db, attempt=attempt, step_key="mass_budget")
    design = await ensure_design(db, attempt=attempt)
    await design_service.save_mass_entry(
        db, design_id=design.id, design_component_id=design_component_id, **body.model_dump()
    )
    result = await design_state_out(db, attempt=attempt, design=design)
    await db.commit()
    return result


@router.post("/attempts/{attempt_id}/components/{design_component_id}/cost-budget", response_model=DesignStateOut)
async def save_cost_budget(
    attempt_id: uuid.UUID, design_component_id: uuid.UUID, body: CostEntrySaveIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    attempt = await _own_design_attempt(db, attempt_id, current)
    await _require_team_not_final_locked(db, attempt=attempt)
    await require_step_unlocked(db, attempt=attempt, step_key="cost_budget")
    design = await ensure_design(db, attempt=attempt)
    await design_service.save_cost_entry(
        db, design_id=design.id, design_component_id=design_component_id, **body.model_dump()
    )
    result = await design_state_out(db, attempt=attempt, design=design)
    await db.commit()
    return result


@router.post("/attempts/{attempt_id}/link-budget", response_model=DesignStateOut)
async def save_link_budget(
    attempt_id: uuid.UUID, body: LinkEntrySaveIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    attempt = await _own_design_attempt(db, attempt_id, current)
    await _require_team_not_final_locked(db, attempt=attempt)
    await require_step_unlocked(db, attempt=attempt, step_key="link_budget")
    design = await ensure_design(db, attempt=attempt)
    await design_service.save_link_entry(db, design_id=design.id, **body.model_dump())
    result = await design_state_out(db, attempt=attempt, design=design)
    await db.commit()
    return result


@router.post("/attempts/{attempt_id}/steps/{step_key}/confirm", response_model=DesignStateOut)
async def confirm_design_step(
    attempt_id: uuid.UUID, step_key: str,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    """Explicit student self-check for one design-phase step (2026-09) —
    "Complete this step" in DesignMissionPage.tsx. `is_valid` alone used to
    be enough for a Roadmap board `mission_run` tile to read done the
    instant a step's bare-minimum requirement was met (e.g. one component
    added); this is the persisted "I'm actually done here" click that
    `_mission_run_item_done` (services/lms/program.py) now also requires.
    Rejects a step whose own requirements aren't met yet — the frontend's
    Complete button is disabled for the same reason, but a client can't be
    trusted to enforce that itself. Idempotent: confirming an
    already-confirmed step just returns the current state."""
    if step_key not in CONFIRMABLE_STEP_KEYS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"'{step_key}' can't be self-confirmed")
    attempt = await _own_design_attempt(db, attempt_id, current)
    await _require_team_not_final_locked(db, attempt=attempt)
    # Checkpoint freeze (design slice): only this phase's *confirmed
    # state* freezes when its own checklist tile sits above a locked
    # checkpoint — every other design write in this file stays open on
    # purpose, because the same shared attempt also drives
    # downstream-phase tiles below the checkpoint that the team must
    # keep editing.
    if step_key in await team_frozen_step_keys_for_attempt(db, attempt_id=attempt.id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="This design phase is frozen by a locked checkpoint — ask an ops staff member to reopen it",
        )
    if step_key != "setup":
        await require_step_unlocked(db, attempt=attempt, step_key=step_key)
    design = await ensure_design(db, attempt=attempt)
    if step_key == "setup":
        ready = design.design_objective is not None
    else:
        variant = await db.get(MissionVariant, attempt.variant_id)
        dash = await design_service.compute_dashboard(
            db, design=design, variant_config=(variant.config or {}) if variant else {}, attempt=attempt,
        )
        step = dash["steps"].get(step_key)
        ready = bool(step and step["has_data"] and step["is_valid"])
    if not ready:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="This step's requirements aren't met yet")
    confirmed = set(design.confirmed_steps or [])
    if step_key not in confirmed:
        confirmed.add(step_key)
        design.confirmed_steps = sorted(confirmed)
        await db.flush()

    # Auto-finalize (2026-09): once every step this cohort's variant
    # actually includes has been explicitly confirmed, and the design is
    # fully valid end to end (this also covers 'downlink', which has no
    # confirm button of its own — it isn't in CONFIRMABLE_STEP_KEYS),
    # there's nothing left for the student to decide. Requiring a further,
    # separate "Mark design complete" click at that point would just repeat
    # work already done — see mark_design_complete's own docstring for what
    # this reuses. Recomputes the dashboard rather than trusting whatever
    # `ready` above already checked for a single step, since a non-"setup"
    # confirm only validates that one step.
    if attempt.status == "in_progress":
        variant = await db.get(MissionVariant, attempt.variant_id)
        dash = await design_service.compute_dashboard(
            db, design=design, variant_config=(variant.config or {}) if variant else {}, attempt=attempt,
        )
        required = {"setup"} | (dash["included_steps"] & CONFIRMABLE_STEP_KEYS)
        if required <= confirmed and dash["all_valid"]:
            try:
                await mark_design_complete(db, attempt=attempt)
            except HTTPException as exc:
                # Expected case: valid when we checked above, became invalid before
                # mark_design_complete's own recompute (concurrent edit) — a 400. Anything
                # else reaching here (e.g. a 409 "attempt not in_progress") would be a real
                # bug, since we already checked attempt.status=="in_progress" above — log it
                # so that stays debuggable instead of silently vanishing. Either way, the step
                # confirmation above still stands; just skip auto-finalize this time. The
                # student (or their next confirm) gets another shot at it.
                logger.info(
                    "Auto-finalize skipped for attempt %s after step '%s': %s %s",
                    attempt.id, step_key, exc.status_code, exc.detail,
                )

    result = await design_state_out(db, attempt=attempt, design=design)
    await db.commit()
    return result


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
    await _require_team_not_final_locked(db, attempt=attempt)
    design = await ensure_design(db, attempt=attempt)
    await mark_design_complete(db, attempt=attempt)
    result = await design_state_out(db, attempt=attempt, design=design)
    await db.commit()
    return result

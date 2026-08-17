"""P7-4/P7-6 (LMS Phase 2 Stage 7, 2026-08-11) — the design service layer:
component snapshotting, dashboard composition, and mark_design_complete.
Redis-free, HTTP-free (verifier HTTPExceptions are still raised directly,
same posture as the rest of services/lms and services/missions).
"""

import uuid

import pytest
from fastapi import HTTPException

from app.models.missions.design import DesignComponentLibrary
from app.models.missions.mission import Mission, MissionVariant
from app.models.user import User
from app.services.missions import start_attempt
from app.services.missions.design import service as design_service
from app.services.missions.verifiers.design import ensure_design, mark_design_complete


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Design User", email=f"design-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=roles or ["student"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _design_mission(db, *, author) -> tuple[Mission, MissionVariant]:
    mission = Mission(
        id=uuid.uuid4(), title="CubeSat Mission Design", slug=f"design-{uuid.uuid4().hex[:8]}",
        kind="design", authored_by=author.id, status="published", team_policy="either",
    )
    db.add(mission)
    await db.flush()
    variant = MissionVariant(
        id=uuid.uuid4(), mission_id=mission.id, label="Engineer", position=2, points=200,
        config={
            "max_storage_kb": 1000.0, "required_storage_margin_kb": 100.0,
            "power_per_solar_cell_w": 1.1, "maximum_budget_aed": 2000.0,
            "assumed_distance_km": 500.0, "transmit_power_dbm": 30.0,
            "good_link_margin_threshold_db": 3.0, "weak_link_margin_threshold_db": 0.0,
        },
    )
    db.add(variant)
    await db.flush()
    return mission, variant


async def _cohort(db):
    from app.models.sessions.cohort import Cohort
    from app.models.sessions.program import Program

    program = Program(
        id=uuid.uuid4(), code=f"DSN-{uuid.uuid4().hex[:8]}", name="Design Step Selection Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Design Step Selection Cohort", status="running")
    db.add(cohort)
    await db.flush()
    return cohort


async def _library_component(db, **overrides) -> DesignComponentLibrary:
    defaults = dict(
        id=uuid.uuid4(), component_name="Test Battery", subsystem="EPS",
        scaled_mass_g=100.0, length_mm=50.0, width_mm=50.0, height_mm=30.0,
        voltage_v=8.2, current_ma=2600.0, assumed_cost_usd=200.0, is_active=True,
    )
    defaults.update(overrides)
    comp = DesignComponentLibrary(**defaults)
    db.add(comp)
    await db.flush()
    return comp


# ── Component snapshotting (F1/F2/F3) ───────────────────────────────────

@pytest.mark.asyncio
async def test_add_component_snapshots_library_values(db):
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    student = await _user(db)
    attempt = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variant.id)
    design = await ensure_design(db, attempt=attempt)
    library = await _library_component(db)

    dc = await design_service.add_component(db, design_id=design.id, library_component_id=library.id, quantity=2)
    assert dc.component_name == "Test Battery"
    assert dc.mass_per_unit_g == 100.0
    assert dc.cost_per_unit_aed == pytest.approx(200.0 * design_service.USD_TO_AED_RATE)


@pytest.mark.asyncio
async def test_editing_the_library_after_add_does_not_change_the_snapshot(db):
    """F2 regression: Madar fell back to live component.* values whenever
    the student hadn't overridden them, so an admin correcting a
    component's mass silently changed past students' totals."""
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    student = await _user(db)
    attempt = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variant.id)
    design = await ensure_design(db, attempt=attempt)
    library = await _library_component(db, scaled_mass_g=100.0)

    dc = await design_service.add_component(db, design_id=design.id, library_component_id=library.id)
    library.scaled_mass_g = 9999.0  # admin edits the library after the fact
    await db.flush()

    assert dc.mass_per_unit_g == 100.0  # snapshot untouched


@pytest.mark.asyncio
async def test_cannot_add_a_retired_component(db):
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    student = await _user(db)
    attempt = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variant.id)
    design = await ensure_design(db, attempt=attempt)
    library = await _library_component(db, is_active=False)

    with pytest.raises(HTTPException):
        await design_service.add_component(db, design_id=design.id, library_component_id=library.id)


# ── Dashboard composition + mark_design_complete ────────────────────────

async def _build_passing_design(db, design_id, library_id):
    modes = await design_service.ensure_default_modes(db, design_id=design_id)
    dc = await design_service.add_component(db, design_id=design_id, library_component_id=library_id, quantity=1)
    ground_station_mode = next(m for m in modes if m.mode_name == "Ground Station")
    await design_service.set_mode_state(db, design_component_id=dc.id, design_mode_id=ground_station_mode.id, is_on=True)
    total = sum(m.duration_min for m in modes)
    for m in modes:
        await design_service.save_mode_duration(db, design_mode_id=m.id, duration_min=90 / len(modes))
    await design_service.save_data_entry(
        db, design_component_id=dc.id, data_size_per_measurement_kb=0.1,
        # Design v2: "Both" — stored on board *and* downlinked. The F7 check
        # treats sending nothing as a failed mission, not a skipped step.
        measurements_per_minute=1.0, storage_mode="Both",
    )
    await design_service.save_power_entry(db, design_component_id=dc.id, voltage_v=5.0, current_ma=100.0)
    await design_service.save_mass_entry(db, design_component_id=dc.id)
    await design_service.save_cost_entry(db, design_component_id=dc.id, cost_per_unit_aed=50.0)
    await design_service.save_link_entry(
        db, design_id=design_id, band_profile="UHF",
        downlink_frequency_mhz=437.5, uplink_frequency_mhz=145.8,
        satellite_antenna_gain_dbi=2.0, data_rate_kbps=9.6, required_signal_quality_db=9.6,
    )
    design = await design_service.get_or_404(db, design_id)
    design.orbit_duration_min = 90.0
    design.orbits_per_day = 15.0
    design.selected_solar_cells = 5
    design.battery_capacity_wh = 10.0  # Design v2 (D4) — the energy step needs one
    await db.flush()


@pytest.mark.asyncio
async def test_dashboard_all_valid_when_every_step_passes(db):
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    student = await _user(db)
    library = await _library_component(db)
    attempt = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variant.id)
    design = await ensure_design(db, attempt=attempt)

    await _build_passing_design(db, design.id, library.id)

    dashboard = await design_service.compute_dashboard(db, design=design, variant_config=variant.config)
    assert dashboard["all_valid"] is True, dashboard["steps"]


@pytest.mark.asyncio
async def test_dashboard_invalid_when_a_step_is_incomplete(db):
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    student = await _user(db)
    attempt = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variant.id)
    design = await ensure_design(db, attempt=attempt)

    dashboard = await design_service.compute_dashboard(db, design=design, variant_config=variant.config)
    assert dashboard["all_valid"] is False
    assert dashboard["steps"]["components"]["has_data"] is False


@pytest.mark.asyncio
async def test_mark_design_complete_rejects_an_invalid_design_without_touching_status(db):
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    student = await _user(db)
    attempt = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variant.id)
    await ensure_design(db, attempt=attempt)

    with pytest.raises(HTTPException) as exc:
        await mark_design_complete(db, attempt=attempt)
    assert exc.value.status_code == 400
    assert attempt.status == "in_progress"  # never flips to failed


@pytest.mark.asyncio
async def test_mark_design_complete_passes_and_awards_points_when_valid(db):
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    student = await _user(db)
    library = await _library_component(db)
    attempt = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variant.id)
    design = await ensure_design(db, attempt=attempt)
    await _build_passing_design(db, design.id, library.id)

    decided, dashboard = await mark_design_complete(db, attempt=attempt)
    assert decided.status == "passed"
    assert dashboard["all_valid"] is True

    from sqlalchemy import select
    from app.models.lms import PointEvent
    events = (await db.execute(select(PointEvent).where(PointEvent.user_id == student.id))).scalars().all()
    assert sum(e.points for e in events) == 200  # the Engineer variant's points


# ── Cohort-scoped step selection (2026-08-17) ───────────────────────────

@pytest.mark.asyncio
async def test_compute_dashboard_attempt_none_matches_legacy_flat_and_over_nine(db):
    """Backward-compat regression: an attempt with no cohort behaves
    identically to the pre-subset flat-AND-over-9 all_valid logic, whether
    or not `attempt` is even passed."""
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    student = await _user(db)
    library = await _library_component(db)
    attempt = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variant.id)
    design = await ensure_design(db, attempt=attempt)
    await _build_passing_design(db, design.id, library.id)

    without_attempt = await design_service.compute_dashboard(db, design=design, variant_config=variant.config)
    with_attempt = await design_service.compute_dashboard(db, design=design, variant_config=variant.config, attempt=attempt)
    assert without_attempt["all_valid"] is True
    assert with_attempt["all_valid"] is True
    assert with_attempt["included_steps"] == without_attempt["included_steps"]
    assert with_attempt["downlink_included"] is True


@pytest.mark.asyncio
async def test_tdra_case_power_and_mass_only_no_conops_required(db):
    """The real TDRA Summer Camp example: a cohort scoped to Power + Mass
    (which pulls in Components, their real shared prereq) reports
    all_valid once those are satisfied, with CONOPS left completely
    untouched — proving power_budget's only hard prerequisite is
    components, not conops."""
    from app.services.missions.step_selection import set_selected_steps

    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    student = await _user(db)
    library = await _library_component(db)
    cohort = await _cohort(db)

    attempt = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variant.id)
    attempt.cohort_id = cohort.id
    await db.flush()
    design = await ensure_design(db, attempt=attempt)
    design.selected_solar_cells = 5  # default is 0 -> power margin would always be negative
    await db.flush()

    await set_selected_steps(
        db, cohort_id=cohort.id, mission_id=mission.id,
        step_keys=["power_budget", "mass_budget"], created_by=author.id,
    )
    await db.commit()

    # Only components + power + mass filled in; CONOPS/data/cost/link left empty.
    dc = await design_service.add_component(db, design_id=design.id, library_component_id=library.id, quantity=1)
    await design_service.save_power_entry(db, design_component_id=dc.id, voltage_v=5.0, current_ma=100.0)
    await design_service.save_mass_entry(db, design_component_id=dc.id)

    dashboard = await design_service.compute_dashboard(db, design=design, variant_config=variant.config, attempt=attempt)
    assert dashboard["included_steps"] == {"components", "power_budget", "mass_budget"}
    # CONOPS was never touched — orbit_duration_min is still the Design
    # row's default (0), so it's genuinely *invalid*, not just unfilled.
    # all_valid must still be True: CONOPS is excluded from this cohort's
    # selection, so its own validity is irrelevant to completion.
    assert dashboard["steps"]["conops"]["is_valid"] is False
    assert dashboard["steps"]["power_budget"]["is_valid"] is True
    assert dashboard["steps"]["mass_budget"]["is_valid"] is True
    assert dashboard["all_valid"] is True, dashboard["steps"]


@pytest.mark.asyncio
async def test_downlink_only_counts_when_data_link_and_conops_are_all_selected(db):
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    student = await _user(db)
    library = await _library_component(db)
    cohort = await _cohort(db)

    attempt = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variant.id)
    attempt.cohort_id = cohort.id
    await db.flush()
    design = await ensure_design(db, attempt=attempt)
    await _build_passing_design(db, design.id, library.id)  # every step genuinely valid

    from app.services.missions.step_selection import set_selected_steps

    await set_selected_steps(
        db, cohort_id=cohort.id, mission_id=mission.id,
        step_keys=["data_budget", "link_budget", "conops"], created_by=author.id,
    )
    await db.commit()
    dashboard = await design_service.compute_dashboard(db, design=design, variant_config=variant.config, attempt=attempt)
    assert dashboard["downlink_included"] is True
    assert dashboard["all_valid"] is True  # downlink itself is genuinely valid here too

    # Drop CONOPS -> downlink no longer counts, even with data+link still selected.
    await set_selected_steps(
        db, cohort_id=cohort.id, mission_id=mission.id,
        step_keys=["data_budget", "link_budget"], created_by=author.id,
    )
    await db.commit()
    dashboard2 = await design_service.compute_dashboard(db, design=design, variant_config=variant.config, attempt=attempt)
    assert dashboard2["downlink_included"] is False
    assert dashboard2["all_valid"] is True  # data+link+components alone are valid; downlink silently dropped


@pytest.mark.asyncio
async def test_link_budget_f6_regression_unsaved_entry_is_not_valid_through_the_real_db_path(db):
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    student = await _user(db)
    attempt = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variant.id)
    design = await ensure_design(db, attempt=attempt)

    dashboard = await design_service.compute_dashboard(db, design=design, variant_config=variant.config)
    assert dashboard["link"].has_data is False
    assert dashboard["steps"]["link_budget"]["is_valid"] is False

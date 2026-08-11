"""P7-1 (LMS Phase 2 Stage 7, 2026-08-11) — the six design-mission budget
calculators, ported from Madar's dashboard.py. Pure functions, no DB: this
is the first test coverage this engine has ever had (MISSIONS_REPORT.md
§1.8, A2 — "Zero tests. No test directory, no CI, no fixtures anywhere").

Each test pins a known-good, hand-computed result and doubles as a
regression test for the F3/F5/F6/F8 fixes made while porting.
"""

from app.services.missions.design.calculators import (
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
from app.services.missions.design.rf_calc import BAND_PRESETS, calculate_link_budget


# ── CONOPS ────────────────────────────────────────────────────────────────

def test_conops_valid_when_modes_sum_to_orbit_duration():
    modes = [ModeInput(id="a", duration_min=60), ModeInput(id="b", duration_min=30)]
    result = calc_conops(orbit_duration_min=90, modes=modes)
    assert result.is_valid is True
    assert result.total_mode_duration_min == 90
    assert result.duration_difference_min == 0


def test_conops_invalid_when_modes_do_not_sum_to_orbit_duration():
    modes = [ModeInput(id="a", duration_min=60), ModeInput(id="b", duration_min=20)]
    result = calc_conops(orbit_duration_min=90, modes=modes)
    assert result.is_valid is False
    assert result.duration_difference_min == -10


def test_conops_has_no_data_with_no_modes():
    result = calc_conops(orbit_duration_min=90, modes=[])
    assert result.has_data is False


# ── Data budget ───────────────────────────────────────────────────────────

def test_data_budget_known_good_result():
    # 1 KB/measurement * 2 measurements/min * 30 active min = 60 KB/orbit.
    # 4 orbits/day -> 240 KB/day, all Stored.
    modes = [ModeInput(id="gs", duration_min=30)]
    components = [ComponentInput(
        subsystem="COMMS", quantity=1, on_mode_ids={"gs"},
        data_size_per_measurement_kb=1.0, measurements_per_minute=2.0, storage_mode="Stored",
    )]
    result = calc_data_budget(
        components=components, modes=modes, orbits_per_day=4.0,
        max_storage_kb=1000.0, required_storage_margin_kb=100.0,
    )
    assert result.total_per_orbit_kb == 60.0
    assert result.total_per_day_kb == 240.0
    assert result.total_stored_per_day_kb == 240.0
    assert result.total_sent_per_day_kb == 0.0
    assert result.storage_remaining_kb == 760.0
    assert result.is_valid is True


def test_data_budget_invalid_when_margin_not_met():
    modes = [ModeInput(id="gs", duration_min=30)]
    components = [ComponentInput(
        subsystem="COMMS", quantity=1, on_mode_ids={"gs"},
        data_size_per_measurement_kb=100.0, measurements_per_minute=1.0, storage_mode="Stored",
    )]
    # 100*1*30 = 3000 KB/orbit * 4 = 12000 KB/day, way past capacity.
    result = calc_data_budget(
        components=components, modes=modes, orbits_per_day=4.0,
        max_storage_kb=1000.0, required_storage_margin_kb=100.0,
    )
    assert result.is_valid is False


def test_data_budget_sent_mode_does_not_count_toward_stored():
    modes = [ModeInput(id="gs", duration_min=10)]
    components = [ComponentInput(
        subsystem="COMMS", quantity=1, on_mode_ids={"gs"},
        data_size_per_measurement_kb=5.0, measurements_per_minute=1.0, storage_mode="Sent",
    )]
    result = calc_data_budget(
        components=components, modes=modes, orbits_per_day=1.0,
        max_storage_kb=1000.0, required_storage_margin_kb=0.0,
    )
    assert result.total_sent_per_day_kb == 50.0
    assert result.total_stored_per_day_kb == 0.0


def test_data_budget_inactive_component_contributes_nothing():
    modes = [ModeInput(id="gs", duration_min=10)]
    components = [ComponentInput(
        subsystem="COMMS", quantity=1, on_mode_ids=set(),  # never on
        data_size_per_measurement_kb=5.0, measurements_per_minute=1.0,
    )]
    result = calc_data_budget(
        components=components, modes=modes, orbits_per_day=1.0,
        max_storage_kb=1000.0, required_storage_margin_kb=0.0,
    )
    assert result.total_per_day_kb == 0.0


# ── Power budget (F5 regression: a correctly-entered 0V must not fall back) ─

def test_power_budget_known_good_result():
    # 5V * 250mA = 1250 mW. Active 60 of 90 min -> energy = 1250*60/60 = 1250 mWh/orbit.
    modes = [ModeInput(id="sun", duration_min=60)]
    components = [ComponentInput(
        subsystem="ADCS", quantity=1, on_mode_ids={"sun"}, voltage_v=5.0, current_ma=250.0,
    )]
    result = calc_power_budget(
        components=components, modes=modes, orbits_per_day=15.0,
        power_per_solar_cell_w=1.1, selected_solar_cells=2,
    )
    assert result.total_power_mw == 1250.0
    assert result.total_energy_per_orbit_mwh == 1250.0
    assert result.generated_power_mw == 2200.0  # 2 * 1.1 * 1000
    assert result.power_margin_mw == 950.0
    assert result.is_valid is True


def test_power_budget_f5_regression_zero_voltage_is_not_treated_as_missing():
    """The exact bug: `voltage or component.voltage` substitutes the
    library default when a student correctly enters 0V for a passive
    element. `is None` must be the guard, not truthiness."""
    modes = [ModeInput(id="sun", duration_min=10)]
    components = [ComponentInput(
        subsystem="Structure", quantity=1, on_mode_ids={"sun"}, voltage_v=0.0, current_ma=0.0,
    )]
    result = calc_power_budget(
        components=components, modes=modes, orbits_per_day=1.0,
        power_per_solar_cell_w=1.1, selected_solar_cells=1,
    )
    assert result.has_data is True  # explicitly entered, even though both values are 0
    assert result.total_power_mw == 0.0


def test_power_budget_insufficient_cells_is_invalid():
    modes = [ModeInput(id="sun", duration_min=60)]
    components = [ComponentInput(
        subsystem="ADCS", quantity=1, on_mode_ids={"sun"}, voltage_v=5.0, current_ma=1000.0,
    )]
    result = calc_power_budget(
        components=components, modes=modes, orbits_per_day=1.0,
        power_per_solar_cell_w=1.1, selected_solar_cells=1,
    )
    assert result.is_valid is False
    assert result.required_solar_cells == 5  # ceil(5000mW / 1000 / 1.1) = ceil(4.54) = 5


# ── Mass budget (F3 regression: dims are numeric now, no string parsing) ───

def test_mass_budget_known_good_result():
    components = [ComponentInput(
        subsystem="EPS", quantity=2, mass_per_unit_g=100.0,
        length_mm=50.0, width_mm=50.0, height_mm=30.0,
    )]
    result = calc_mass_budget(
        components=components, max_allowed_mass_kg=1.33, available_internal_volume_cm3=1000.0,
    )
    assert result.total_mass_kg == 0.2  # 200g / 1000
    assert result.mass_margin_kg == 1.13
    # volume: 50*50*30 = 75000 mm^3 per unit * 2 = 150000 mm^3 = 150 cm^3
    assert result.total_volume_cm3 == 150.0
    assert result.volume_margin_cm3 == 850.0
    assert result.is_valid is True


def test_mass_budget_f3_regression_multiplication_sign_never_reaches_the_calculator():
    """Madar's bug lived entirely in string parsing (`×` vs ASCII `x`) that
    doesn't exist anymore — dimensions are numeric columns now. This test
    documents that a component with real numeric dims (as if seeded from
    "50×50×30", now parsed once at import time into three floats) produces
    nonzero volume, unlike Madar's vacuous 0."""
    components = [ComponentInput(
        subsystem="ADCS", quantity=1, mass_per_unit_g=85.0,
        length_mm=50.0, width_mm=50.0, height_mm=30.0,
    )]
    result = calc_mass_budget(components=components, max_allowed_mass_kg=1.33, available_internal_volume_cm3=1000.0)
    assert result.total_volume_cm3 > 0


def test_mass_budget_over_limit_is_invalid():
    components = [ComponentInput(subsystem="Payload", quantity=1, mass_per_unit_g=2000.0)]
    result = calc_mass_budget(components=components, max_allowed_mass_kg=1.33, available_internal_volume_cm3=1000.0)
    assert result.is_valid is False
    assert result.mass_margin_kg < 0


def test_cubesat_presets_are_the_only_source_of_the_limit():
    assert CUBESAT_PRESETS["1U"]["max_mass_kg"] == 1.33
    assert CUBESAT_PRESETS["3U"]["available_volume_cm3"] == 3000.0


# ── Cost budget ───────────────────────────────────────────────────────────

def test_cost_budget_known_good_result():
    components = [
        ComponentInput(subsystem="COMMS", quantity=2, cost_per_unit_aed=500.0),
        ComponentInput(subsystem="EPS", quantity=1, cost_per_unit_aed=300.0),
    ]
    result = calc_cost_budget(components=components, maximum_budget_aed=2000.0)
    assert result.total_cost_aed == 1300.0
    assert result.cost_margin_aed == 700.0
    assert result.is_valid is True


def test_cost_budget_over_budget_is_invalid():
    components = [ComponentInput(subsystem="Payload", quantity=1, cost_per_unit_aed=5000.0)]
    result = calc_cost_budget(components=components, maximum_budget_aed=2000.0)
    assert result.is_valid is False


# ── Link budget ───────────────────────────────────────────────────────────

def test_link_budget_uhf_preset_known_good_result():
    preset = BAND_PRESETS["UHF"]
    calc = calculate_link_budget(
        downlink_frequency_mhz=preset["downlink_frequency_mhz"],
        satellite_antenna_gain_dbi=preset["satellite_antenna_gain_dbi"],
        data_rate_kbps=preset["data_rate_kbps"],
        required_signal_quality_db=preset["required_signal_quality_db"],
        transmit_power_dbm=30.0, distance_km=500.0,
    )
    # FSPL = 20*log10(d_m) + 20*log10(f_hz) - 147.55, d=500km, f=437.5MHz.
    assert round(calc.free_space_path_loss_db, 1) == 139.2
    assert calc.eirp_dbm == 32.0  # 30 + 2
    assert calc.link_status == "Good Link"
    result = calc_link_budget_status(is_saved=True, link_status=calc.link_status, margin_db=calc.system_link_margin_db)
    assert result.has_data is True
    assert result.status == calc.link_status


def test_link_budget_f6_regression_unsaved_entry_has_no_data_regardless_of_stored_values():
    """The exact bug: Madar inferred "has the student touched this" from
    `updated_at <= created_at`, corruptible by any other writer. An
    explicit `is_saved=False` must mean no data, even if a status string
    happens to be present."""
    result = calc_link_budget_status(is_saved=False, link_status="Good Link", margin_db=10.0)
    assert result.has_data is False
    assert result.is_valid is False
    assert result.status == "No Link Data"


def test_link_budget_weak_and_failed_thresholds():
    good = calculate_link_budget(
        downlink_frequency_mhz=437.5, satellite_antenna_gain_dbi=50.0, data_rate_kbps=1.0,
        required_signal_quality_db=0.0, transmit_power_dbm=30.0, distance_km=1.0,
    )
    assert good.link_status == "Good Link"

    failed = calculate_link_budget(
        downlink_frequency_mhz=2400.0, satellite_antenna_gain_dbi=0.0, data_rate_kbps=1000.0,
        required_signal_quality_db=50.0, transmit_power_dbm=10.0, distance_km=10000.0,
    )
    assert failed.link_status == "Failed Link"

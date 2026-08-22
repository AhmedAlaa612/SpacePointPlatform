"""Design v2 (7D-2) — the two cross-checks Madar left open, plus the
content and report layers, as pure functions.

`MISSIONS_MADAR_GAP.md` §3.5 recorded both F7 and F8 as still open in the
port: `total_sent_per_day_kb` was computed and compared against nothing, and
`total_energy_per_orbit_mwh` was computed and discarded. These tests are the
regression suite for closing them.

The headline case is the one the audit named: **500 MB/day over a 9,600 bps
UHF radio used to pass every check.** It cannot now.
"""

import pytest

from app.services.missions.design import content, report
from app.services.missions.design.calculators import (
    ComponentInput,
    ModeInput,
    calc_downlink_budget,
    calc_energy_budget,
)

# A 90-minute orbit split the way the default CONOPS does: sun pointing,
# nadir pointing, an 8-minute ground station pass, and eclipse.
SUN, NADIR, GS, ECLIPSE = "sun", "nadir", "gs", "ecl"
MODES = [
    ModeInput(SUN, 40.0, 0),
    ModeInput(NADIR, 20.0, 1),
    ModeInput(GS, 8.0, 2),
    ModeInput(ECLIPSE, 22.0, 3),
]


def component(*, on: set[str], v: float = 5.0, ma: float = 200.0) -> ComponentInput:
    return ComponentInput(subsystem="EPS", quantity=1, on_mode_ids=on, voltage_v=v, current_ma=ma)


# ── F7: data ↔ link ↔ CONOPS ─────────────────────────────────────────────

def test_the_case_the_audit_named_now_fails():
    """500 MB/day over UHF at 9.6 kbps. Madar passed it; so did the port."""
    result = calc_downlink_budget(
        total_sent_per_day_kb=500_000, orbits_per_day=15, modes=MODES,
        data_rate_kbps=9.6, link_is_saved=True,
    )
    assert result.is_valid is False
    assert result.utilisation_pct > 100
    # 9.6 kbps x 8 min x 60 / 8 = 576 KB per pass
    assert result.downlink_capacity_per_orbit_kb == pytest.approx(576.0, abs=1.0)
    assert result.contact_minutes == 8.0


def test_a_realistic_s_band_design_passes():
    result = calc_downlink_budget(
        total_sent_per_day_kb=20_000, orbits_per_day=15, modes=MODES,
        data_rate_kbps=1000.0, link_is_saved=True,
    )
    assert result.is_valid is True
    assert result.downlink_margin_kb > 0


def test_a_longer_ground_station_window_buys_capacity():
    """One of the three real trades: collect less, transmit faster, or
    spend longer over the station."""
    short = calc_downlink_budget(
        total_sent_per_day_kb=15_000, orbits_per_day=15, modes=MODES,
        data_rate_kbps=10.0, link_is_saved=True,
    )
    longer = calc_downlink_budget(
        total_sent_per_day_kb=15_000, orbits_per_day=15,
        modes=[ModeInput(SUN, 30.0, 0), ModeInput(NADIR, 18.0, 1), ModeInput(GS, 20.0, 2), ModeInput(ECLIPSE, 22.0, 3)],
        data_rate_kbps=10.0, link_is_saved=True,
    )
    assert longer.downlink_capacity_per_orbit_kb > short.downlink_capacity_per_orbit_kb
    assert short.is_valid is False and longer.is_valid is True


def test_sending_nothing_is_a_failure_not_a_pass():
    """Marking every component 'Stored' must not be a way to skip the
    check. A spacecraft that never downlinks has no mission."""
    result = calc_downlink_budget(
        total_sent_per_day_kb=0, orbits_per_day=15, modes=MODES,
        data_rate_kbps=1000.0, link_is_saved=True,
    )
    assert result.has_data is True   # there is a link, so it is evaluable
    assert result.is_valid is False  # and it fails


def test_no_link_budget_means_not_yet_evaluable():
    result = calc_downlink_budget(
        total_sent_per_day_kb=1000, orbits_per_day=15, modes=MODES,
        data_rate_kbps=None, link_is_saved=False,
    )
    assert result.has_data is False


def test_required_margin_reserves_headroom():
    tight = calc_downlink_budget(
        total_sent_per_day_kb=7_500, orbits_per_day=15, modes=MODES,
        data_rate_kbps=10.0, link_is_saved=True, required_margin_fraction=0.0,
    )
    strict = calc_downlink_budget(
        total_sent_per_day_kb=7_500, orbits_per_day=15, modes=MODES,
        data_rate_kbps=10.0, link_is_saved=True, required_margin_fraction=0.5,
    )
    assert tight.is_valid is True
    assert strict.is_valid is False


# ── F8: energy over an orbit, and the battery ────────────────────────────

def test_sunlit_time_comes_from_the_students_own_conops():
    result = calc_energy_budget(
        components=[component(on={SUN})], modes=MODES, orbit_duration_min=90.0,
        generated_power_mw=2000.0, battery_capacity_wh=10.0,
    )
    assert result.eclipse_minutes == 22.0
    assert result.sunlit_minutes == 68.0


def test_an_array_sized_for_peak_can_still_fail_the_orbit():
    """The lesson: passing the instantaneous power check says nothing about
    whether the orbit balances, because the array stops in eclipse."""
    always_on = [component(on={SUN, NADIR, GS, ECLIPSE}, v=5.0, ma=400.0)]
    result = calc_energy_budget(
        components=always_on, modes=MODES, orbit_duration_min=90.0,
        generated_power_mw=2100.0, battery_capacity_wh=20.0,
    )
    assert result.energy_balance_ok is False
    assert result.energy_margin_mwh < 0


def test_turning_the_payload_off_in_eclipse_fixes_both_checks():
    always_on = [component(on={SUN, NADIR, GS, ECLIPSE}, v=5.0, ma=400.0)]
    duty_cycled = [component(on={SUN, NADIR, GS}, v=5.0, ma=400.0)]
    bad = calc_energy_budget(components=always_on, modes=MODES, orbit_duration_min=90.0,
                             generated_power_mw=2100.0, battery_capacity_wh=20.0)
    good = calc_energy_budget(components=duty_cycled, modes=MODES, orbit_duration_min=90.0,
                              generated_power_mw=2100.0, battery_capacity_wh=20.0)
    assert bad.is_valid is False
    assert good.is_valid is True
    assert good.eclipse_draw_mwh == 0.0
    assert good.depth_of_discharge_pct == 0.0


def test_depth_of_discharge_is_a_separate_failure_from_energy_balance():
    """A design can generate plenty over an orbit and still ruin its
    battery every eclipse."""
    result = calc_energy_budget(
        components=[component(on={SUN, NADIR, GS, ECLIPSE}, v=5.0, ma=300.0)],
        modes=MODES, orbit_duration_min=90.0,
        generated_power_mw=8000.0,   # a very generous array
        battery_capacity_wh=0.5,     # and a tiny battery
    )
    assert result.energy_balance_ok is True
    assert result.depth_of_discharge_ok is False
    assert result.is_valid is False


def test_the_dod_limit_is_variant_owned():
    args = dict(
        components=[component(on={SUN, ECLIPSE}, v=5.0, ma=200.0)],
        modes=MODES, orbit_duration_min=90.0, generated_power_mw=4000.0, battery_capacity_wh=2.0,
    )
    lenient = calc_energy_budget(**args, max_depth_of_discharge_pct=40.0)
    strict = calc_energy_budget(**args, max_depth_of_discharge_pct=5.0)
    assert lenient.depth_of_discharge_ok is True
    assert strict.depth_of_discharge_ok is False


def test_no_battery_means_the_step_is_not_started():
    result = calc_energy_budget(
        components=[component(on={SUN})], modes=MODES, orbit_duration_min=90.0,
        generated_power_mw=2000.0, battery_capacity_wh=None,
    )
    assert result.has_data is False
    assert result.is_valid is False


def test_a_zero_current_component_is_not_treated_as_missing():
    """F5's `is None` discipline, carried into the new calculator."""
    result = calc_energy_budget(
        components=[ComponentInput(subsystem="STR", quantity=1, on_mode_ids={SUN}, voltage_v=0.0, current_ma=0.0)],
        modes=MODES, orbit_duration_min=90.0, generated_power_mw=2000.0, battery_capacity_wh=10.0,
    )
    assert result.has_data is True
    assert result.consumed_per_orbit_mwh == 0.0


# ── The report layer (7D-3) ──────────────────────────────────────────────

def _dash(**over):
    """A minimal dashboard dict shaped like `compute_dashboard`'s output."""
    from app.services.missions.design.calculators import (
        calc_conops, calc_cost_budget, calc_data_budget, calc_link_budget_status,
        calc_mass_budget, calc_power_budget,
    )
    comps = over.pop("components", [component(on={SUN, NADIR, GS})])
    data = calc_data_budget(components=comps, modes=MODES, orbits_per_day=15,
                            max_storage_kb=1_000_000, required_storage_margin_kb=0)
    power = calc_power_budget(components=comps, modes=MODES, orbits_per_day=15,
                              power_per_solar_cell_w=1.1, selected_solar_cells=5)
    dash = {
        "conops": calc_conops(orbit_duration_min=90.0, modes=MODES),
        "data": data, "power": power,
        "mass": calc_mass_budget(components=comps, max_allowed_mass_kg=1.33,
                                 available_internal_volume_cm3=1000.0),
        "cost": calc_cost_budget(components=comps, maximum_budget_aed=2000.0),
        "link": calc_link_budget_status(is_saved=True, link_status="Good Link", margin_db=6.0),
        "downlink": calc_downlink_budget(total_sent_per_day_kb=0, orbits_per_day=15, modes=MODES,
                                         data_rate_kbps=9.6, link_is_saved=True),
        "energy": calc_energy_budget(components=comps, modes=MODES, orbit_duration_min=90.0,
                                     generated_power_mw=power.generated_power_mw, battery_capacity_wh=10.0),
        "all_valid": False,
        "steps": {},
    }
    dash.update(over)
    return dash


THRESHOLDS = {"max_storage_kb": 1_000_000, "maximum_budget_aed": 2000.0}
LIMITS = {"max_mass_kg": 1.33, "available_volume_cm3": 1000.0}

# The unfiltered case — every step in scope, matching a cohort/solo run with
# no MissionStepSelection configured (report.py's own "all included" default).
ALL_STEPS = frozenset({
    "components", "conops", "data_budget", "power_budget", "energy_budget",
    "link_budget", "downlink", "mass_budget", "cost_budget",
})


def test_every_margin_carries_an_interpretation():
    """The half of Madar's dashboard the port dropped: the numbers were
    always there, the judgement was not."""
    margins = report.build_margins(_dash(), THRESHOLDS, LIMITS, ALL_STEPS)
    assert len(margins) >= 9
    for row in margins:
        assert row["interpretation"], row["key"]
        assert row["status"] in {"good", "tight", "fail", "incomplete"}


def test_a_failing_margin_produces_an_alert_and_a_recommendation():
    dash = _dash(components=[component(on={SUN, NADIR, GS, ECLIPSE}, v=12.0, ma=900.0)])
    margins = report.build_margins(dash, THRESHOLDS, LIMITS, ALL_STEPS)
    alerts, recs = report.build_advice(dash, margins, ALL_STEPS)
    assert any(a["severity"] == "error" for a in alerts)
    assert recs, "a failing design should be told what to change"
    assert all(r["message"] and r["why"] for r in recs)


def test_recommendations_come_from_the_shared_mistake_library():
    """So the dashboard's advice and the handbook can never disagree."""
    dash = _dash(components=[component(on={SUN, NADIR, GS, ECLIPSE}, v=12.0, ma=900.0)])
    margins = report.build_margins(dash, THRESHOLDS, LIMITS, ALL_STEPS)
    _, recs = report.build_advice(dash, margins, ALL_STEPS)
    known = {m["key"] for m in content.MISTAKES} | {"tight_margins"}
    assert {r["key"] for r in recs} <= known


def test_overall_status_counts_what_is_wrong():
    dash = _dash()
    margins = report.build_margins(dash, THRESHOLDS, LIMITS, ALL_STEPS)
    overall = report.overall_status(dash, margins)
    assert overall["label"] in {"Ready", "Ready — margins tight", "Invalid design", "Incomplete"}
    assert overall["errors"] + overall["warnings"] + overall["incomplete"] >= 0


def test_module_cards_point_at_a_tab_to_fix_it():
    dash = _dash()
    dash["steps"] = {k: {"has_data": True, "is_valid": True} for k in
                     ("components", "conops", "data_budget", "power_budget", "energy_budget",
                      "link_budget", "downlink", "mass_budget", "cost_budget")}
    cards = report.build_module_cards(dash, THRESHOLDS, 1, ALL_STEPS)
    assert len(cards) == 9
    assert all(c["tab"] for c in cards)


def test_module_cards_and_margins_are_filtered_to_the_cohorts_selected_steps():
    """A cohort run that only selected components/conops/link_budget should
    not see power/mass/cost/data rows at all — this is the actual fix for
    the live bug (2026-08-22): a 3-step student run was showing all 9
    categories, including a "Power budget: FAIL" card for a step the
    student never had access to."""
    dash = _dash(components=[component(on={SUN, NADIR, GS, ECLIPSE}, v=12.0, ma=900.0)])
    dash["steps"] = {k: {"has_data": True, "is_valid": True} for k in
                     ("components", "conops", "data_budget", "power_budget", "energy_budget",
                      "link_budget", "downlink", "mass_budget", "cost_budget")}
    scoped = frozenset({"components", "conops", "link_budget"})

    margins = report.build_margins(dash, THRESHOLDS, LIMITS, scoped)
    assert {m["key"] for m in margins} == {"link"}

    cards = report.build_module_cards(dash, THRESHOLDS, 1, scoped)
    assert {c["key"] for c in cards} == {"components", "conops", "link_budget"}

    # Unscoped, this overloaded design fails power — with the cards/margins
    # above proving that step isn't in scope, the alerts and recommendations
    # built from the *scoped* margins must not mention it either.
    full_margins = report.build_margins(dash, THRESHOLDS, LIMITS, ALL_STEPS)
    assert "power" in {m["key"] for m in full_margins if m["status"] == "fail"}

    alerts, recs = report.build_advice(dash, margins, scoped)
    assert not any(a["step"] == "power" for a in alerts)
    assert "array_sized_for_peak" not in {r["key"] for r in recs}


def test_charts_aggregate_by_subsystem():
    class Row:
        def __init__(self, subsystem, v, ma, mass, cost):
            self.subsystem, self.voltage_v, self.current_ma = subsystem, v, ma
            self.mass_per_unit_g, self.cost_per_unit_aed, self.quantity = mass, cost, 1

    charts = report.build_charts(
        [Row("EPS", 5, 100, 50, 200), Row("ADCS", 3.3, 50, 20, 400), Row("EPS", 5, 50, 10, 100)],
        [],
    )
    eps = next(c for c in charts["power_by_subsystem"] if c["subsystem"] == "EPS")
    assert eps["value"] == pytest.approx(5 * 100 + 5 * 50)
    assert len(charts["mass_by_subsystem"]) == 2


# ── Content (7D-4 / 7D-5 / D8) ───────────────────────────────────────────

def test_the_handbook_covers_every_step_the_dashboard_can_fail():
    """A budget with no handbook entry is unteachable."""
    keys = {b["key"] for b in content.BUDGETS}
    assert {"conops", "data_budget", "power_budget", "energy_budget",
            "link_budget", "downlink", "mass_budget", "cost_budget"} <= keys


def test_every_mistake_points_at_real_steps():
    step_keys = {s["key"] for s in content.STEP_ORDER}
    for mistake in content.MISTAKES:
        assert set(mistake["steps"]) <= step_keys, mistake["key"]


def test_disclosure_scales_what_is_written_down():
    full = content.handbook(disclosure="full")
    symptoms = content.handbook(disclosure="symptoms")
    reference = content.handbook(disclosure="reference")

    assert all("fix" in b for b in full["budgets"])
    assert all("fix" not in b for b in symptoms["budgets"])
    assert all("means" in b for b in symptoms["budgets"])
    assert all("means" not in b for b in reference["budgets"])
    # The formula and what it checks are never withheld — knowing a budget
    # exists is not the puzzle.
    assert all(b["formula"] and b["checks"] for b in reference["budgets"])


def test_all_eight_madar_data_types_survive():
    names = {d["name"] for d in content.DATA_TYPES}
    assert {"Telemetry", "Image", "Science Data", "Video", "Housekeeping",
            "GPS/Nav", "Telemetry and Commands", "TT&C"} == names


def test_authored_overrides_replace_only_what_they_name():
    base = content.handbook(disclosure="full")
    merged = content.apply_overrides(base, {
        "what_is_a_budget": "Custom explanation.",
        "budgets": {"conops": {"fix": "Custom fix."}},
    })
    assert merged["what_is_a_budget"] == "Custom explanation."
    conops = next(b for b in merged["budgets"] if b["key"] == "conops")
    assert conops["fix"] == "Custom fix."
    assert conops["formula"] == next(b for b in base["budgets"] if b["key"] == "conops")["formula"]


def test_overrides_cannot_invent_or_reshape_content():
    """An allowlist, not a free-form merge: a bad edit can garble wording
    but never add a step or change a formula the calculators use."""
    base = content.handbook(disclosure="full")
    merged = content.apply_overrides(base, {
        "budgets": {"conops": {"formula": "1 + 1 = 3", "key": "hacked"}},
        "steps": [{"key": "invented"}],
    })
    conops = next(b for b in merged["budgets"] if b["key"] == "conops")
    assert conops["formula"] != "1 + 1 = 3"
    assert len(merged["budgets"]) == len(base["budgets"])


def test_empty_overrides_leave_the_defaults_untouched():
    base = content.handbook(disclosure="full")
    assert content.apply_overrides(base, {}) == base
    assert content.apply_overrides(base, None) == base


def test_editable_content_shows_the_default_alongside_the_override():
    editable = content.editable_content({"what_is_a_budget": "Mine."})
    assert editable["what_is_a_budget"]["value"] == "Mine."
    assert editable["what_is_a_budget"]["overridden"] is True
    assert editable["what_is_a_budget"]["default"] == content.WHAT_IS_A_BUDGET
    assert len(editable["budgets"]) == len(content.BUDGETS)


def test_assumptions_are_stated_not_hidden():
    """F9 — the audit's complaint was that the link budget reported
    'Good Link' as though it were authoritative."""
    joined = " ".join(content.ASSUMPTIONS).lower()
    assert "ground-station antenna gain" in joined
    assert "290 k" in joined
    assert "packing factor" in joined

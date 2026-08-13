"""Operate v2 (Stage 7C) — the simulation core, tested as pure functions.

No database, no clock, no fixtures: a list of `(sim_t, command)` pairs goes
in and an asserted spacecraft state comes out. That testability is the main
practical dividend of making the simulator a deterministic replay rather
than a mutable session object, and it is why these tests can assert on
physics rather than on plumbing.

The first block is the regression suite for the v1 scoring exploits, which
were verified against the shipped code before this rewrite:

  * ending the session with no commands scored 100% and **passed on the
    hardest variant with full points**, because score was "percent of
    *triggered* anomalies resolved" and nothing had triggered;
  * typing the fix commands twice scored 100% without reading a single
    telemetry channel.

Neither is patched — both are structurally impossible now, and these tests
exist to keep it that way.
"""

import pytest

from app.services.missions.operate.anomalies import LIBRARY, handbook
from app.services.missions.operate.commands import CATALOG, parse
from app.services.missions.operate.crew import ROLE_COMMANDS, is_command_allowed
from app.services.missions.operate.evaluator import evaluate
from app.services.missions.operate.orbit import (
    OrbitModel,
    orbit_summary,
    phase_at,
    signal_strength_dbm,
)
from app.services.missions.operate.spacecraft import (
    MODE_SAFE,
    PAYLOAD_OFF,
    SpacecraftParams,
    schedule_injected_faults,
    simulate,
)
from app.services.missions.operate.telemetry import (
    channel_status,
    compute_telemetry,
    subsystem_detail,
    subsystem_health,
)

ORBIT = OrbitModel(orbits=3)
PARAMS = SpacecraftParams()
P = ORBIT.period_seconds


def cmd(t, base, arg=""):
    return {"sim_t": t, "base": base, "arg": arg}


def fly(commands, *, orbit=ORBIT, params=PARAMS, until=None, injected=None, config=None):
    injected = injected if injected is not None else schedule_injected_faults(orbit, config or {}, seed=0)
    return simulate(
        orbit=orbit, params=params, commands=sorted(commands, key=lambda c: c["sim_t"]),
        until_t=orbit.session_seconds if until is None else until, injected=injected,
    )


def competent_flight(orbit=ORBIT, injected=None):
    """A flight flown properly: duty-cycle the payload, downlink during the
    pass, desaturate between passes, fix faults when they appear."""
    injected = injected if injected is not None else schedule_injected_faults(orbit, {}, seed=0)
    period = orbit.period_seconds
    out = []
    for i in range(orbit.orbits):
        b = i * period
        out += [
            cmd(b + 30, "PAYLOAD_ON"), cmd(b + 90, "COLLECT_SAMPLE"),
            cmd(b + 500, "COLLECT_SAMPLE"), cmd(b + 1000, "PAYLOAD_OFF"),
            cmd(b + 0.42 * period + 15, "DOWNLINK_SCIENCE"),
            cmd(b + 0.42 * period + 470, "DOWNLINK_STOP"),
            cmd(b + 0.62 * period, "ADCS_DESAT"),
        ]
    fixes = {"seu": ("RESET_WDT", ""), "beacon_lock": ("UPDATE_BEACON", "30")}
    for f in injected:
        base, arg = fixes[f.key]
        out.append(cmd(f.at_t + 40, base, arg))
        if f.key == "beacon_lock":
            out.append(cmd(f.at_t + 70, "DOWNLINK_SCIENCE"))
    return out, injected


# --------------------------------------------------------------------------
# Regressions on the v1 scoring exploits
# --------------------------------------------------------------------------

def test_doing_nothing_fails_the_mission():
    """v1's headline bug: end immediately, score 100%, pass with full points.

    Now, doing nothing means no science collected, nothing downlinked, and a
    battery that drains through eclipse until the spacecraft safes itself.
    No minimum-engagement guard is involved — the objectives simply aren't met.
    """
    result = fly([])
    outcome = evaluate(state=result.state, params=PARAMS, config={}, penalties_seen=[], pass_threshold=65)

    assert outcome.passed is False
    assert outcome.score < 25
    assert result.state.science_takes == 0
    assert result.state.downlinked_mb == 0
    assert result.state.safe_mode_entries >= 1


def test_ending_a_flight_immediately_fails():
    """The exact v1 exploit: create an attempt, finish it at once."""
    result = fly([], until=1.0)
    outcome = evaluate(state=result.state, params=PARAMS, config={}, penalties_seen=[], pass_threshold=65)
    assert outcome.passed is False
    assert outcome.objectives_score < 60


def test_spamming_fix_commands_does_not_pass():
    """v1: repeating every fix command twice scored 100%. Here the fix
    commands don't touch the objectives at all, so blind spam gets nowhere."""
    spam = []
    for i in range(6):
        for base in ("EPS_RECONFIG", "RESET_WDT", "ADCS_RECALIBRATE", "PAYLOAD_RESET"):
            spam.append(cmd(60 + i * 300, base))
    result = fly(spam)
    outcome = evaluate(state=result.state, params=PARAMS, config={}, penalties_seen=[], pass_threshold=65)
    assert outcome.passed is False
    assert result.state.downlinked_mb == 0


def test_a_competent_flight_passes():
    commands, injected = competent_flight()
    result = fly(commands, injected=injected)
    outcome = evaluate(state=result.state, params=PARAMS, config={}, penalties_seen=[], pass_threshold=65)

    assert outcome.passed is True
    assert result.state.safe_mode_entries == 0
    assert result.state.science_takes >= 3
    assert result.state.downlinked_mb >= 60


# --------------------------------------------------------------------------
# Orbital mechanics — derived, not hardcoded
# --------------------------------------------------------------------------

def test_orbit_numbers_are_computed_from_real_mechanics():
    """SatKit displayed a literal '7.6 km/s' next to a literal '97.5 deg'.
    Both are right for 550 km, and now both are derived."""
    s = orbit_summary(ORBIT)
    assert 95.0 < s["period_minutes"] < 96.0
    assert 7.55 < s["velocity_km_s"] < 7.62
    assert 97.0 < s["inclination_deg"] < 98.2


def test_altitude_changes_the_orbit():
    low, high = OrbitModel(altitude_km=400.0), OrbitModel(altitude_km=800.0)
    assert low.period_seconds < high.period_seconds
    assert low.velocity_km_s > high.velocity_km_s


def test_eclipse_and_pass_windows_are_where_the_model_says():
    lit = phase_at(ORBIT, 0.1 * P)
    dark = phase_at(ORBIT, 0.9 * P)
    in_pass = phase_at(ORBIT, 0.46 * P)

    assert lit.sunlit and not dark.sunlit
    assert in_pass.in_pass and not lit.in_pass
    assert in_pass.elevation_deg > 0
    assert lit.seconds_to_eclipse > 0
    assert dark.seconds_to_sunrise > 0


def test_signal_rises_and_falls_across_a_pass():
    """A student watching this learns to plan work around the window."""
    start = signal_strength_dbm(phase_at(ORBIT, 0.421 * P))
    peak = signal_strength_dbm(phase_at(ORBIT, 0.462 * P))
    outside = signal_strength_dbm(phase_at(ORBIT, 0.2 * P))

    assert outside == -120.0
    assert peak > start > outside
    assert peak > -75.0


def test_orbit_number_advances():
    assert phase_at(ORBIT, 0.0).orbit_number == 1
    assert phase_at(ORBIT, P * 1.5).orbit_number == 2
    assert phase_at(ORBIT, P * 2.5).orbit_number == 3


# --------------------------------------------------------------------------
# The physics actually couples
# --------------------------------------------------------------------------

def test_payload_left_on_through_eclipse_drains_the_battery():
    """The power lesson, in one assertion: same spacecraft, same orbit, the
    only difference is whether the instrument was shut down before shadow."""
    careless = fly([])  # payload starts ON and is never touched
    careful = fly([cmd(30, "PAYLOAD_OFF")])
    assert careful.state.min_soc_seen > careless.state.min_soc_seen + 0.2


def test_undervoltage_safes_the_spacecraft_autonomously():
    result = fly([])
    assert result.state.mode == MODE_SAFE
    assert result.state.payload_state == PAYLOAD_OFF
    assert any(f.key == "safe_mode" for f in result.state.faults)


def test_cannot_leave_safe_mode_until_the_battery_recovers():
    """You can't command your way out of a power problem — you have to fix
    the power. Trying early is refused and carries a penalty."""
    safed = fly([])
    assert safed.state.mode == MODE_SAFE
    entered = next(f for f in safed.state.faults if f.key == "safe_mode").raised_t

    result = fly([cmd(entered + 30, "EXIT_SAFE_MODE")])
    assert result.state.mode == MODE_SAFE
    assert any(r.penalty == "premature_safe_exit" for r in result.command_results)


def test_wheel_saturates_if_never_desaturated_and_that_kills_the_downlink():
    saturated = fly([cmd(30, "PAYLOAD_OFF")])
    assert saturated.state.wheel_rpm >= PARAMS.wheel_max_rpm
    assert saturated.state.attitude_error_deg > 20
    assert saturated.state.link_ok is False


def test_desaturation_recovers_the_wheel():
    desat = fly([cmd(30, "PAYLOAD_OFF")] + [cmd(0.62 * P + i * P, "ADCS_DESAT") for i in range(3)])
    assert desat.state.wheel_rpm < PARAMS.wheel_warn_rpm


def test_desaturating_during_a_pass_breaks_pointing():
    """The reason the handbook says to do it between passes."""
    result = fly([cmd(0.43 * P, "ADCS_DESAT")], until=0.44 * P)
    assert result.state.attitude_error_deg > 5.0
    assert result.state.link_ok is False


def test_downlink_only_works_during_a_pass():
    outside = fly([cmd(0.2 * P, "DOWNLINK_SCIENCE")], until=0.3 * P)
    assert outside.state.downlinked_mb == 0
    assert any(r.penalty == "downlink_out_of_pass" for r in outside.command_results)


def test_science_downlinks_during_a_pass():
    result = fly([
        cmd(60, "COLLECT_SAMPLE"), cmd(120, "COLLECT_SAMPLE"),
        cmd(0.425 * P, "DOWNLINK_SCIENCE"),
    ], until=0.50 * P)
    assert result.state.downlinked_mb > 20
    assert result.state.storage_used_mb < 40


def test_mass_memory_fills_and_drops_science():
    """The data budget made visceral: generation is cheap, downlink is scarce."""
    collects = [cmd(60 + i * 40, "COLLECT_SAMPLE") for i in range(12)]
    result = fly(collects, until=0.4 * P)
    assert result.state.science_dropped > 0
    assert any(r.penalty == "data_loss" for r in result.command_results)


def test_collecting_needs_the_payload_powered():
    result = fly([cmd(30, "PAYLOAD_OFF"), cmd(60, "COLLECT_SAMPLE")], until=200)
    assert result.state.science_takes == 0
    assert result.command_results[-1].accepted is False


def test_payload_left_on_overheats_but_duty_cycling_does_not():
    hot = fly([], until=0.6 * P)
    cool = fly([cmd(400, "PAYLOAD_STANDBY")], until=0.6 * P)
    assert hot.state.payload_temp_c > PARAMS.payload_temp_limit_c
    assert cool.state.payload_temp_c < PARAMS.payload_temp_limit_c


# --------------------------------------------------------------------------
# Injected faults
# --------------------------------------------------------------------------

def test_seu_fires_in_the_south_atlantic_anomaly():
    """Not at an arbitrary clock time — which is the point of modelling
    the SAA at all."""
    injected = schedule_injected_faults(ORBIT, {"injected_faults": ["seu"]}, seed=0)
    seu = next(f for f in injected if f.key == "seu")
    assert phase_at(ORBIT, seu.at_t).in_saa is True


def test_ignoring_an_upset_latches_the_obc_and_only_a_reboot_clears_it():
    """The best teaching moment in the set: REBOOT_OBC is punished on first
    reach and *correct* on a recurring latch-up. The rule is conditional."""
    config = {"injected_faults": ["seu", "seu"], "shuffle_faults": False}
    injected = schedule_injected_faults(ORBIT, config, seed=0)
    assert len(injected) == 2

    ignored = fly([], injected=injected, config=config)
    assert ignored.state.obc_wedged is True

    second = injected[1].at_t
    reset_only = fly([cmd(second + 60, "RESET_WDT")], injected=injected, config=config)
    assert reset_only.state.obc_wedged is True  # a watchdog reset can't clear a latch-up

    rebooted = fly([cmd(second + 60, "REBOOT_OBC")], injected=injected, config=config)
    assert rebooted.state.obc_wedged is False


def test_rebooting_with_no_fault_is_penalised():
    result = fly([cmd(60, "REBOOT_OBC")], until=300)
    assert any(r.penalty == "needless_reboot" for r in result.command_results)


def test_beacon_failure_blocks_the_downlink_until_the_period_is_set():
    config = {"injected_faults": ["beacon_lock"], "shuffle_faults": False}
    injected = schedule_injected_faults(ORBIT, config, seed=0)
    at = injected[0].at_t

    ignored = fly([cmd(60, "COLLECT_SAMPLE"), cmd(at + 20, "DOWNLINK_SCIENCE")],
                  until=0.51 * P, injected=injected, config=config)
    assert ignored.state.downlinked_mb == 0

    fixed = fly([
        cmd(60, "COLLECT_SAMPLE"), cmd(at + 20, "UPDATE_BEACON", "30"), cmd(at + 30, "DOWNLINK_SCIENCE"),
    ], until=0.51 * P, injected=injected, config=config)
    assert fixed.state.downlinked_mb > 0


def test_update_beacon_requires_its_argument():
    """SatKit echoed the parameter back; v1 accepted it and silently dropped
    it. Here the period is the command."""
    config = {"injected_faults": ["beacon_lock"], "shuffle_faults": False}
    injected = schedule_injected_faults(ORBIT, config, seed=0)
    at = injected[0].at_t
    result = fly([cmd(at + 20, "UPDATE_BEACON")], until=at + 60, injected=injected, config=config)
    assert result.command_results[-1].accepted is False
    assert "period" in result.command_results[-1].message.lower()


# --------------------------------------------------------------------------
# Determinism, scheduling and difficulty (D-b, D-f)
# --------------------------------------------------------------------------

def test_the_same_flight_replays_identically():
    """The property the whole architecture rests on: what the student saw
    live and what the debrief reconstructs can never differ."""
    commands, injected = competent_flight()
    a = fly(commands, injected=injected)
    b = fly(commands, injected=injected)
    assert a.state.battery_soc == b.state.battery_soc
    assert a.state.downlinked_mb == b.state.downlinked_mb
    assert [f.outcome for f in a.state.faults] == [f.outcome for f in b.state.faults]


def test_fixed_variants_do_not_shuffle_and_seeded_ones_do():
    fixed = {"injected_faults": ["seu", "beacon_lock"], "shuffle_faults": False}
    shuffled = {"injected_faults": ["seu", "beacon_lock"], "shuffle_faults": True}

    assert ([f.at_t for f in schedule_injected_faults(ORBIT, fixed, seed=1)]
            == [f.at_t for f in schedule_injected_faults(ORBIT, fixed, seed=99)])

    layouts = {tuple(round(f.at_t) for f in schedule_injected_faults(ORBIT, shuffled, seed=s)) for s in range(6)}
    assert len(layouts) > 1


def test_crew_concurrency_puts_faults_on_one_orbit():
    config = {"injected_faults": ["seu", "beacon_lock"], "shuffle_faults": True}
    concurrent = schedule_injected_faults(ORBIT, config, seed=3, concurrent=True)
    orbits = {int(f.at_t // P) for f in concurrent}
    assert len(orbits) == 1


def test_repeated_faults_never_land_at_the_same_instant():
    """Two upsets at once would latch the OBC with no chance to react."""
    for seed in range(8):
        injected = schedule_injected_faults(
            OrbitModel(orbits=4), {"injected_faults": ["seu", "beacon_lock", "seu"], "shuffle_faults": True},
            seed=seed,
        )
        times = [round(f.at_t) for f in injected if f.key == "seu"]
        assert len(set(times)) == len(times)


# --------------------------------------------------------------------------
# Fault accounting
# --------------------------------------------------------------------------

def test_a_fault_that_clears_itself_earns_no_credit():
    """A payload that cooled off because the spacecraft flew into eclipse
    was not an act of operations. Crediting it would reward waiting."""
    result = fly([])
    overtemp = [f for f in result.state.faults if f.key == "payload_overtemp"]
    assert overtemp, "expected the instrument to overheat on an untouched flight"
    assert all(f.outcome == "unresolved" for f in overtemp)
    assert any(f.self_cleared for f in overtemp)


def test_prompt_and_late_responses_are_graded_differently():
    config = {"injected_faults": ["seu"], "shuffle_faults": False}
    injected = schedule_injected_faults(ORBIT, config, seed=0)
    at = injected[0].at_t

    prompt = fly([cmd(at + 60, "RESET_WDT")], injected=injected, config=config)
    late = fly([cmd(at + 1800, "RESET_WDT")], injected=injected, config=config)

    assert next(f for f in prompt.state.faults if f.key == "seu").outcome == "resolved"
    assert next(f for f in late.state.faults if f.key == "seu").outcome == "late"


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------

def test_score_is_objectives_plus_performance_minus_penalties():
    commands, injected = competent_flight()
    result = fly(commands, injected=injected)
    outcome = evaluate(state=result.state, params=PARAMS, config={}, penalties_seen=["needless_reboot"],
                       pass_threshold=65)
    expected = outcome.objectives_score * 0.60 + outcome.performance_score * 0.40 - outcome.penalty_points
    assert outcome.score == pytest.approx(max(0.0, min(100.0, round(expected, 2))), abs=0.02)
    assert outcome.penalty_points == 5.0


def test_objectives_carry_partial_credit():
    """Two of three takes down is genuinely better than none."""
    partial = fly([
        cmd(60, "COLLECT_SAMPLE"), cmd(120, "COLLECT_SAMPLE"),
        cmd(0.425 * P, "DOWNLINK_SCIENCE"), cmd(0.5 * P, "PAYLOAD_OFF"),
    ], until=0.55 * P)
    outcome = evaluate(state=partial.state, params=PARAMS, config={}, penalties_seen=[], pass_threshold=65)
    downlink = next(o for o in outcome.objectives if o.key == "downlink")
    assert 0 < downlink.fraction < 1.0


def test_variant_config_moves_the_targets():
    result = fly([])
    easy = evaluate(state=result.state, params=PARAMS, pass_threshold=50,
                    config={"objectives": {"science_takes": 1, "downlink_mb": 10, "soc_floor": 0.1}},
                    penalties_seen=[])
    hard = evaluate(state=result.state, params=PARAMS, pass_threshold=80,
                    config={"objectives": {"science_takes": 6, "downlink_mb": 200, "soc_floor": 0.6}},
                    penalties_seen=[])
    assert easy.objectives_score > hard.objectives_score


# --------------------------------------------------------------------------
# Telemetry is a view of the state, and it reacts
# --------------------------------------------------------------------------

def test_telemetry_reflects_eclipse():
    """v1's telemetry was a function of elapsed time alone, so a fault had
    no signature and the health light had to name it instead."""
    lit = fly([], until=0.2 * P)
    dark = fly([], until=0.85 * P)
    tm_lit = compute_telemetry(lit.state, PARAMS)
    tm_dark = compute_telemetry(dark.state, PARAMS)

    assert tm_lit["solar_current"] > 0
    assert tm_dark["solar_current"] == 0
    assert tm_dark["panel_temp_c"] < tm_lit["panel_temp_c"]


def test_battery_voltage_tracks_state_of_charge():
    full = fly([cmd(30, "PAYLOAD_OFF")], until=0.3 * P)
    drained = fly([], until=ORBIT.session_seconds)
    assert compute_telemetry(full.state, PARAMS)["battery_voltage"] > \
        compute_telemetry(drained.state, PARAMS)["battery_voltage"]


def test_channel_status_warns_before_it_alarms():
    assert channel_status("battery_soc", 80) == "nominal"
    assert channel_status("battery_soc", 43) == "warn"
    assert channel_status("battery_soc", 30) == "alarm"
    assert channel_status("wheel_rpm", 1000) == "nominal"
    assert channel_status("wheel_rpm", 4200) == "warn"
    assert channel_status("wheel_rpm", 5000) == "alarm"


def test_negative_power_warns_before_it_alarms():
    """Negative power is normal in eclipse — the limit is on how hard you
    are drawing, not on the sign, so the warn band must sit above it."""
    assert channel_status("net_power_w", 2.0) == "nominal"
    assert channel_status("net_power_w", -7.5) == "warn"
    assert channel_status("net_power_w", -9.0) == "alarm"


def test_subsystem_health_reports_condition_not_the_answer():
    result = fly([])
    health = subsystem_health(result.state)
    assert set(health) == {"EPS", "CDHS", "ADCS", "COMMS", "PAYLOAD"}
    assert health["EPS"] == "critical"  # safed
    assert health["ADCS"] in ("warning", "critical")


def test_subsystem_cards_carry_real_readouts():
    """SatKit's five cards had per-subsystem detail; v1 collapsed them into
    one-word lights."""
    result = fly([], until=0.3 * P)
    cards = subsystem_detail(result.state, PARAMS)
    assert [c["subsystem"] for c in cards] == ["EPS", "CDHS", "ADCS", "COMMS", "PAYLOAD"]
    assert all(len(c["rows"]) >= 4 for c in cards)


def test_spacecraft_log_narrates_the_orbit():
    """The alert channel SatKit had as `mission_logs` and v1 dropped."""
    result = fly([])
    messages = " ".join(e["message"] for e in result.state.log)
    assert "AOS" in messages
    assert "eclipse entry" in messages
    assert "sunrise" in messages
    assert any(e["level"] == "ERROR" for e in result.state.log)


# --------------------------------------------------------------------------
# Content: commands, handbook, crew
# --------------------------------------------------------------------------

def test_all_seven_satkit_commands_survive():
    """They were real domain content and there was nothing wrong with them."""
    names = {c.name for c in CATALOG}
    assert {"HELP", "RESET_WDT", "DOWNLOAD_TM", "UPDATE_BEACON",
            "QUEUE_SCIENCE", "COLLECT_SAMPLE", "REBOOT_OBC"} <= names


def test_parse_splits_a_command_from_its_argument():
    assert parse("update_beacon 30s") == ("UPDATE_BEACON", "30s")
    assert parse("  help ") == ("HELP", "")
    assert parse("") == ("", "")


def test_handbook_disclosure_controls_how_much_is_written_down():
    full = handbook(disclosure="full")[0]
    symptoms = handbook(disclosure="symptoms")[0]
    reference = handbook(disclosure="reference")[0]

    assert "action" in full and "if_ignored" in full
    assert "meaning" in symptoms and "action" not in symptoms
    assert "meaning" not in reference
    assert reference["symptom"]  # you always get told what to watch


def test_every_library_fault_can_actually_be_raised():
    """A handbook entry for something the simulator never produces would be
    a lie, and a fault with no entry would be unteachable."""
    from app.services.missions.operate.spacecraft import RESPONSE_WINDOWS
    assert {a.key for a in LIBRARY} == set(RESPONSE_WINDOWS)


def test_every_fault_names_a_command_that_exists():
    names = {c.name for c in CATALOG}
    for spec in LIBRARY:
        assert set(spec.commands) <= names, spec.key


def test_crew_roles_are_derived_from_the_command_catalog():
    for spec in CATALOG:
        if spec.role:
            assert spec.name in ROLE_COMMANDS[spec.role]


def test_an_empty_seat_never_blocks_anyone():
    assert is_command_allowed(command="EPS_RECONFIG", issuer_id="u1", crew={}) is True
    assert is_command_allowed(command="EPS_RECONFIG", issuer_id="u1", crew={"eps": "u2"}) is False
    assert is_command_allowed(command="EPS_RECONFIG", issuer_id="u2", crew={"eps": "u2"}) is True
    assert is_command_allowed(command="HELP", issuer_id="u1", crew={"eps": "u2"}) is True


def test_a_full_replay_is_fast_enough_to_poll():
    """It runs on every 2-second poll, so it has to stay cheap."""
    import time
    commands, injected = competent_flight(OrbitModel(orbits=4))
    start = time.perf_counter()
    for _ in range(5):
        fly(commands, orbit=OrbitModel(orbits=4), injected=injected)
    assert (time.perf_counter() - start) / 5 < 0.15

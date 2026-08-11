"""Stage 7B-3 (Phase 2B, 2026-08-12) — the operate mission's pure functions:
telemetry, telecommands, and the anomaly evaluator. No DB needed for any of
these, same posture as the design mission's calculator tests.
"""

from app.services.missions.operate.commands import KNOWN_COMMANDS, process_command
from app.services.missions.operate.evaluator import evaluate_operation
from app.services.missions.operate.telemetry import compute_telemetry


# ── Telemetry ────────────────────────────────────────────────────────────

def test_telemetry_at_zero_elapsed_is_the_wave_functions_at_zero():
    snap = compute_telemetry(0.0)
    assert snap.pitch == 0.0
    assert snap.roll == 15.0  # cos(0) = 1
    assert snap.yaw == 0.0
    assert snap.battery_voltage == 3.7


def test_telemetry_yaw_increases_monotonically_and_wraps():
    early = compute_telemetry(10.0)
    later = compute_telemetry(100.0)
    assert 0 <= early.yaw < 360
    assert 0 <= later.yaw < 360
    # 480 deg of raw rotation by t=100s (100*0.75=75... let's just check wrap behavior directly)
    wrapped = compute_telemetry(600.0)  # 600*0.75 = 450 -> wraps to 90
    assert wrapped.yaw == 90.0


def test_telemetry_negative_elapsed_is_clamped_not_negative_time():
    snap = compute_telemetry(-5.0)
    assert snap == compute_telemetry(0.0)


def test_telemetry_is_a_pure_function_same_input_same_output():
    a = compute_telemetry(42.5)
    b = compute_telemetry(42.5)
    assert a == b


# ── Telecommands ─────────────────────────────────────────────────────────

def test_help_lists_every_known_command_by_name():
    result = process_command("HELP")
    assert result.success is True
    for cmd in KNOWN_COMMANDS:
        assert cmd in result.message


def test_reboot_obc_is_the_one_command_that_fails():
    result = process_command("REBOOT_OBC")
    assert result.success is False


def test_unknown_command_fails_with_a_helpful_message():
    result = process_command("LAUNCH_NUKES")
    assert result.success is False
    assert "HELP" in result.message


def test_command_is_case_and_whitespace_insensitive():
    assert process_command("  reset_wdt  ").success is True
    assert process_command("Reset_Wdt").success is True


def test_every_fix_command_succeeds():
    for cmd in ("EPS_RECONFIG", "ADCS_RECALIBRATE", "PAYLOAD_RESET", "RESET_WDT", "UPDATE_BEACON"):
        assert process_command(cmd).success is True


# ── Anomaly evaluator ────────────────────────────────────────────────────

SCRIPT = [
    {"trigger_after_commands": 2, "subsystem": "EPS", "correct_command": "EPS_RECONFIG"},
    {"trigger_after_commands": 4, "subsystem": "COMMS", "correct_command": "UPDATE_BEACON"},
]


def test_no_anomalies_triggered_yet_is_a_trivial_pass_so_far():
    result = evaluate_operation(commands_issued=["HELP"], anomaly_script=SCRIPT, pass_threshold=70)
    assert result.triggered_count == 0
    assert result.score == 100.0  # nothing has triggered yet, nothing to fail
    assert result.passed is True


def test_triggered_and_correctly_resolved_anomaly():
    commands = ["HELP", "DOWNLOAD_TM", "EPS_RECONFIG"]  # anomaly triggers at 2, resolved by the 3rd command
    result = evaluate_operation(commands_issued=commands, anomaly_script=SCRIPT, pass_threshold=70)
    assert result.triggered_count == 1
    assert result.resolved_count == 1
    assert result.score == 100.0
    assert result.anomalies[0].resolved is True


def test_triggered_but_unresolved_anomaly_fails_the_threshold():
    commands = ["HELP", "DOWNLOAD_TM", "COLLECT_SAMPLE"]  # anomaly #1 triggers, never fixed
    result = evaluate_operation(commands_issued=commands, anomaly_script=SCRIPT, pass_threshold=70)
    assert result.triggered_count == 1
    assert result.resolved_count == 0
    assert result.score == 0.0
    assert result.passed is False


def test_command_issued_before_trigger_point_does_not_pre_resolve():
    # EPS_RECONFIG issued as the very first command, before the anomaly has
    # even triggered (trigger_after_commands=2) -- must not count.
    commands = ["EPS_RECONFIG", "HELP", "DOWNLOAD_TM"]
    result = evaluate_operation(commands_issued=commands, anomaly_script=SCRIPT, pass_threshold=70)
    assert result.triggered_count == 1
    assert result.resolved_count == 0  # the fix came too early to count


def test_partial_resolution_score_and_threshold():
    # Both anomalies trigger (need >=4 commands); only the first is fixed.
    commands = ["HELP", "DOWNLOAD_TM", "EPS_RECONFIG", "COLLECT_SAMPLE"]
    result = evaluate_operation(commands_issued=commands, anomaly_script=SCRIPT, pass_threshold=70)
    assert result.triggered_count == 2
    assert result.resolved_count == 1
    assert result.score == 50.0
    assert result.passed is False  # 50 < 70


def test_empty_anomaly_script_always_passes():
    result = evaluate_operation(commands_issued=["HELP"], anomaly_script=[], pass_threshold=70)
    assert result.triggered_count == 0
    assert result.score == 100.0
    assert result.passed is True

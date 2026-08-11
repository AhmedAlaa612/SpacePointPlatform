"""Stage 7B-5 — crew role gating, pure function. Roles are optional: an
unfilled role never blocks anyone (MISSIONS_PHASE2B_PLAN.md D6).
"""

from app.services.missions.operate.crew import is_command_allowed


def test_unfilled_role_never_blocks_anyone():
    assert is_command_allowed(command="EPS_RECONFIG", issuer_id="alice", crew={}) is True


def test_filled_role_only_allows_the_assigned_member():
    crew = {"eps": "alice"}
    assert is_command_allowed(command="EPS_RECONFIG", issuer_id="alice", crew=crew) is True
    assert is_command_allowed(command="EPS_RECONFIG", issuer_id="bob", crew=crew) is False


def test_commands_no_role_owns_are_never_gated():
    crew = {"eps": "alice", "commander": "alice", "adcs": "alice", "comms": "alice", "payload": "alice"}
    for cmd in ("HELP", "DOWNLOAD_TM", "QUEUE_SCIENCE", "COLLECT_SAMPLE"):
        assert is_command_allowed(command=cmd, issuer_id="bob", crew=crew) is True


def test_reboot_obc_is_commander_only_once_filled():
    crew = {"commander": "alice"}
    assert is_command_allowed(command="REBOOT_OBC", issuer_id="alice", crew=crew) is True
    assert is_command_allowed(command="REBOOT_OBC", issuer_id="bob", crew=crew) is False


def test_reset_wdt_is_also_the_commanders_seat():
    crew = {"commander": "alice"}
    assert is_command_allowed(command="RESET_WDT", issuer_id="bob", crew=crew) is False


def test_each_role_only_gates_its_own_command():
    crew = {"eps": "alice", "adcs": "bob"}
    assert is_command_allowed(command="EPS_RECONFIG", issuer_id="bob", crew=crew) is False
    assert is_command_allowed(command="ADCS_RECALIBRATE", issuer_id="alice", crew=crew) is False
    assert is_command_allowed(command="ADCS_RECALIBRATE", issuer_id="bob", crew=crew) is True


def test_command_matching_is_case_and_argument_insensitive():
    crew = {"comms": "alice"}
    assert is_command_allowed(command="update_beacon 5m", issuer_id="bob", crew=crew) is False
    assert is_command_allowed(command="UPDATE_BEACON", issuer_id="alice", crew=crew) is True

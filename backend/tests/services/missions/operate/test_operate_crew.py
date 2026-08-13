"""Crew role gating (Stage 7B-5, carried into Operate v2), pure function.
Roles are optional: an unfilled seat never blocks anyone
(MISSIONS_PHASE2B_PLAN.md D6).

**What v2 changed.** In v1 four of the five officers had nothing to own —
only two of the seven commands mapped to a subsystem at all, so a crew was
one person working and four watching. Now every subsystem has live
telemetry, its own failure mode and its own commands, so the ownership map
is much wider: collecting science belongs to the Payload Officer, running
the downlink belongs to Comms. Only the two ground-segment commands (HELP,
STATUS) are ungated, because they read what the station already has and
never touch the vehicle.

The map itself is derived from `commands.CATALOG`, so a command cannot be
added without someone deciding whose job it is.
"""

from app.services.missions.operate.commands import CATALOG
from app.services.missions.operate.crew import ROLE_COMMANDS, is_command_allowed


def test_unfilled_role_never_blocks_anyone():
    assert is_command_allowed(command="EPS_RECONFIG", issuer_id="alice", crew={}) is True


def test_filled_role_only_allows_the_assigned_member():
    crew = {"eps": "alice"}
    assert is_command_allowed(command="EPS_RECONFIG", issuer_id="alice", crew=crew) is True
    assert is_command_allowed(command="EPS_RECONFIG", issuer_id="bob", crew=crew) is False


def test_only_ground_segment_commands_are_ungated():
    crew = {"eps": "alice", "commander": "alice", "adcs": "alice", "comms": "alice", "payload": "alice"}
    for cmd in ("HELP", "STATUS"):
        assert is_command_allowed(command=cmd, issuer_id="bob", crew=crew) is True


def test_every_subsystem_officer_has_real_work():
    """The point of D-f: five seats, five jobs. In v1 three of the five
    owned nothing at all."""
    for role in ("commander", "eps", "adcs", "comms", "payload"):
        assert len(ROLE_COMMANDS[role]) >= 2, role


def test_science_and_downlink_belong_to_their_officers():
    crew = {"payload": "alice", "comms": "bob"}
    assert is_command_allowed(command="COLLECT_SAMPLE", issuer_id="bob", crew=crew) is False
    assert is_command_allowed(command="COLLECT_SAMPLE", issuer_id="alice", crew=crew) is True
    assert is_command_allowed(command="DOWNLINK_SCIENCE", issuer_id="alice", crew=crew) is False
    assert is_command_allowed(command="DOWNLINK_SCIENCE", issuer_id="bob", crew=crew) is True


def test_the_ownership_map_comes_from_the_command_catalog():
    """One list, so a new command can't quietly end up owned by nobody."""
    for spec in CATALOG:
        if spec.role is None:
            assert spec.subsystem == "GROUND", spec.name
        else:
            assert spec.name in ROLE_COMMANDS[spec.role]


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

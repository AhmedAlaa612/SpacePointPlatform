"""The telecommand catalog (Operate v2, Stage 7C-3).

This module is the *vocabulary* — what exists, what it's for, who may send
it, and whether it takes an argument. What each command actually *does* is
physics and lives in `spacecraft.py::apply_command`, because the answer
depends on where the spacecraft is and what state it's in ("downlink"
means something different with no station in view).

All seven of SatKit's original commands survive with their flavour text
intact — that was real domain content and there was nothing wrong with it.
What's new is that they now *do* something: SatKit's terminal and its
subsystem-health model were two disconnected systems, so no command it
accepted ever changed a reading anywhere.

Arguments matter again. SatKit echoed a parameter back into the response
(`UPDATE_BEACON 5m` -> `PERIOD: 5m`); the Stage 7B port matched with
`startswith` and silently dropped it. Here `UPDATE_BEACON` without a
period is a syntax error, because getting the beacon period right is the
whole point of the command.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandSpec:
    name: str
    subsystem: str
    summary: str
    usage: str
    takes_arg: bool = False
    # Which crew role owns it on a team attempt (crew.py). None = anyone.
    role: str | None = None
    # Commands that resolve a fault when used correctly — surfaced in the
    # Ops Handbook so the student can look the response up rather than
    # guess, which is how flight rules actually work.
    resolves: str | None = None


CATALOG: tuple[CommandSpec, ...] = (
    CommandSpec("HELP", "GROUND", "List every telecommand available to you.", "HELP"),
    CommandSpec("STATUS", "GROUND", "One-line summary of vehicle state.", "STATUS"),

    CommandSpec("RESET_WDT", "CDHS", "Reset the watchdog timer and clear a pending upset.",
                "RESET_WDT", role="commander", resolves="seu"),
    CommandSpec("REBOOT_OBC", "CDHS",
                "Cold-reboot the onboard computer. Costs 120s of flight time — correct only "
                "for a latched-up processor.", "REBOOT_OBC", role="commander", resolves="seu"),

    CommandSpec("EPS_LOAD_SHED", "EPS", "Drop payload and transmitter to protect the battery.",
                "EPS_LOAD_SHED", role="eps", resolves="brownout"),
    CommandSpec("EPS_RECONFIG", "EPS", "Reconfigure the power bus and charge controller.",
                "EPS_RECONFIG", role="eps", resolves="brownout"),
    CommandSpec("EXIT_SAFE_MODE", "EPS", "Return to nominal ops. Refused below 50% battery.",
                "EXIT_SAFE_MODE", role="commander", resolves="safe_mode"),

    CommandSpec("PAYLOAD_ON", "PAYLOAD", "Power the instrument up so it can collect.",
                "PAYLOAD_ON", role="payload"),
    CommandSpec("PAYLOAD_STANDBY", "PAYLOAD", "Idle the instrument — low power, and it cools.",
                "PAYLOAD_STANDBY", role="payload", resolves="payload_overtemp"),
    CommandSpec("PAYLOAD_OFF", "PAYLOAD", "Power the instrument down completely.",
                "PAYLOAD_OFF", role="payload", resolves="payload_overtemp"),
    CommandSpec("PAYLOAD_RESET", "PAYLOAD", "Reset the instrument controller.",
                "PAYLOAD_RESET", role="payload", resolves="payload_overtemp"),
    CommandSpec("COLLECT_SAMPLE", "PAYLOAD", "Capture one science take into mass memory.",
                "COLLECT_SAMPLE", role="payload"),
    CommandSpec("QUEUE_SCIENCE", "PAYLOAD", "Alias of COLLECT_SAMPLE, kept from the original flight software.",
                "QUEUE_SCIENCE [tag]", takes_arg=True, role="payload"),

    CommandSpec("ADCS_DESAT", "ADCS",
                "Dump reaction-wheel momentum with the magnetorquers. Perturbs pointing for "
                "180s — don't do it during a pass.", "ADCS_DESAT", role="adcs",
                resolves="wheel_saturation"),
    CommandSpec("ADCS_RECALIBRATE", "ADCS", "Refresh the attitude estimate from the gyros.",
                "ADCS_RECALIBRATE", role="adcs"),

    CommandSpec("UPDATE_BEACON", "COMMS", "Reconfigure the beacon period to re-acquire ground lock.",
                "UPDATE_BEACON <period>", takes_arg=True, role="comms", resolves="beacon_lock"),
    CommandSpec("DOWNLINK_SCIENCE", "COMMS", "Transmitter on — stream mass memory to the ground.",
                "DOWNLINK_SCIENCE", role="comms", resolves="storage_full"),
    CommandSpec("DOWNLINK_STOP", "COMMS", "Transmitter off.", "DOWNLINK_STOP", role="comms"),
    CommandSpec("DOWNLOAD_TM", "COMMS", "Dump housekeeping telemetry during a pass.",
                "DOWNLOAD_TM", role="comms"),
)

BY_NAME: dict[str, CommandSpec] = {c.name: c for c in CATALOG}
KNOWN_COMMANDS = frozenset(BY_NAME)


def parse(raw_command: str) -> tuple[str, str]:
    """`"update_beacon 30s"` -> `("UPDATE_BEACON", "30s")`. Everything after
    the first space is the argument, so a command can take a phrase."""
    clean = (raw_command or "").strip()
    if not clean:
        return "", ""
    head, _, rest = clean.partition(" ")
    return head.upper(), rest.strip()


def help_text() -> str:
    """Grouped by subsystem, because that's how an operator thinks about
    them — and because on a crewed attempt each group is somebody's job."""
    groups: dict[str, list[str]] = {}
    for spec in CATALOG:
        groups.setdefault(spec.subsystem, []).append(spec.usage)
    return " | ".join(f"{sub}: {', '.join(items)}" for sub, items in groups.items())


def command_reference() -> list[dict]:
    """The Ops Handbook's command tab. Available at every difficulty —
    knowing a command exists is not the puzzle; knowing *when* to reach
    for it is."""
    return [
        {
            "name": c.name,
            "subsystem": c.subsystem,
            "summary": c.summary,
            "usage": c.usage,
            "role": c.role,
        }
        for c in CATALOG
    ]

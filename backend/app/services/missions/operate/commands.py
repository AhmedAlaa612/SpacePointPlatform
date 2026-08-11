"""Telecommand vocabulary. The 7 original responses are SatKit's own flavor
text, kept verbatim — that's pure domain content, no bugs to fix. The 3
`*_FIX` commands are new: SatKit's terminal and its subsystem-health model
never actually talked to each other (subsystem status was only ever
toggled manually by an admin, never by anything a student typed), so only
2 of the 5 subsystems (CDHS via `RESET_WDT`, COMMS via `UPDATE_BEACON`)
had a natural command to reuse. EPS/ADCS/PAYLOAD get new commands, in the
same terminal style, because the source has nothing to port for them.

`REBOOT_OBC` keeps its original behavior on purpose: `success=False`, and
it never resolves anything. It's the one command that punishes reaching
for it — a small, deliberate lesson (SatKit's own design, worth keeping)
that not every problem should be solved by rebooting the computer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

KNOWN_COMMANDS = {
    "HELP", "RESET_WDT", "DOWNLOAD_TM", "UPDATE_BEACON", "QUEUE_SCIENCE",
    "COLLECT_SAMPLE", "REBOOT_OBC", "EPS_RECONFIG", "ADCS_RECALIBRATE", "PAYLOAD_RESET",
}

# subsystem a fix command resolves an anomaly on, if it resolves one at all
FIX_COMMAND_SUBSYSTEM: dict[str, str] = {
    "EPS_RECONFIG": "EPS",
    "RESET_WDT": "CDHS",
    "ADCS_RECALIBRATE": "ADCS",
    "UPDATE_BEACON": "COMMS",
    "PAYLOAD_RESET": "PAYLOAD",
}


@dataclass
class CommandResult:
    success: bool
    message: str


def process_command(raw_command: str) -> CommandResult:
    """Server-side only, same posture as every other verifier in this
    codebase — the terminal never grades itself client-side."""
    clean = raw_command.strip()
    base = clean.upper()
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")

    if base == "HELP":
        return CommandResult(True, f"[{ts}] AVAILABLE GROUND TELECOMMANDS: HELP, RESET_WDT, DOWNLOAD_TM, "
                                    f"UPDATE_BEACON, QUEUE_SCIENCE, COLLECT_SAMPLE, REBOOT_OBC, "
                                    f"EPS_RECONFIG, ADCS_RECALIBRATE, PAYLOAD_RESET")
    if base == "RESET_WDT":
        return CommandResult(True, f"[{ts}] OBC: WATCHDOG TIMER RESET SUCCESSFUL // COUNTER REGISTERS CLEAR [0x00]")
    if base == "DOWNLOAD_TM":
        return CommandResult(True, f"[{ts}] TRX: SUB-ORBITAL LINK CONFIRMED. DOWNLOADING TELEMETRY PACKETS 0x001 THROUGH 0x14F...")
    if base.startswith("UPDATE_BEACON"):
        return CommandResult(True, f"[{ts}] TRX: BEACON SCHEDULE RECONFIGURED. DATA STRING: \"SAT-KIT-MVP\"")
    if base.startswith("QUEUE_SCIENCE"):
        return CommandResult(True, f"[{ts}] OBC: AUTONOMOUS FLIGHT TASK ASSIGNED. MISSION TIMELINE LOGGED.")
    if base == "COLLECT_SAMPLE":
        return CommandResult(True, f"[{ts}] PAYLOAD: MAGNETOSPHERE PARTICLE INSTRUMENT ACTIVATED // BUFFER LOADING NOMINAL")
    if base == "REBOOT_OBC":
        return CommandResult(False, f"[{ts}] CRITICAL: ON-BOARD PROCESSING CORE SHUTTING DOWN FOR REBOOT. GROUND TERMINAL LINK SEVERED.")
    if base == "EPS_RECONFIG":
        return CommandResult(True, f"[{ts}] EPS: POWER BUS RECONFIGURED // BATTERY CHARGE CONTROLLER RESTORED TO NOMINAL")
    if base == "ADCS_RECALIBRATE":
        return CommandResult(True, f"[{ts}] ADCS: GYROSCOPE RECALIBRATION COMPLETE // ATTITUDE LOCK REACQUIRED")
    if base == "PAYLOAD_RESET":
        return CommandResult(True, f"[{ts}] PAYLOAD: INSTRUMENT CONTROLLER RESET // SENSOR ARRAY BACK ONLINE")

    return CommandResult(False, f"[{ts}] ERROR: UNRECOGNIZED UPLINK MACRO. TYPE 'HELP' FOR SYSTEM TELECOMMANDS.")

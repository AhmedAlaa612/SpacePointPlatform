"""The command allowlist — ported straight from the legacy app's actual
command set (`LoRa-Dashboard-V3-main/backend/serial_reader.py`), not
reinvented. This is the one piece of "logic" that stays even under time
pressure: it's controlling physical hardware, so an unvalidated command name
reaching the agent is a real-world hazard, not just a data-integrity one.
"""

from __future__ import annotations

ALLOWED_COMMANDS: frozenset[str] = frozenset({
    "PING",           # connectivity check
    "GET_STATUS",     # request a fresh status frame
    "FAKE",           # toggle the rig's own simulated-data mode
    "SPIN_CW",        # motor: spin clockwise
    "SPIN_CCW",       # motor: spin counter-clockwise
    "STOP",           # motor: stop
    "TAKE_PICTURE",   # camera capture
})


def is_allowed(name: str) -> bool:
    return name.strip().upper() in ALLOWED_COMMANDS

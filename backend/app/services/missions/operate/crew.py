"""Crew roles for team `operate` attempts (Phase 2B, Stage 7B-5) — new
domain design, nothing in SatKit to port (its "teams" were just a name on
a mission record, no role concept at all).

Roles are **optional, not mandatory** (MISSIONS_PHASE2B_PLAN.md D6): a
role only restricts a command once someone is actually assigned to it.
An unfilled role means "anyone on the team can act," so a 2-person team
or a solo attempt is never blocked by an empty seat. This is why crew
state lives in `mission_attempts.payload["crew"]` — a plain
`{role: user_id}` map — rather than a schema change that would force
every team attempt to have a full crew.

`commander` covers CDHS (the same "who's in charge of the computer"
pairing SatKit's own `REBOOT_OBC`/`RESET_WDT` flavor text implies) and is
also the only role allowed to issue `REBOOT_OBC` at all on a crewed
attempt — the one deliberately risky command stays gated to whoever's in
charge, once anyone has actually taken that seat.
"""

from __future__ import annotations

ROLES = ("commander", "eps", "adcs", "comms", "payload")

ROLE_LABELS = {
    "commander": "Commander",
    "eps": "Power Engineer",
    "adcs": "Flight Dynamics Officer",
    "comms": "Comms Officer",
    "payload": "Payload/Science Officer",
}

# role -> the commands only that role may issue, once the role is filled
ROLE_COMMANDS: dict[str, set[str]] = {
    "commander": {"RESET_WDT", "REBOOT_OBC"},
    "eps": {"EPS_RECONFIG"},
    "adcs": {"ADCS_RECALIBRATE"},
    "comms": {"UPDATE_BEACON"},
    "payload": {"PAYLOAD_RESET"},
}


def _role_owning(command: str) -> str | None:
    base = command.strip().upper().split(" ")[0]
    for role, commands in ROLE_COMMANDS.items():
        if base in commands:
            return role
    return None


def is_command_allowed(*, command: str, issuer_id: str, crew: dict[str, str]) -> bool:
    """`crew` is `{role: user_id}` for roles that have actually been
    filled — an absent key means that role is open, so anyone may issue
    the commands it owns. Commands no role owns (HELP, DOWNLOAD_TM,
    QUEUE_SCIENCE, COLLECT_SAMPLE, and the three fix commands' role
    itself when unfilled) are never gated.
    """
    role = _role_owning(command)
    if role is None:
        return True
    assigned_to = crew.get(role)
    if assigned_to is None:
        return True  # role open -- anyone may act
    return assigned_to == issuer_id

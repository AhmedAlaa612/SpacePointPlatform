"""Crew roles for team `operate` attempts (Stage 7B-5, carried into v2).

Roles are **optional, not mandatory** (MISSIONS_PHASE2B_PLAN.md D6): a role
only restricts a command once someone is actually sitting in that seat. An
unfilled role means "anyone on the team can act," so a two-person team or a
solo attempt is never blocked by an empty chair. That is why crew state
lives in `mission_attempts.payload["crew"]` as a plain `{role: user_id}`
map rather than a schema change that would force every team attempt to
field a full crew.

**What v2 changes.** The role-to-command mapping is no longer a second
hardcoded dict — it is derived from `commands.CATALOG`, where each command
declares its owning role. One list, so a new command can't be added
without someone deciding whose job it is.

The other change is that the seats now have something to do. In v1 four of
the five officers had no telemetry to watch and no failure mode to own; now
each subsystem has live readouts, its own fault, and its own fix command,
which is what D-f (concurrent anomalies on crewed attempts) is there to
exercise.
"""

from __future__ import annotations

from app.services.missions.operate.commands import CATALOG, parse

ROLES = ("commander", "eps", "adcs", "comms", "payload")

ROLE_LABELS = {
    "commander": "Commander",
    "eps": "Power Engineer",
    "adcs": "Flight Dynamics Officer",
    "comms": "Comms Officer",
    "payload": "Payload/Science Officer",
}

ROLE_SUBSYSTEMS = {
    "commander": "CDHS",
    "eps": "EPS",
    "adcs": "ADCS",
    "comms": "COMMS",
    "payload": "PAYLOAD",
}

# Derived, not duplicated — `commands.CommandSpec.role` is the single place
# a command's ownership is declared.
ROLE_COMMANDS: dict[str, set[str]] = {role: set() for role in ROLES}
for _spec in CATALOG:
    if _spec.role in ROLE_COMMANDS:
        ROLE_COMMANDS[_spec.role].add(_spec.name)


def _role_owning(command: str) -> str | None:
    base, _ = parse(command)
    for role, commands in ROLE_COMMANDS.items():
        if base in commands:
            return role
    return None


def is_command_allowed(*, command: str, issuer_id: str, crew: dict[str, str]) -> bool:
    """`crew` is `{role: user_id}` for seats that have actually been taken —
    an absent key means the seat is open, so anyone may issue the commands
    it owns. Commands no role owns (HELP, STATUS) are never gated.

    Worth being honest about the ceiling here: any member can vacate their
    own seat at any time, so this is a coordination aid rather than an
    enforcement mechanism. For a classroom that is the right trade — the
    goal is to give five people five distinct jobs, not to build an
    authorization system a teenager will treat as a puzzle.
    """
    role = _role_owning(command)
    if role is None:
        return True
    assigned_to = crew.get(role)
    if assigned_to is None:
        return True  # seat open — anyone may act
    return assigned_to == issuer_id


def role_brief() -> list[dict]:
    """What each seat is responsible for — shown on the briefing page and
    in the crew panel, so taking a seat means something before the first
    fault rather than after it."""
    return [
        {
            "role": role,
            "label": ROLE_LABELS[role],
            "subsystem": ROLE_SUBSYSTEMS[role],
            "commands": sorted(ROLE_COMMANDS[role]),
        }
        for role in ROLES
    ]

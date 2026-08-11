"""Student nicknames (Live Games Phase 2C, 8-1 / D1, D2) — the public
identity every leaderboard and live game shows instead of a real name.
Cosmic word + creature word + a 3-digit number (e.g. "NebulaFalcon482"),
matching the shipped design's own examples exactly.

Assigned once, at student-account creation (`assign_nickname`, called from
the two real account-creation call sites: `routers/auth.py`'s self-signup
and `services/lms/ops_integration.py::get_or_create_student_account`).
Idempotent — a second call on an account that already has one is a no-op,
so it's safe to call defensively. The only other mutation path is a
student-initiated reroll (`reroll_nickname`), rate-limited to once every 7
days; there is deliberately no staff-facing edit tool (D2).
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

REROLL_COOLDOWN = timedelta(days=7)
_MAX_GENERATION_ATTEMPTS = 20

# Two independent pools (not one pool repeated) so combinations stay varied
# and never read as "NebulaNebula123" — this is the exact pattern the
# shipped Claude Design mock uses throughout (NebulaFalcon482, QuasarLynx119,
# OrbitRaven730, ...).
COSMIC_WORDS = [
    "Nebula", "Quasar", "Orbit", "Comet", "Solar", "Lunar", "Ion", "Vega",
    "Astro", "Pulsar", "Meteor", "Helios", "Titan", "Drift", "Zenith",
    "Nova", "Cosmo", "Stellar", "Lumen", "Photon", "Gravity", "Eclipse",
    "Aurora", "Corona", "Galactic", "Cryo", "Plasma", "Radiant", "Umbra",
    "Celestial", "Meridian", "Apogee", "Perigee", "Parallax", "Zero-G",
    "Vector", "Warp", "Cislunar", "Interstellar", "Polaris", "Equinox",
    "Solstice", "Magnetar", "Cosmic", "Astral", "Lightyear", "Voyager",
    "Ranger", "Pioneer", "Odyssey",
]

CREATURE_WORDS = [
    "Falcon", "Lynx", "Raven", "Magpie", "Otter", "Halcyon", "Puma",
    "Badger", "Kite", "Sable", "Wren", "Corvid", "Ibis", "Moth", "Heron",
    "Osprey", "Jackal", "Mantis", "Cobra", "Panther", "Coyote",
    "Kestrel", "Weasel", "Marten", "Bison", "Condor", "Gecko", "Hawk",
    "Ferret", "Vulture", "Jaguar", "Lemur", "Mongoose", "Ocelot", "Owl",
    "Peregrine", "Stoat", "Tern", "Viper", "Wolverine", "Bittern",
    "Caracal", "Dingo", "Egret", "Fennec", "Grouse", "Harrier", "Ibex",
    "Jackdaw",
]


def _candidate() -> str:
    number = random.randint(100, 999)
    return f"{random.choice(COSMIC_WORDS)}{random.choice(CREATURE_WORDS)}{number}"


async def _unique_candidate(db: AsyncSession) -> str:
    for _ in range(_MAX_GENERATION_ATTEMPTS):
        candidate = _candidate()
        taken = (await db.execute(select(User.id).where(User.nickname == candidate))).first()
        if taken is None:
            return candidate
    # ~2,500,000 combinations before the number even varies further — this
    # is unreachable in practice, but fail loudly rather than silently
    # assign a colliding nickname if the pools are ever shrunk drastically.
    raise RuntimeError("nicknames: exhausted generation attempts without finding a free combination")


async def assign_nickname(db: AsyncSession, user: User) -> None:
    """Idempotent — does nothing if `user` already has a nickname. Only
    ever called for accounts holding the `student` role."""
    if user.nickname:
        return
    user.nickname = await _unique_candidate(db)
    await db.flush()


async def reroll_nickname(db: AsyncSession, user: User) -> str:
    """Student-initiated only. 429s if the account rerolled within the last
    7 days — `nickname_rerolled_at` is the single source of truth for the
    cooldown, checked here and nowhere else (no separate staff override)."""
    now = datetime.now(timezone.utc)
    if user.nickname_rerolled_at is not None:
        next_allowed = user.nickname_rerolled_at + REROLL_COOLDOWN
        if now < next_allowed:
            raise HTTPException(
                429,
                detail=f"You can change your nickname again on {next_allowed.date().isoformat()}",
            )
    user.nickname = await _unique_candidate(db)
    user.nickname_rerolled_at = now
    await db.flush()
    return user.nickname

"""Design → Operate (Operate v2, Stage 7C-9) — fly the satellite you built.

This is the thing neither legacy repo could ever do, and most of the
argument for having put them on one platform. Madar let a student design a
CubeSat and checked it against six budgets. SatKit let a student watch a
telemetry dashboard for a satellite nobody designed. Separately, both are
exercises. Together, the design mission stops being a spreadsheet:

    A student who cut the power margin thin in design flies a satellite
    that browns out in eclipse, and finds out *why* margins exist in a way
    no budget table can teach.

Mechanically it is small — a mapper from the design attempt's budget rows
onto `SpacecraftParams` — because both halves already existed. The design
mission computes exactly the quantities the simulator needs: total solar
generation, battery capacity, storage, data rate, mass and cost. The only
new idea is pointing one at the other.

**Rules, so this can't quietly change a grade:**

* Only a *passed* design attempt is used. A half-finished design would
  produce a spacecraft that can't fly, and the failure would look like the
  operate mission's fault.
* Parameters are clamped to a survivable envelope. A design with a
  1-watt array is a legitimate design-mission failure but an unplayable
  flight, and the lesson lands better as "this was tight and here is why"
  than as "you lost before you started".
* The mapping is snapshotted into `attempt.payload["spacecraft_source"]`
  at start, so editing the design afterwards never changes a flight that
  has already been graded — the same F2 discipline the design mission
  itself had to learn from Madar.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.missions.mission import Mission, MissionAttempt
from app.services.missions.operate.spacecraft import SpacecraftParams

# The envelope a derived vehicle is clamped into. Wide enough that a good
# design and a mediocre one fly very differently; narrow enough that
# neither is impossible.
BOUNDS = {
    "battery_capacity_wh": (8.0, 60.0),
    "solar_array_w": (3.0, 16.0),
    "payload_active_w": (2.0, 14.0),
    "storage_capacity_mb": (40.0, 512.0),
    "downlink_mbps": (0.25, 8.0),
    "transmitter_w": (3.0, 16.0),
}


def _clamp(key: str, value: float) -> float:
    low, high = BOUNDS[key]
    return max(low, min(high, value))


async def find_passed_design(
    db: AsyncSession, *, user_id: uuid.UUID | None, team_id: uuid.UUID | None,
) -> MissionAttempt | None:
    """The most recent passed `design` attempt belonging to this owner."""
    owner_col = MissionAttempt.user_id if user_id is not None else MissionAttempt.mission_team_id
    owner_val = user_id if user_id is not None else team_id
    if owner_val is None:
        return None

    return await db.scalar(
        select(MissionAttempt)
        .join(Mission, Mission.id == MissionAttempt.mission_id)
        .where(
            Mission.kind == "design",
            owner_col == owner_val,
            MissionAttempt.status == "passed",
        )
        .order_by(MissionAttempt.decided_at.desc())
    )


async def spacecraft_from_design(
    db: AsyncSession, *, design_attempt: MissionAttempt, base: SpacecraftParams,
) -> tuple[SpacecraftParams, dict]:
    """Build a flyable vehicle from a passed design attempt.

    Reads the design mission's own rollup (`design/service.compute_dashboard`)
    rather than a parallel calculation, so the numbers a student saw on
    their design dashboard are literally the numbers they now fly.

    Every lookup is defensive. The design schema will keep evolving, and a
    key that isn't there yet must mean "use the standard part" — never a
    crash halfway through someone's flight.
    """
    from app.models.missions.design import Design, DesignLinkBudgetEntry
    from app.models.missions.mission import MissionVariant
    from app.services.missions.design.service import compute_dashboard, variant_thresholds

    design = await db.scalar(select(Design).where(Design.attempt_id == design_attempt.id))
    if design is None:
        return base, {}

    variant = await db.get(MissionVariant, design_attempt.variant_id)
    config = (variant.config or {}) if variant else {}

    try:
        dash = await compute_dashboard(db, design=design, variant_config=config, attempt=design_attempt)
    except Exception:  # a design we can't roll up is not worth failing a flight over
        return base, {}

    thresholds = variant_thresholds(config)
    link = await db.scalar(select(DesignLinkBudgetEntry).where(DesignLinkBudgetEntry.design_id == design.id))

    changes: dict[str, dict] = {}
    kwargs: dict[str, float] = {}

    def take(param: str, value, label: str, unit: str, note: str = "") -> None:
        try:
            raw = float(value)
        except (TypeError, ValueError):
            return
        if raw <= 0:
            return
        final = _clamp(param, raw)
        kwargs[param] = final
        changes[param] = {
            "label": label, "unit": unit, "note": note,
            "designed": round(raw, 2), "flown": round(final, 2),
            "clamped": abs(final - raw) > 1e-6,
        }

    # Design v2 (7D-9) closes the loop: the design mission now has a real
    # battery (F8/D4), so the one parameter this mapper previously had to
    # skip is finally available. The battery you sized in design is the
    # battery that browns out in eclipse when you fly it.
    take("battery_capacity_wh", design.battery_capacity_wh,
         "Battery capacity", "Wh", "the battery you sized in your design")

    power = dash.get("power")
    if power is not None:
        # The design's generation figure is watts available while the array
        # is illuminated — exactly what the simulator means by solar_array_w.
        take("solar_array_w", getattr(power, "generated_power_mw", 0) / 1000.0,
             "Solar array", "W", "from the solar cells you selected")
        # Everything the student hung on the bus, less the flight-computer
        # baseline the simulator charges separately.
        total_load_w = getattr(power, "total_power_mw", 0) / 1000.0
        take("payload_active_w", total_load_w - base.bus_idle_w,
             "Instrument draw", "W", "your components' total draw, less the bus baseline")

    take("storage_capacity_mb", thresholds.get("max_storage_kb", 0) / 1024.0,
         "Mass memory", "MB", "the storage limit your data budget was checked against")

    if link is not None and getattr(link, "is_saved", False):
        take("downlink_mbps", (getattr(link, "data_rate_kbps", 0) or 0) / 1000.0,
             "Downlink rate", "Mbps", "the data rate from your link budget")

    return SpacecraftParams(**{**base.__dict__, **kwargs}), changes


def source_note(changes: dict) -> list[str]:
    """Lines the console shows, so a student can see which of their own
    design decisions they are now living with.

    Battery capacity joined this list in Design v2 (7D-9), once the design
    mission grew a real energy budget. Before that it was deliberately
    absent — the design had no battery model, and claiming the flown
    capacity came from the student's design would have been a lie about
    where the number came from."""
    notes = []
    for meta in changes.values():
        line = f"{meta['label']}: {meta['designed']} {meta['unit']}"
        if meta.get("note"):
            line += f" — {meta['note']}"
        if meta["clamped"]:
            line += f". Flown at {meta['flown']} {meta['unit']}, clamped to a survivable range."
        notes.append(line)
    return notes

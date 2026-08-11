"""The six design-mission budget calculators — ported from Madar's
`routes/dashboard.py` (MISSIONS_REPORT.md §1.4), as pure functions over
plain dataclasses instead of ORM objects, so a database is never needed to
test the actual engineering math (Madar had zero test coverage; this is
the first).

Every finding from §1.8 that lives in this math is fixed here, not ported
then patched:

- **F3** (dimension-parsing: seed data uses U+00D7, the old parser split on
  ASCII `x`, so every seeded component contributed zero volume) — gone by
  construction. `ComponentInput.length_mm/width_mm/height_mm` are numeric
  fields on the new schema, never a parsed string.
- **F5** (`or`-based fallbacks treat a legitimate 0 as missing, e.g. a
  correctly-entered 0V passive component silently got the library value
  substituted) — every optional numeric here is `is None`-checked, the
  pattern the old mass calculator already used correctly and the others
  didn't.
- **F6** ("has the student touched this?" inferred from
  `updated_at <= created_at`, corrupted by any other writer) — replaced by
  an explicit `is_saved` flag the caller passes in, backed by a real
  recorded fact instead of a timestamp heuristic (`DesignLinkBudgetEntry.
  is_saved`).
- **F8** (per-component energy is computed then thrown away; only
  instantaneous power is checked) — the per-orbit/per-day energy totals
  are now *returned*, not discarded, even though the pass/fail check is
  still instantaneous power vs. solar generation (matching Madar's actual
  documented behavior — a full battery/depth-of-discharge model is P7-8,
  explicitly optional/day-scale scope, not bundled here).

F4 (a student can raise their own mass/volume limit) and F7 (data budget
never checks against link capacity) are fixed one layer up, not here:
F4 by making `max_allowed_mass_kg`/`available_internal_volume_cm3` inputs
the caller derives from a hardcoded CubeSat-size preset table plus the
mission variant's read-only `config`, never a student-editable column;
F7 is P7-8 (optional).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


# CubeSat form-factor presets — hardcoded, never student-editable (F4 fix:
# Madar let a student PUT their own max_allowed_mass_kg/available_volume_cm3
# directly, so a failing design could just raise its own pass threshold).
# A student picks a size; the size determines the limit. There is no path
# that lets a student set the limit itself.
CUBESAT_PRESETS = {
    "1U": {"available_volume_cm3": 1000.0, "max_mass_kg": 1.33},
    "2U": {"available_volume_cm3": 2000.0, "max_mass_kg": 2.66},
    "3U": {"available_volume_cm3": 3000.0, "max_mass_kg": 4.00},
    "6U": {"available_volume_cm3": 6000.0, "max_mass_kg": 8.00},
}


@dataclass
class ModeInput:
    id: str
    duration_min: float


@dataclass
class ComponentInput:
    """The pure-function view of one `DesignComponent` row: its frozen
    snapshot values (never the mutable library row — P7-3) plus which
    modes it's on in, expressed as a set of mode ids (matching
    `DesignComponentModeState`)."""
    subsystem: str
    quantity: int
    on_mode_ids: set[str] = field(default_factory=set)
    mass_per_unit_g: float | None = None
    length_mm: float | None = None
    width_mm: float | None = None
    height_mm: float | None = None
    voltage_v: float | None = None
    current_ma: float | None = None
    cost_per_unit_aed: float | None = None
    data_size_per_measurement_kb: float | None = None
    measurements_per_minute: float | None = None
    storage_mode: str = "Stored"  # Stored|Sent|Both

    def active_minutes(self, modes: list[ModeInput]) -> float:
        return sum(m.duration_min for m in modes if m.id in self.on_mode_ids)


# ── CONOPS ────────────────────────────────────────────────────────────────

@dataclass
class ConopsResult:
    is_valid: bool
    has_data: bool
    total_mode_duration_min: float
    duration_difference_min: float


def calc_conops(*, orbit_duration_min: float, modes: list[ModeInput]) -> ConopsResult:
    total = sum(m.duration_min for m in modes)
    diff = round(total - orbit_duration_min, 4)
    valid = bool(orbit_duration_min) and abs(diff) < 0.001
    return ConopsResult(
        is_valid=valid, has_data=len(modes) > 0,
        total_mode_duration_min=round(total, 4), duration_difference_min=diff,
    )


# ── Data budget ───────────────────────────────────────────────────────────

@dataclass
class DataBudgetResult:
    is_valid: bool
    has_data: bool
    total_per_orbit_kb: float
    total_per_day_kb: float
    total_stored_per_day_kb: float
    total_sent_per_day_kb: float
    storage_remaining_kb: float


def calc_data_budget(
    *, components: list[ComponentInput], modes: list[ModeInput], orbits_per_day: float,
    max_storage_kb: float, required_storage_margin_kb: float,
) -> DataBudgetResult:
    has_data = False
    total_per_orbit = total_per_day = total_stored = total_sent = 0.0
    for c in components:
        if c.data_size_per_measurement_kb is not None or c.measurements_per_minute is not None:
            has_data = True
        sz = c.data_size_per_measurement_kb or 0.0
        mpm = c.measurements_per_minute or 0.0
        dpo = sz * mpm * c.active_minutes(modes)
        dpd = dpo * orbits_per_day
        total_per_orbit += dpo
        total_per_day += dpd
        if c.storage_mode in ("Stored", "Both"):
            total_stored += dpd
        if c.storage_mode in ("Sent", "Both"):
            total_sent += dpd

    remaining = max_storage_kb - total_stored
    capacity_ok = total_stored <= max_storage_kb
    margin_ok = remaining >= required_storage_margin_kb
    return DataBudgetResult(
        is_valid=capacity_ok and margin_ok, has_data=has_data,
        total_per_orbit_kb=round(total_per_orbit, 4), total_per_day_kb=round(total_per_day, 4),
        total_stored_per_day_kb=round(total_stored, 4), total_sent_per_day_kb=round(total_sent, 4),
        storage_remaining_kb=round(remaining, 4),
    )


# ── Power budget ──────────────────────────────────────────────────────────

@dataclass
class PowerBudgetResult:
    is_valid: bool
    has_data: bool
    total_power_mw: float
    total_energy_per_orbit_mwh: float
    total_energy_per_day_mwh: float
    power_margin_mw: float
    required_solar_cells: int
    generated_power_mw: float


def calc_power_budget(
    *, components: list[ComponentInput], modes: list[ModeInput], orbits_per_day: float,
    power_per_solar_cell_w: float, selected_solar_cells: int,
) -> PowerBudgetResult:
    has_data = False
    total_power = total_energy_orbit = 0.0
    for c in components:
        if c.voltage_v is not None or c.current_ma is not None:
            has_data = True
        v = c.voltage_v if c.voltage_v is not None else 0.0
        i = c.current_ma if c.current_ma is not None else 0.0
        p = v * i
        total_power += p
        total_energy_orbit += p * c.active_minutes(modes) / 60

    generated_mw = selected_solar_cells * power_per_solar_cell_w * 1000
    margin = generated_mw - total_power
    required_cells = (
        math.ceil(total_power / 1000 / power_per_solar_cell_w)
        if total_power > 0 and power_per_solar_cell_w > 0 else 0
    )
    return PowerBudgetResult(
        is_valid=total_power > 0 and margin >= 0, has_data=has_data,
        total_power_mw=round(total_power, 3),
        total_energy_per_orbit_mwh=round(total_energy_orbit, 3),
        total_energy_per_day_mwh=round(total_energy_orbit * orbits_per_day, 3),
        power_margin_mw=round(margin, 3), required_solar_cells=required_cells,
        generated_power_mw=round(generated_mw, 3),
    )


# ── Mass budget ───────────────────────────────────────────────────────────

@dataclass
class MassBudgetResult:
    is_valid: bool
    has_data: bool
    total_mass_kg: float
    mass_margin_kg: float
    total_volume_cm3: float
    volume_margin_cm3: float


def calc_mass_budget(
    *, components: list[ComponentInput], max_allowed_mass_kg: float, available_internal_volume_cm3: float,
) -> MassBudgetResult:
    has_data = False
    total_mass_g = total_vol_mm3 = 0.0
    for c in components:
        if c.mass_per_unit_g is not None:
            has_data = True
        mass = c.mass_per_unit_g or 0.0
        lx, wy, hz = c.length_mm or 0.0, c.width_mm or 0.0, c.height_mm or 0.0
        total_mass_g += mass * c.quantity
        total_vol_mm3 += (lx * wy * hz) * c.quantity

    total_mass_kg = total_mass_g / 1000
    total_vol_cm3 = total_vol_mm3 / 1000
    mass_margin = max_allowed_mass_kg - total_mass_kg
    vol_margin = available_internal_volume_cm3 - total_vol_cm3
    return MassBudgetResult(
        is_valid=mass_margin >= 0 and vol_margin >= 0, has_data=has_data,
        total_mass_kg=round(total_mass_kg, 6), mass_margin_kg=round(mass_margin, 6),
        total_volume_cm3=round(total_vol_cm3, 3), volume_margin_cm3=round(vol_margin, 3),
    )


# ── Cost budget ───────────────────────────────────────────────────────────

@dataclass
class CostBudgetResult:
    is_valid: bool
    has_data: bool
    total_cost_aed: float
    cost_margin_aed: float


def calc_cost_budget(*, components: list[ComponentInput], maximum_budget_aed: float) -> CostBudgetResult:
    has_data = False
    total = 0.0
    for c in components:
        if c.cost_per_unit_aed is not None:
            has_data = True
        total += (c.cost_per_unit_aed or 0.0) * c.quantity

    margin = maximum_budget_aed - total
    return CostBudgetResult(
        is_valid=margin >= 0, has_data=has_data,
        total_cost_aed=round(total, 2), cost_margin_aed=round(margin, 2),
    )


# ── Link budget (thin wrapper over rf_calc, F6 fix) ─────────────────────────

@dataclass
class LinkBudgetResult:
    is_valid: bool
    has_data: bool
    margin_db: float
    status: str


def calc_link_budget_status(*, is_saved: bool, link_status: str | None, margin_db: float | None) -> LinkBudgetResult:
    """`is_saved` is a real recorded fact (`DesignLinkBudgetEntry.is_saved`,
    flipped once by the save endpoint) — not Madar's `updated_at <=
    created_at` heuristic (F6), which any other writer or a no-op save
    corrupts."""
    if not is_saved or link_status is None:
        return LinkBudgetResult(is_valid=False, has_data=False, margin_db=0.0, status="No Link Data")
    return LinkBudgetResult(
        is_valid=link_status == "Good Link", has_data=True,
        margin_db=margin_db or 0.0, status=link_status,
    )

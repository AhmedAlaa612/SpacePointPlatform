"""The mission report (Design v2, 7D-3) — the payoff screen.

Madar's dashboard was the point of the whole tool: a Satellite Mission
Report with seven KPIs, a margin table carrying an *interpretation* for
every row, six module cards, ten charts, and templated alerts and
recommendations telling a student what to change. The port rendered a
boolean and seven step badges (`MISSIONS_MADAR_GAP.md` §2.1).

Almost every number was already being computed and returned — the frontend
just never read it. What genuinely did not exist, and is built here, is the
*judgement*: turning `power_margin_mw = -184` into "your array is 184 mW
short of your load; add three cells or drop a component."

Nothing in this module feeds a pass/fail decision. `all_valid` is decided
by the calculators; this only explains the result. That separation is what
lets a mission manager edit the wording on a published mission (D8) without
touching anyone's grade.
"""

from __future__ import annotations

from app.services.missions.design import content

# Below this fraction of the limit a passing budget is called out as tight
# rather than comfortable. A design that only just fits is a design with no
# room for the thing that always goes wrong later.
TIGHT_MARGIN_FRACTION = 0.10


def _status(is_valid: bool, has_data: bool, *, tight: bool = False) -> str:
    if not has_data:
        return "incomplete"
    if not is_valid:
        return "fail"
    return "tight" if tight else "good"


def _fmt(value: float, unit: str) -> str:
    if abs(value) >= 1000:
        return f"{value:,.0f} {unit}"
    if abs(value) >= 10:
        return f"{value:.1f} {unit}"
    return f"{value:.2f} {unit}"


def build_margins(dash: dict, thresholds: dict, limits: dict) -> list[dict]:
    """One row per constrained resource: what you have, what you used, what
    is left, and — the part Madar had and the port dropped — what that
    actually means."""
    data, power, energy = dash["data"], dash["power"], dash["energy"]
    mass, cost, link, downlink = dash["mass"], dash["cost"], dash["link"], dash["downlink"]

    rows: list[dict] = []

    # ── storage ──────────────────────────────────────────────────────────
    cap = thresholds["max_storage_kb"]
    tight = data.has_data and data.is_valid and cap > 0 and data.storage_remaining_kb < cap * TIGHT_MARGIN_FRACTION
    rows.append({
        "key": "storage", "label": "Storage", "value": data.storage_remaining_kb, "unit": "KB",
        "status": _status(data.is_valid, data.has_data, tight=tight),
        "interpretation": (
            "No data budget entered yet." if not data.has_data
            else f"You are storing {_fmt(data.total_stored_per_day_kb, 'KB')}/day against "
                 f"{_fmt(cap, 'KB')} of memory — over capacity." if not data.is_valid
            else f"Only {_fmt(data.storage_remaining_kb, 'KB')} spare. Any new instrument will overflow it."
            if tight
            else f"{_fmt(data.storage_remaining_kb, 'KB')} spare after storing "
                 f"{_fmt(data.total_stored_per_day_kb, 'KB')}/day."
        ),
    })

    # ── instantaneous power ──────────────────────────────────────────────
    gen = power.generated_power_mw
    tight = power.has_data and power.is_valid and gen > 0 and power.power_margin_mw < gen * TIGHT_MARGIN_FRACTION
    rows.append({
        "key": "power", "label": "Power (peak)", "value": power.power_margin_mw, "unit": "mW",
        "status": _status(power.is_valid, power.has_data, tight=tight),
        "interpretation": (
            "No power budget entered yet." if not power.has_data
            else f"Your array makes {_fmt(gen, 'mW')} but the load peaks at "
                 f"{_fmt(power.total_power_mw, 'mW')} — {_fmt(abs(power.power_margin_mw), 'mW')} short. "
                 f"You need about {power.required_solar_cells} cells." if not power.is_valid
            else f"Only {_fmt(power.power_margin_mw, 'mW')} of headroom at peak load."
            if tight
            else f"{_fmt(power.power_margin_mw, 'mW')} of headroom at peak load."
        ),
    })

    # ── energy over an orbit ─────────────────────────────────────────────
    rows.append({
        "key": "energy", "label": "Energy per orbit", "value": energy.energy_margin_mwh, "unit": "mWh",
        "status": _status(energy.energy_balance_ok, energy.has_data),
        "interpretation": (
            "Size a battery to complete this check." if not energy.has_data
            else f"You consume {_fmt(energy.consumed_per_orbit_mwh, 'mWh')} per orbit but only generate "
                 f"{_fmt(energy.generated_per_orbit_mwh, 'mWh')} in {energy.sunlit_minutes:.0f} minutes of "
                 f"sunlight. The battery loses {_fmt(abs(energy.energy_margin_mwh), 'mWh')} every lap."
            if not energy.energy_balance_ok
            else f"Generation covers consumption with {_fmt(energy.energy_margin_mwh, 'mWh')} to spare each orbit."
        ),
    })

    # ── depth of discharge ───────────────────────────────────────────────
    dod_limit = energy.max_depth_of_discharge_pct
    rows.append({
        "key": "depth_of_discharge", "label": "Battery depth of discharge", "value": energy.depth_of_discharge_pct,
        "unit": "%",
        "status": _status(energy.depth_of_discharge_ok, energy.has_data,
                          tight=energy.depth_of_discharge_ok and energy.depth_of_discharge_pct > dod_limit * 0.85),
        "interpretation": (
            "Size a battery to complete this check." if not energy.has_data
            else f"Eclipse takes {energy.depth_of_discharge_pct:.0f}% out of the battery — over the "
                 f"{dod_limit:.0f}% limit. Sixteen times a day for years, that wears the cells out."
            if not energy.depth_of_discharge_ok
            else f"Eclipse takes {energy.depth_of_discharge_pct:.0f}% out of a {dod_limit:.0f}% allowance."
        ),
    })

    # ── link margin ──────────────────────────────────────────────────────
    rows.append({
        "key": "link", "label": "Link margin", "value": link.margin_db, "unit": "dB",
        "status": _status(link.is_valid, link.has_data),
        "interpretation": (
            "No link budget saved yet." if not link.has_data
            else f"Link status is '{link.status}' at {link.margin_db:.1f} dB. Raise transmit power, "
                 f"antenna gain, or lower the data rate." if not link.is_valid
            else f"{link.margin_db:.1f} dB of margin — the link closes."
        ),
    })

    # ── downlink capacity (F7) ───────────────────────────────────────────
    rows.append({
        "key": "downlink", "label": "Downlink per orbit", "value": downlink.downlink_margin_kb, "unit": "KB",
        "status": _status(downlink.is_valid, downlink.has_data),
        "interpretation": (
            "Save a link budget to check this." if not downlink.has_data
            else "Nothing is marked to send. A spacecraft that stores science forever and never "
                 "downlinks it has no mission — set at least one component's data to Sent or Both."
            if downlink.data_to_downlink_per_orbit_kb <= 0
            else f"You want to send {_fmt(downlink.data_to_downlink_per_orbit_kb, 'KB')} per orbit but the "
                 f"{downlink.contact_minutes:.0f}-minute pass only carries "
                 f"{_fmt(downlink.downlink_capacity_per_orbit_kb, 'KB')} — that is "
                 f"{downlink.utilisation_pct:.0f}% of capacity." if not downlink.is_valid
            else f"Using {downlink.utilisation_pct:.0f}% of the contact window."
        ),
    })

    # ── mass and volume ──────────────────────────────────────────────────
    max_mass = limits["max_mass_kg"]
    tight = mass.has_data and mass.is_valid and mass.mass_margin_kg < max_mass * TIGHT_MARGIN_FRACTION
    rows.append({
        "key": "mass", "label": "Mass", "value": mass.mass_margin_kg, "unit": "kg",
        "status": _status(mass.is_valid, mass.has_data, tight=tight),
        "interpretation": (
            "No mass budget entered yet." if not mass.has_data
            else f"{mass.total_mass_kg:.3f} kg against a {max_mass:.2f} kg limit." if not mass.is_valid
            else f"{mass.mass_margin_kg:.3f} kg spare — tight." if tight
            else f"{mass.mass_margin_kg:.3f} kg spare of {max_mass:.2f} kg."
        ),
    })
    rows.append({
        "key": "volume", "label": "Volume", "value": mass.volume_margin_cm3, "unit": "cm³",
        "status": _status(mass.volume_margin_cm3 >= 0, mass.has_data),
        "interpretation": (
            "No dimensions entered yet." if not mass.has_data
            else f"Components total {mass.total_volume_cm3:,.0f} cm³ against "
                 f"{limits['available_volume_cm3']:,.0f} cm³ inside the CubeSat."
            if mass.volume_margin_cm3 < 0
            else f"{mass.volume_margin_cm3:,.0f} cm³ spare — before harness and brackets, which "
                 f"typically take another 20–30%."
        ),
    })

    # ── cost ─────────────────────────────────────────────────────────────
    budget = thresholds["maximum_budget_aed"]
    tight = cost.has_data and cost.is_valid and cost.cost_margin_aed < budget * TIGHT_MARGIN_FRACTION
    rows.append({
        "key": "cost", "label": "Cost", "value": cost.cost_margin_aed, "unit": "AED",
        "status": _status(cost.is_valid, cost.has_data, tight=tight),
        "interpretation": (
            "No cost budget entered yet." if not cost.has_data
            else f"{cost.total_cost_aed:,.0f} AED against a {budget:,.0f} AED budget." if not cost.is_valid
            else f"{cost.cost_margin_aed:,.0f} AED left — not much room to fix anything later." if tight
            else f"{cost.cost_margin_aed:,.0f} AED of {budget:,.0f} AED left."
        ),
    })

    return rows


def build_kpis(dash: dict, component_count: int, mode_count: int) -> dict:
    return {
        "total_components": component_count,
        "total_modes": mode_count,
        "total_data_per_day_kb": dash["data"].total_per_day_kb,
        "total_power_mw": dash["power"].total_power_mw,
        "energy_per_orbit_mwh": dash["energy"].consumed_per_orbit_mwh,
        "total_mass_kg": dash["mass"].total_mass_kg,
        "total_cost_aed": dash["cost"].total_cost_aed,
        "link_margin_db": dash["link"].margin_db,
    }


_MODULE_TABS = {
    "conops": "conops", "data_budget": "data", "power_budget": "power", "energy_budget": "energy",
    "link_budget": "link", "downlink": "dashboard", "mass_budget": "mass", "cost_budget": "cost",
    "components": "components",
}


def build_module_cards(dash: dict, thresholds: dict, component_count: int) -> list[dict]:
    """One card per step: status, two numbers that matter, and where to go
    to fix it. `downlink` deliberately points at the dashboard rather than a
    tab, because it is a constraint across three steps and the alert says
    which one to change."""
    d = dash
    spec = [
        ("components", "Components", "Selected", str(component_count), "", ""),
        ("conops", "CONOPS", "Mode total", f"{d['conops'].total_mode_duration_min:.0f} min",
         "Difference", f"{d['conops'].duration_difference_min:+.1f} min"),
        ("data_budget", "Data budget", "Per day", _fmt(d["data"].total_per_day_kb, "KB"),
         "Stored", _fmt(d["data"].total_stored_per_day_kb, "KB")),
        ("power_budget", "Power budget", "Peak load", _fmt(d["power"].total_power_mw, "mW"),
         "Generated", _fmt(d["power"].generated_power_mw, "mW")),
        ("energy_budget", "Energy & battery", "Margin/orbit", _fmt(d["energy"].energy_margin_mwh, "mWh"),
         "Depth of discharge", f"{d['energy'].depth_of_discharge_pct:.0f}%"),
        ("link_budget", "Link budget", "Margin", f"{d['link'].margin_db:.1f} dB", "Status", d["link"].status),
        ("downlink", "Downlink check", "Needed", _fmt(d["downlink"].data_to_downlink_per_orbit_kb, "KB"),
         "Capacity", _fmt(d["downlink"].downlink_capacity_per_orbit_kb, "KB")),
        ("mass_budget", "Mass & volume", "Mass", f"{d['mass'].total_mass_kg:.3f} kg",
         "Volume", f"{d['mass'].total_volume_cm3:,.0f} cm³"),
        ("cost_budget", "Cost budget", "Total", f"{d['cost'].total_cost_aed:,.0f} AED",
         "Budget", f"{thresholds['maximum_budget_aed']:,.0f} AED"),
    ]
    cards = []
    for key, title, k1, v1, k2, v2 in spec:
        step = dash["steps"].get(key, {"has_data": False, "is_valid": False})
        cards.append({
            "key": key, "title": title,
            "status": _status(step["is_valid"], step["has_data"]),
            "kpi1_label": k1, "kpi1_value": v1, "kpi2_label": k2, "kpi2_value": v2,
            "tab": _MODULE_TABS.get(key, "dashboard"),
        })
    return cards


def build_charts(components: list, modes: list) -> dict:
    """Three charts, not Madar's ten (D5). Power, mass and cost by
    subsystem are the three that actually drive a redesign decision."""
    def by_subsystem(value_of) -> list[dict]:
        totals: dict[str, float] = {}
        for c in components:
            totals[c.subsystem] = totals.get(c.subsystem, 0.0) + value_of(c)
        return [{"subsystem": k, "value": round(v, 3)} for k, v in sorted(totals.items()) if v > 0]

    return {
        "power_by_subsystem": by_subsystem(
            lambda c: ((c.voltage_v or 0.0) * (c.current_ma or 0.0)) * c.quantity),
        "mass_by_subsystem": by_subsystem(
            lambda c: (c.mass_per_unit_g or 0.0) * c.quantity),
        "cost_by_subsystem": by_subsystem(
            lambda c: (c.cost_per_unit_aed or 0.0) * c.quantity),
        "mode_distribution": [
            {"mode_name": m.mode_name, "duration_min": m.duration_min} for m in modes
        ],
    }


def build_advice(dash: dict, margins: list[dict]) -> tuple[list[dict], list[dict]]:
    """Alerts say what is wrong; recommendations say what to do about it.

    This is where the mission teaches on failure rather than just reporting
    it, and it is the half of Madar's dashboard that was pure content — the
    numbers were always there, the judgement was not. Recommendations are
    drawn from `content.MISTAKES` wherever a known pattern matches, so the
    advice a student gets here is the same advice the handbook gives.
    """
    alerts: list[dict] = []
    recs: list[dict] = []
    failing = {m["key"] for m in margins if m["status"] == "fail"}
    tight = {m["key"] for m in margins if m["status"] == "tight"}

    for row in margins:
        if row["status"] == "fail":
            alerts.append({"severity": "error", "step": row["key"], "message": row["interpretation"]})
        elif row["status"] == "tight":
            alerts.append({"severity": "warning", "step": row["key"], "message": row["interpretation"]})

    conops = dash["conops"]
    if conops.has_data and not conops.is_valid:
        alerts.insert(0, {
            "severity": "error", "step": "conops",
            "message": f"Your mode durations total {conops.total_mode_duration_min:.0f} minutes, "
                       f"{abs(conops.duration_difference_min):.0f} minutes "
                       f"{'over' if conops.duration_difference_min > 0 else 'under'} one orbit. Every "
                       f"budget downstream reads these durations.",
        })

    # Known-mistake matching: a mistake fires when any of its steps failed.
    step_of_margin = {
        "storage": "data_budget", "power": "power_budget", "energy": "energy_budget",
        "depth_of_discharge": "energy_budget", "link": "link_budget", "downlink": "downlink",
        "mass": "mass_budget", "volume": "mass_budget", "cost": "cost_budget",
    }
    failing_steps = {step_of_margin.get(k, k) for k in failing}
    if conops.has_data and not conops.is_valid:
        failing_steps.add("conops")

    for mistake in content.MISTAKES:
        if failing_steps & set(mistake["steps"]):
            recs.append({
                "key": mistake["key"], "title": mistake["title"],
                "message": mistake["fix"], "why": mistake["meaning"],
            })

    if not alerts:
        if dash["all_valid"]:
            alerts.append({
                "severity": "success", "step": None,
                "message": "Every budget closes. This design would survive a preliminary design review.",
            })
        else:
            alerts.append({
                "severity": "info", "step": None,
                "message": "No budget has failed — some steps just aren't finished yet.",
            })
    if tight and not failing:
        recs.append({
            "key": "tight_margins", "title": "Your margins are thin",
            "message": "Everything closes, but with very little to spare. Real projects lose margin as "
                       "they mature — the part you actually get is heavier than the datasheet, the "
                       "harness is longer than planned. Buy some headroom back now.",
            "why": "A design that only just fits at this stage rarely still fits at the end.",
        })

    return alerts, recs


def overall_status(dash: dict, margins: list[dict]) -> dict:
    errors = sum(1 for m in margins if m["status"] == "fail")
    warnings = sum(1 for m in margins if m["status"] == "tight")
    incomplete = sum(1 for m in margins if m["status"] == "incomplete")

    if dash["all_valid"] and warnings == 0:
        label = "Ready"
    elif dash["all_valid"]:
        label = "Ready — margins tight"
    elif errors:
        label = "Invalid design"
    else:
        label = "Incomplete"

    return {
        "label": label, "all_valid": dash["all_valid"],
        "errors": errors, "warnings": warnings, "incomplete": incomplete,
    }

"""The design mission's teaching content (Design v2, 7D-2/7D-4/7D-5).

Everything a student reads lives here as authored data, for the same reason
`operate/anomalies.py` does: writing a new lesson should be one record, not
an edit to three files that must agree. The briefing renders `BUDGETS` and
`STEP_ORDER`, the Design Handbook renders all of it, the dashboard's
recommendations render `MISTAKES`, and the link budget renders
`ASSUMPTIONS`.

**Why this file exists at all.** The ported page had zero words of
explanatory copy in 596 lines. Madar had a data-types guide, live formulas
on the link page, interpretation strings on every margin, and templated
advice on every failure — none of which came across
(`MISSIONS_MADAR_GAP.md` §2.3). A student was filling in nine tabs of
numbers with nothing telling them what a budget *is*.

Editing this is a content change, never a grading change: nothing here
feeds a pass/fail check. That is what makes it safe for a mission manager
to edit on a published mission under D8, where thresholds stay frozen.
"""

from __future__ import annotations

# ── What a budget is, and why there are seven ────────────────────────────

WHAT_IS_A_BUDGET = (
    "A budget in systems engineering is not money — it is any finite resource you have to "
    "share out across a spacecraft. Mass, power, data, cost, radio link margin. You have a "
    "fixed amount, every component takes a share, and the design only works if the shares add "
    "up to less than what you have.\n\n"
    "That is the whole job. Almost every real spacecraft decision is a trade between budgets: "
    "a bigger battery fixes your power problem and breaks your mass budget; a faster radio "
    "fixes your downlink and costs you power. Budgets are how engineers find out which "
    "trade they are actually making."
)

STEP_ORDER = [
    {
        "key": "setup", "label": "Mission setup",
        "detail": "Name the mission, pick an orbit and a CubeSat size. The size sets your mass and "
                  "volume limits — it is the first real constraint you choose.",
        "depends_on": [],
    },
    {
        "key": "components", "label": "Components",
        "detail": "Choose what goes on the spacecraft. Every later budget is computed from these "
                  "parts, so this is the decision everything else inherits.",
        "depends_on": ["setup"],
    },
    {
        "key": "conops", "label": "CONOPS",
        "detail": "Split one orbit into modes — sun pointing, nadir pointing, ground station, "
                  "eclipse — and tick which components are on in each. This is the step "
                  "everything else reads: active time per component comes from here, and four "
                  "separate budgets consume it.",
        "depends_on": ["components"],
    },
    {
        "key": "data_budget", "label": "Data budget",
        "detail": "How much data you generate per orbit and per day, and whether it fits in "
                  "storage. Uses active time from CONOPS.",
        "depends_on": ["conops"],
    },
    {
        "key": "power_budget", "label": "Power budget",
        "detail": "Instantaneous load against what the solar array can produce, and how many "
                  "cells that needs.",
        "depends_on": ["conops"],
    },
    {
        "key": "energy_budget", "label": "Energy & battery",
        "detail": "Power over a whole orbit, not just at one instant: does generation in sunlight "
                  "cover consumption, and does the battery survive eclipse?",
        "depends_on": ["power_budget", "conops"],
    },
    {
        "key": "link_budget", "label": "Link budget",
        "detail": "Whether the radio signal is strong enough to close the link to the ground "
                  "station at all.",
        "depends_on": ["components"],
    },
    {
        "key": "downlink", "label": "Downlink check",
        "detail": "Whether you can actually get your data down in the minutes you are over the "
                  "station. Needs the data budget, the link budget and CONOPS together — which "
                  "is why it has no tab of its own.",
        "depends_on": ["data_budget", "link_budget", "conops"],
    },
    {
        "key": "mass_budget", "label": "Mass & volume",
        "detail": "Does it weigh less than the launch limit, and does it physically fit inside "
                  "the CubeSat you chose?",
        "depends_on": ["components"],
    },
    {
        "key": "cost_budget", "label": "Cost budget",
        "detail": "Can you afford it?",
        "depends_on": ["components"],
    },
]


# ── Per-budget handbook entries ──────────────────────────────────────────

BUDGETS = [
    {
        "key": "conops",
        "title": "CONOPS — the concept of operations",
        "checks": "That your mode durations add up to exactly one orbit.",
        "means": "A spacecraft does different things at different points in its orbit: charging "
                 "with panels to the Sun, pointing an instrument at Earth, talking to a ground "
                 "station, or riding out eclipse on battery. The matrix records which components "
                 "are powered in each mode, and from that one table comes each component’s active time — how "
                 "many minutes per orbit each component actually runs.",
        "fails_when": "Your mode durations do not sum to the orbit period. An orbit is a fixed "
                      "length of time; every minute of it has to be spent doing something.",
        "fix": "Adjust the mode durations until they total your orbit duration.",
        "formula": "active_time(component) = Σ duration(mode) for every mode the component is on in",
        "why_it_matters": "Four separate budgets read this table. Getting it wrong quietly moves "
                          "every number downstream, which is why it comes before them.",
    },
    {
        "key": "data_budget",
        "title": "Data budget — how much you generate",
        "checks": "That the data you keep on board fits in memory, with the margin your mission requires.",
        "means": "Each instrument produces a measurement of some size, some number of times per "
                 "minute, for however long it is switched on. Multiply those out across an orbit "
                 "and a day and you get your data volume. Some of it you keep on board; some you "
                 "send to the ground.",
        "fails_when": "Stored data exceeds mass memory, or leaves less than the required margin.",
        "fix": "Lower the measurement rate, reduce the data size per measurement, mark more data "
               "as Sent rather than Stored, or reduce the component's active time in CONOPS.",
        "formula": "data_per_orbit = size_per_measurement × measurements_per_minute × active_minutes",
        "why_it_matters": "Storage is the cheap half of the problem. Getting the data down to the ground is "
                          "the hard half — see the downlink check.",
    },
    {
        "key": "power_budget",
        "title": "Power budget — the instantaneous load",
        "checks": "That the solar array can supply the total load at any one moment.",
        "means": "Every component draws voltage × current while it is on. Add them up and you get "
                 "the peak the power system has to be able to supply.",
        "fails_when": "Total load exceeds what your selected solar cells generate.",
        "fix": "Add solar cells, or remove/replace high-power components, or turn things off in "
               "more modes so fewer things are on at once.",
        "formula": "power (mW) = voltage (V) × current (mA);  generated = cells × watts_per_cell × 1000",
        "why_it_matters": "This check alone is not enough — it says nothing about eclipse, or "
                          "about whether you can keep it up for a whole orbit. That is the "
                          "energy budget.",
    },
    {
        "key": "energy_budget",
        "title": "Energy & battery — power over a whole orbit",
        "checks": "Two things: that energy generated over one orbit covers energy consumed, and "
                  "that the battery does not discharge too deeply through eclipse.",
        "means": "The array only produces while the spacecraft is in sunlight, and roughly a "
                 "third of a low Earth orbit is spent in Earth's shadow. Your CONOPS already "
                 "says how long that is — it is whatever you allocated to the eclipse mode. "
                 "Everything running during eclipse comes out of the battery.",
        "fails_when": "Energy in over a lap is less than energy out (the battery trends down every "
                      "orbit until the spacecraft dies), or eclipse discharge exceeds the depth-"
                      "of-discharge limit.",
        "fix": "Turn non-essential components off in the eclipse mode, add solar cells, or size a "
               "larger battery. Turning things off in eclipse usually fixes both checks at once.",
        "formula": "generated = solar_power × sunlit_minutes / 60\n"
                   "consumed  = Σ (power × active_minutes) / 60\n"
                   "depth_of_discharge = eclipse_draw / battery_capacity",
        "why_it_matters": "Depth of discharge is a lifetime limit, not a survival one. A "
                          "lithium cell taken to 60% every orbit — sixteen times a day, for "
                          "years — wears out long before the mission is over. This is what "
                          "actually kills satellites.",
    },
    {
        "key": "link_budget",
        "title": "Link budget — can the radio close the link?",
        "checks": "That the received signal is strong enough above the noise for the data rate "
                  "and quality you asked for.",
        "means": "Radio power spreads out over distance and arrives at the ground much weaker "
                 "than it left. The link budget adds up everything that helps (transmit power, "
                 "antenna gain) and everything that hurts (path loss, noise), and reports "
                 "whatever margin is left.",
        "fails_when": "Margin falls below your mission's threshold.",
        "fix": "Increase transmit power, use a higher-gain antenna, or reduce the data rate — "
               "a slower link needs less signal, which is the trade most students miss.",
        "formula": "FSPL = 20·log₁₀(d) + 20·log₁₀(f) − 147.55\n"
                   "EIRP = transmit_power + antenna_gain\n"
                   "noise = 10·log₁₀(k · T · bandwidth) + 30\n"
                   "margin = (EIRP − FSPL − noise) − required_signal_quality",
        "why_it_matters": "A closed link tells you a signal arrives. It does not tell you the "
                          "data fits in the time you have — that is the downlink check.",
    },
    {
        "key": "downlink",
        "title": "Downlink check — can you get it down in time?",
        "checks": "That the data you marked to send each orbit fits in the ground station "
                  "contact window, at your link's data rate, with headroom.",
        "means": "This is the one constraint that spans three steps. Your data budget says how "
                 "much you want to send. Your link budget says how fast the radio is. Your "
                 "CONOPS says how many minutes per orbit the ground station is actually in "
                 "view. All three have to agree.",
        "fails_when": "Demand per orbit exceeds what the contact window can carry.",
        "fix": "Any of three places — collect less (data budget), transmit faster (link budget), "
               "or spend longer over the station (CONOPS). Each is a real engineering trade "
               "with its own cost.",
        "formula": "capacity_per_orbit (KB) = data_rate (kbps) × contact_minutes × 60 / 8\n"
                   "demand_per_orbit  (KB) = data_sent_per_day / orbits_per_day",
        "why_it_matters": "You can generate all the science you like — you still have to get it "
                          "down in the eight minutes you are over the ground station. This is "
                          "the single most important idea in the whole mission.",
    },
    {
        "key": "mass_budget",
        "title": "Mass & volume — does it fly, and does it fit?",
        "checks": "Total mass against the launch limit for your CubeSat size, and total component "
                  "volume against the space inside it.",
        "means": "A CubeSat is sold by the 'U' — a 10 cm cube. Each size carries a mass limit "
                 "the launch provider enforces and an internal volume you physically cannot "
                 "exceed.",
        "fails_when": "You are over on either. Volume is the one people forget.",
        "fix": "Lighter or smaller parts, fewer of them, or step up a CubeSat size — which "
               "raises both limits but also the cost.",
        "formula": "mass = Σ (mass_per_unit × quantity);  volume = Σ (L × W × H × quantity)",
        "why_it_matters": "Volume here is a simple sum of bounding boxes with no packing factor, "
                          "so it is optimistic. Real integration engineers assume you lose "
                          "20–30% to harness, brackets and clearance.",
    },
    {
        "key": "cost_budget",
        "title": "Cost budget — can you afford it?",
        "checks": "Total component cost against the mission's budget.",
        "means": "Every part has a price. The sum has to fit.",
        "fails_when": "You are over budget.",
        "fix": "Cheaper alternatives, or fewer units.",
        "formula": "cost = Σ (cost_per_unit × quantity)",
        "why_it_matters": "Cost is the budget that decides which of the other trades you are "
                          "actually allowed to make.",
    },
]


# ── The eight data types (lifted from Madar, which got this right) ───────

DATA_TYPES = [
    {"name": "Telemetry", "detail": "Real-time health and status data from subsystems — temperatures, currents, voltages."},
    {"name": "Image", "detail": "Visual data captured by cameras or sensors, e.g. Earth observation."},
    {"name": "Science Data", "detail": "Raw measurements from mission-specific sensors or instruments."},
    {"name": "Video", "detail": "High-bandwidth visual streams. The most expensive thing you can choose to downlink."},
    {"name": "Housekeeping", "detail": "Background data tracking the satellite's long-term health and history."},
    {"name": "GPS/Nav", "detail": "Position, velocity and time synchronisation from global navigation systems."},
    {"name": "Telemetry and Commands", "detail": "Bidirectional signals for the CDHS to report status and receive directives."},
    {"name": "TT&C", "detail": "Telemetry, Tracking and Command — the critical link carrying health, ranging and uplink commands."},
]


# ── Common mistakes: the design analog of the anomaly library ────────────

MISTAKES = [
    {
        "key": "array_sized_for_peak",
        "title": "Sizing the array for peak load",
        "symptom": "Power budget passes, energy budget fails with a negative margin.",
        "meaning": "Peak load happens for a few minutes an orbit — usually while transmitting. "
                   "Sizing the array to cover the peak instant is expensive and still doesn't "
                   "guarantee the orbit balances, because the array stops entirely in eclipse.",
        "fix": "Size for orbit-average consumption and let the battery cover the peaks. Then check "
               "the battery can actually cover them.",
        "steps": ["power_budget", "energy_budget"],
    },
    {
        "key": "everything_on_always",
        "title": "Every component on in every mode",
        "symptom": "Active time equals the full orbit for everything; power and data both come out "
                   "very high; eclipse discharge is enormous.",
        "meaning": "That is not a concept of operations, it is a parts list. The entire point of "
                   "the CONOPS matrix is that things turn off — a camera does not run in eclipse, "
                   "a transmitter does not run outside a ground station pass.",
        "fix": "Go back to CONOPS and untick anything that has no reason to be on in that mode. "
               "It usually fixes the power, energy and data budgets at once.",
        "steps": ["conops"],
    },
    {
        "key": "blank_dimensions",
        "title": "Volume passes because dimensions are blank",
        "symptom": "Volume margin looks huge and comfortable.",
        "meaning": "A component with no length, width or height contributes zero volume. It isn't "
                   "fitting — it just isn't being counted.",
        "fix": "Fill in the dimensions on the mass budget, or check the library entry has them.",
        "steps": ["mass_budget"],
    },
    {
        "key": "data_never_downlinked",
        "title": "Generating data you can never send",
        "symptom": "Data budget passes, link budget passes, downlink check fails at several hundred "
                   "percent utilisation.",
        "meaning": "Storage and downlink are different problems. A UHF radio at 9,600 bps moves "
                   "about 0.5 MB in an eight-minute pass. If you are generating tens of megabytes "
                   "a day, it will never come down.",
        "fix": "Collect less, move to a faster band, or lengthen the ground station window — and "
               "understand what each of those costs.",
        "steps": ["data_budget", "link_budget", "downlink"],
    },
    {
        "key": "battery_too_small",
        "title": "A battery that can't survive the night",
        "symptom": "Energy balance is positive but depth of discharge is over the limit.",
        "meaning": "Over a full orbit you generate enough — but the eclipse pass takes too much "
                   "out of the battery in one go. Charging back up afterwards doesn't undo the "
                   "wear of a deep discharge.",
        "fix": "A bigger battery, or a smaller eclipse load. Turning the payload off in eclipse is "
               "almost always the cheaper answer.",
        "steps": ["energy_budget"],
    },
    {
        "key": "data_rate_too_high",
        "title": "Asking for a data rate the link can't support",
        "symptom": "Link margin goes negative as soon as you raise the data rate.",
        "meaning": "A faster link needs more signal to stay above the noise. Doubling the data rate "
                   "costs you about 3 dB of margin — the same as halving your transmit power.",
        "fix": "Reduce the data rate, or buy the margin back with antenna gain or transmit power.",
        "steps": ["link_budget"],
    },
    {
        "key": "conops_doesnt_add_up",
        "title": "Mode durations that don't total the orbit",
        "symptom": "CONOPS shows a duration difference, and every downstream budget looks slightly wrong.",
        "meaning": "An orbit is a fixed length of time. If your modes sum to more or less than it, "
                   "the active times feeding four other budgets are wrong too.",
        "fix": "Make the mode durations total your orbit period exactly.",
        "steps": ["conops"],
    },
]


# ── F9: what this model simplifies, stated rather than hidden ────────────

ASSUMPTIONS = [
    "The link budget is a teaching model. It accounts for transmit power, satellite antenna gain, "
    "free-space path loss and thermal noise — and omits ground-station antenna gain, system G/T, "
    "pointing and polarisation losses, and atmospheric absorption. A real link budget has twenty "
    "more lines.",
    "System noise temperature is fixed at 290 K, and noise bandwidth is approximated by the data "
    "rate. Both are reasonable first-order choices and neither is exact.",
    "Distance to the ground station is a fixed assumed range, not a real slant range that changes "
    "through a pass. A real link is weakest at the horizon and strongest overhead.",
    "Volume is a sum of component bounding boxes with no packing factor. Real integration loses "
    "20–30% to harness, brackets and clearance, so a design that just fits here does not fit in "
    "reality.",
    "The energy budget uses your eclipse mode duration as the shadow fraction. A real eclipse "
    "fraction varies through the year with the orbit's beta angle.",
    "Battery modelling is capacity and depth of discharge only — no temperature effects, no charge "
    "efficiency curve, no ageing.",
    "Costs are indicative component prices converted at a fixed rate. They exclude launch, "
    "integration, testing, licensing and ground segment, which on a real CubeSat usually cost more "
    "than the parts.",
]


def handbook(*, disclosure: str = "full") -> dict:
    """The Design Handbook, disclosure-scaled the same way the operate
    mission's Ops Handbook is (D-d there, reused here):

    * `full`      — everything, including the fix.  (Cadet)
    * `symptoms`  — what it checks and what it means; you work out the fix.  (Engineer)
    * `reference` — formulas and limits only. You are the systems engineer.  (Flight Director)
    """
    def budget(entry: dict) -> dict:
        out = {"key": entry["key"], "title": entry["title"], "checks": entry["checks"],
               "formula": entry["formula"]}
        if disclosure in ("full", "symptoms"):
            out["means"] = entry["means"]
            out["fails_when"] = entry["fails_when"]
            out["why_it_matters"] = entry["why_it_matters"]
        if disclosure == "full":
            out["fix"] = entry["fix"]
        return out

    def mistake(entry: dict) -> dict:
        out = {"key": entry["key"], "title": entry["title"], "symptom": entry["symptom"],
               "steps": entry["steps"]}
        if disclosure in ("full", "symptoms"):
            out["meaning"] = entry["meaning"]
        if disclosure == "full":
            out["fix"] = entry["fix"]
        return out

    return {
        "disclosure": disclosure,
        "what_is_a_budget": WHAT_IS_A_BUDGET,
        "step_order": STEP_ORDER,
        "budgets": [budget(b) for b in BUDGETS],
        "data_types": DATA_TYPES,
        "mistakes": [mistake(m) for m in MISTAKES],
        "assumptions": ASSUMPTIONS,
    }


def briefing(variant, *, mission_title: str, mission_summary: str | None) -> dict:
    """Everything a student should read before they start designing
    (7D-4). Available before an attempt row exists, so opening it never
    burns a retry — the same split the operate mission's pre-flight
    briefing uses, and for the same reason.

    The variant's thresholds are shown rather than hidden. A student should
    know what they are being held to before they start, not discover it on
    the report screen.
    """
    from app.services.missions.design.calculators import CUBESAT_PRESETS
    from app.services.missions.design.service import variant_thresholds

    config = variant.config or {}
    t = variant_thresholds(config)

    return {
        "mission_title": mission_title,
        "mission_summary": mission_summary,
        "variant_id": str(variant.id),
        "variant_label": variant.label,
        "points": variant.points,
        "what_is_a_budget": WHAT_IS_A_BUDGET,
        "step_order": STEP_ORDER,
        "limits": [
            {"key": "storage", "label": "Mass memory",
             "value": f"{t['max_storage_kb'] / 1024:,.0f} MB",
             "detail": f"with at least {t['required_storage_margin_kb'] / 1024:,.0f} MB left spare"},
            {"key": "cost", "label": "Budget", "value": f"{t['maximum_budget_aed']:,.0f} AED",
             "detail": "for every component on the spacecraft"},
            {"key": "link", "label": "Link margin",
             "value": f"{t['good_link_margin_threshold_db']:.0f} dB",
             "detail": f"at an assumed range of {t['assumed_distance_km']:,.0f} km"},
            {"key": "battery", "label": "Depth of discharge",
             "value": f"{t['max_depth_of_discharge_pct']:.0f}%",
             "detail": "the most the battery may be drained each eclipse"},
            {"key": "downlink", "label": "Downlink headroom",
             "value": f"{t['required_downlink_margin_fraction'] * 100:.0f}%",
             "detail": "of the contact window must stay free"},
        ],
        "cubesat_sizes": [
            {"size": k, "max_mass_kg": v["max_mass_kg"], "available_volume_cm3": v["available_volume_cm3"]}
            for k, v in CUBESAT_PRESETS.items()
        ],
        "budgets": [
            {"key": b["key"], "title": b["title"], "checks": b["checks"],
             "why_it_matters": b["why_it_matters"]}
            for b in BUDGETS
        ],
        "assumptions": ASSUMPTIONS,
    }


# ── Authored overrides (D8) ─────────────────────────────────────────────

# Only these may be overridden from `missions.content`. An allowlist rather
# than a free-form merge, so a bad edit can garble the wording but never
# invent a step, drop a fault from the library, or change a formula the
# calculators actually use.
OVERRIDABLE_BUDGET_FIELDS = {"title", "checks", "means", "fails_when", "fix", "why_it_matters"}
OVERRIDABLE_MISTAKE_FIELDS = {"title", "symptom", "meaning", "fix"}


def apply_overrides(payload: dict, overrides: dict | None) -> dict:
    """Merge a mission's authored content over the defaults.

    Absent keys fall through, so a mission with `content = {}` behaves
    exactly as it did before this existed.
    """
    if not overrides:
        return payload
    out = dict(payload)

    if isinstance(overrides.get("what_is_a_budget"), str) and overrides["what_is_a_budget"].strip():
        out["what_is_a_budget"] = overrides["what_is_a_budget"]

    if isinstance(overrides.get("assumptions"), list) and overrides["assumptions"]:
        out["assumptions"] = [str(a) for a in overrides["assumptions"]]

    budget_over = overrides.get("budgets") or {}
    if isinstance(budget_over, dict) and out.get("budgets"):
        out["budgets"] = [
            {**b, **{k: v for k, v in (budget_over.get(b["key"]) or {}).items()
                     if k in OVERRIDABLE_BUDGET_FIELDS and isinstance(v, str) and v.strip()}}
            for b in out["budgets"]
        ]

    mistake_over = overrides.get("mistakes") or {}
    if isinstance(mistake_over, dict) and out.get("mistakes"):
        out["mistakes"] = [
            {**m, **{k: v for k, v in (mistake_over.get(m["key"]) or {}).items()
                     if k in OVERRIDABLE_MISTAKE_FIELDS and isinstance(v, str) and v.strip()}}
            for m in out["mistakes"]
        ]

    return out


def editable_content(overrides: dict | None) -> dict:
    """What the authoring UI shows: the current text for every overridable
    field, with a flag for whether it is the default or has been edited."""
    over = overrides or {}
    return {
        "what_is_a_budget": {
            "value": over.get("what_is_a_budget") or WHAT_IS_A_BUDGET,
            "overridden": bool(over.get("what_is_a_budget")),
            "default": WHAT_IS_A_BUDGET,
        },
        "budgets": [
            {
                "key": b["key"],
                "fields": {
                    f: {
                        "value": (over.get("budgets", {}).get(b["key"], {}) or {}).get(f) or b.get(f, ""),
                        "overridden": bool((over.get("budgets", {}).get(b["key"], {}) or {}).get(f)),
                        "default": b.get(f, ""),
                    }
                    for f in sorted(OVERRIDABLE_BUDGET_FIELDS) if b.get(f) is not None
                },
            }
            for b in BUDGETS
        ],
        "mistakes": [
            {
                "key": m["key"],
                "fields": {
                    f: {
                        "value": (over.get("mistakes", {}).get(m["key"], {}) or {}).get(f) or m.get(f, ""),
                        "overridden": bool((over.get("mistakes", {}).get(m["key"], {}) or {}).get(f)),
                        "default": m.get(f, ""),
                    }
                    for f in sorted(OVERRIDABLE_MISTAKE_FIELDS) if m.get(f) is not None
                },
            }
            for m in MISTAKES
        ],
        "assumptions": {
            "value": over.get("assumptions") or ASSUMPTIONS,
            "overridden": bool(over.get("assumptions")),
            "default": ASSUMPTIONS,
        },
    }

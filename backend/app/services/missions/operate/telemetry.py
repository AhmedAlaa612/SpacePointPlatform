"""Telemetry (Operate v2, Stage 7C-1/7C-5) — a *view* of the spacecraft
state, never a second source of truth.

This file used to be the simulation: v1 computed every channel from
`elapsed_seconds` with sine waves ported from SatKit, which meant the
readouts were decorative. Nothing read them — not the anomalies, not the
score, not the pass/fail threshold — so a student could ignore the whole
dashboard and lose nothing. Worse, the mission's own description promised
"the only warning is what the telemetry tells you," which simply wasn't
true: when EPS went critical, the battery voltage kept its untouched wave.

Now every channel is derived from `SpacecraftState`, so a fault has a
*signature*. That is the difference between diagnosing a problem and
reading a label off a status light.

Each channel carries its nominal range, and the console colours the
readout against it. Those same ranges are the flight rules the briefing
teaches, so what the student is told and what the console shows can't
drift apart — they're one table.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.services.missions.operate.orbit import signal_strength_dbm
from app.services.missions.operate.spacecraft import (
    MODE_SAFE,
    PAYLOAD_OFF,
    PAYLOAD_ON,
    POINTING_LIMIT_DEG,
    SpacecraftParams,
    SpacecraftState,
)


@dataclass(frozen=True)
class Channel:
    """One readout. `low`/`high` are the flight-rule limits; either may be
    None for a channel that's only bounded on one side."""

    key: str
    label: str
    unit: str
    subsystem: str
    low: float | None = None
    high: float | None = None
    precision: int = 2


CHANNELS: tuple[Channel, ...] = (
    Channel("battery_soc", "Battery charge", "%", "EPS", low=40.0, high=None, precision=1),
    Channel("battery_voltage", "Bus voltage", "V", "EPS", low=3.5, high=4.2),
    Channel("battery_current", "Battery current", "A", "EPS", precision=3),
    Channel("solar_current", "Array current", "A", "EPS", precision=3),
    # Negative power is *normal* in eclipse — that's what a battery is for.
    # The limit is on how hard you're drawing, not on the sign.
    Channel("net_power_w", "Power balance", "W", "EPS", low=-8.0, precision=2),

    Channel("obc_uptime_s", "OBC uptime", "s", "CDHS", precision=0),
    Channel("storage_used_mb", "Mass memory", "MB", "CDHS", precision=1),
    Channel("system_temp_c", "Avionics temp", "C", "CDHS", low=-10.0, high=50.0, precision=1),

    Channel("wheel_rpm", "Reaction wheel", "RPM", "ADCS", high=4500.0, precision=0),
    Channel("attitude_error_deg", "Pointing error", "deg", "ADCS", high=POINTING_LIMIT_DEG, precision=2),
    Channel("pitch", "Pitch", "deg", "ADCS", precision=1),
    Channel("roll", "Roll", "deg", "ADCS", precision=1),
    Channel("yaw", "Yaw", "deg", "ADCS", precision=1),

    Channel("signal_strength", "Signal strength", "dBm", "COMMS", precision=1),
    Channel("packets_received", "Packets received", "", "COMMS", precision=0),
    Channel("downlinked_mb", "Downlinked", "MB", "COMMS", precision=1),

    Channel("payload_temp_c", "Instrument temp", "C", "PAYLOAD", high=55.0, precision=1),
    Channel("panel_temp_c", "Panel temp", "C", "PAYLOAD", low=-30.0, high=60.0, precision=1),
)

CHANNELS_BY_KEY = {c.key: c for c in CHANNELS}


def compute_telemetry(state: SpacecraftState, params: SpacecraftParams) -> dict:
    """Every channel the console shows, as a flat dict.

    Attitude angles keep SatKit's original wave shapes — a nadir-pointing
    spacecraft really does oscillate gently about its reference, and there
    was nothing wrong with that part of the source. What's new is that the
    *amplitude* grows with `attitude_error_deg`, so a saturating wheel is
    visible as the spacecraft starting to wander before it fully loses
    control. That's the signature the ADCS lesson depends on.
    """
    phase = state.phase
    t = state.t

    # Bus voltage sags under load and with depth of discharge, which is
    # what a real battery does and why voltage is the channel operators
    # actually watch.
    v_nominal = 3.6 + 0.6 * state.battery_soc
    sag = 0.02 * max(0.0, state.load_w - state.generation_w)
    battery_voltage = max(3.0, v_nominal - sag)

    battery_current = round((state.load_w - state.generation_w) / max(1.0, battery_voltage), 3)
    solar_current = round(state.generation_w / max(1.0, battery_voltage), 3)

    wobble = 1.0 + state.attitude_error_deg
    return {
        # attitude
        "pitch": round(math.sin(t * 0.0011) * wobble, 2),
        "roll": round(math.cos(t * 0.0009) * wobble * 0.6, 2),
        "yaw": round((t * 0.0628) % 360.0, 2),
        "attitude_error_deg": round(state.attitude_error_deg, 2),
        "wheel_rpm": round(state.wheel_rpm, 0),
        "imu_x": round(0.02 + math.sin(t * 0.003) * 0.05, 4),
        "imu_y": round(-0.01 + math.cos(t * 0.002) * 0.04, 4),
        "imu_z": round(0.98 + math.sin(t * 0.001) * 0.02, 4),

        # power
        "battery_soc": round(state.battery_soc * 100.0, 1),
        "battery_voltage": round(battery_voltage, 3),
        "battery_current": battery_current,
        "solar_current": solar_current,
        "net_power_w": round(state.net_power_w, 2),
        "generation_w": round(state.generation_w, 2),
        "load_w": round(state.load_w, 2),

        # thermal
        "panel_temp_c": round(state.panel_temp_c, 1),
        "payload_temp_c": round(state.payload_temp_c, 1),
        "system_temp_c": round(state.system_temp_c, 1),

        # comms
        "signal_strength": signal_strength_dbm(phase) if phase else -120.0,
        "packets_received": state.packets_received,
        "downlinked_mb": round(state.downlinked_mb, 1),
        "link_ok": state.link_ok,
        "transmitter_on": state.transmitter_on,
        "beacon_locked": state.beacon_locked,

        # data
        "storage_used_mb": round(state.storage_used_mb, 1),
        "storage_capacity_mb": round(params.storage_capacity_mb, 1),
        "science_takes": state.science_takes,

        # CDHS
        "obc_uptime_s": round(state.obc_uptime_s, 0),
        "obc_wedged": state.obc_wedged,

        # modes
        "mode": state.mode,
        "payload_state": state.payload_state,
    }


def channel_status(key: str, value: float) -> str:
    """`nominal` · `warn` · `alarm`, against the flight rules. This is what
    turns a wall of numbers into something a student can scan — and it uses
    exactly the limits the briefing taught them.

    The warn band is the last 10% of the approach to a limit, measured from
    whichever side the limit is on. That matters for channels whose limit
    is negative (power balance): warning has to fire *before* the alarm,
    not past it.
    """
    channel = CHANNELS_BY_KEY.get(key)
    if channel is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return "nominal"

    if channel.high is not None:
        if value >= channel.high:
            return "alarm"
        if value >= channel.high - 0.1 * abs(channel.high):
            return "warn"
    if channel.low is not None:
        if value <= channel.low:
            return "alarm"
        if value <= channel.low + 0.1 * abs(channel.low):
            return "warn"
    return "nominal"


def subsystem_health(state: SpacecraftState) -> dict[str, str]:
    """One word per subsystem for the health strip.

    Unlike v1's lights — which reported anomaly state and therefore told
    the student the answer — these report *condition*, derived from the
    physics. A red EPS light means the power is genuinely bad right now;
    it doesn't name a command.
    """
    health: dict[str, str] = {}

    if state.mode == MODE_SAFE:
        health["EPS"] = "critical"
    elif state.battery_soc < 0.40 or state.net_power_w < -4.0:
        health["EPS"] = "warning"
    else:
        health["EPS"] = "nominal"

    if state.obc_wedged:
        health["CDHS"] = "critical"
    elif state.seu_pending or state.obc_busy_until_t > state.t:
        health["CDHS"] = "warning"
    elif state.storage_fraction >= 0.80:
        health["CDHS"] = "warning"
    else:
        health["CDHS"] = "nominal"

    if state.attitude_error_deg >= POINTING_LIMIT_DEG * 2:
        health["ADCS"] = "critical"
    elif state.attitude_error_deg >= POINTING_LIMIT_DEG or state.wheel_rpm >= 4500:
        health["ADCS"] = "warning"
    else:
        health["ADCS"] = "nominal"

    if not state.beacon_locked:
        health["COMMS"] = "critical"
    elif state.phase is not None and state.phase.in_pass and not state.link_ok:
        health["COMMS"] = "warning"
    else:
        health["COMMS"] = "nominal"

    if state.payload_temp_c >= 55.0:
        health["PAYLOAD"] = "critical"
    elif state.payload_temp_c >= 50.0:
        health["PAYLOAD"] = "warning"
    elif state.payload_state == PAYLOAD_OFF:
        health["PAYLOAD"] = "off"
    else:
        health["PAYLOAD"] = "nominal"

    return health


def subsystem_detail(state: SpacecraftState, params: SpacecraftParams) -> list[dict]:
    """The five subsystem cards — the real readouts SatKit had and the v1
    port collapsed into one-word lights. Each row carries its own status so
    the failing number is the one that turns red, not the whole card."""
    tm = compute_telemetry(state, params)
    health = subsystem_health(state)
    phase = state.phase

    def row(key: str, value, text: str | None = None) -> dict:
        channel = CHANNELS_BY_KEY.get(key)
        return {
            "key": key,
            "label": channel.label if channel else key,
            "value": text if text is not None else value,
            "unit": channel.unit if channel else "",
            "status": channel_status(key, value) if text is None else "nominal",
        }

    return [
        {
            "subsystem": "EPS", "title": "EPS — Electrical Power", "status": health["EPS"],
            "rows": [
                row("battery_soc", tm["battery_soc"]),
                row("battery_voltage", tm["battery_voltage"]),
                row("net_power_w", tm["net_power_w"]),
                row("solar_current", tm["solar_current"]),
                {"key": "mode", "label": "Mode", "value": state.mode, "unit": "",
                 "status": "alarm" if state.mode == MODE_SAFE else "nominal"},
            ],
        },
        {
            "subsystem": "CDHS", "title": "CDHS — Command & Data Handling", "status": health["CDHS"],
            "rows": [
                row("obc_uptime_s", tm["obc_uptime_s"]),
                row("storage_used_mb", tm["storage_used_mb"],
                    text=f"{state.storage_used_mb:.0f} / {params.storage_capacity_mb:.0f} MB"),
                row("system_temp_c", tm["system_temp_c"]),
                {"key": "obc_state", "label": "Processor", "value":
                    "LATCHED UP" if state.obc_wedged else ("UPSET PENDING" if state.seu_pending else "Healthy"),
                 "unit": "", "status": "alarm" if (state.obc_wedged or state.seu_pending) else "nominal"},
            ],
        },
        {
            "subsystem": "ADCS", "title": "ADCS — Attitude Control", "status": health["ADCS"],
            "rows": [
                row("wheel_rpm", tm["wheel_rpm"]),
                row("attitude_error_deg", tm["attitude_error_deg"]),
                {"key": "pointing", "label": "Pointing mode", "value":
                    "Sun-safe" if state.mode == MODE_SAFE else
                    ("Momentum dump" if state.desat_until_t > state.t else "Nadir lock"),
                 "unit": "", "status": "nominal"},
                row("pitch", tm["pitch"]),
            ],
        },
        {
            "subsystem": "COMMS", "title": "COMMS — Communications", "status": health["COMMS"],
            "rows": [
                row("signal_strength", tm["signal_strength"]),
                row("packets_received", tm["packets_received"]),
                row("downlinked_mb", tm["downlinked_mb"]),
                {"key": "link", "label": "Link", "value":
                    ("Downlinking" if (state.transmitter_on and state.link_ok) else
                     "Locked, idle" if (phase and phase.in_pass and state.beacon_locked) else
                     "No beacon lock" if not state.beacon_locked else "No station in view"),
                 "unit": "", "status": "alarm" if not state.beacon_locked else "nominal"},
            ],
        },
        {
            "subsystem": "PAYLOAD", "title": "PAYLOAD — Science Instrument", "status": health["PAYLOAD"],
            "rows": [
                {"key": "payload_state", "label": "Instrument", "value": state.payload_state, "unit": "",
                 "status": "nominal" if state.payload_state == PAYLOAD_ON else "warn"},
                row("payload_temp_c", tm["payload_temp_c"]),
                row("panel_temp_c", tm["panel_temp_c"]),
                {"key": "takes", "label": "Science takes", "value": state.science_takes, "unit": "",
                 "status": "nominal"},
            ],
        },
    ]


def flight_rules() -> list[dict]:
    """The nominal-range table the briefing shows and the console colours
    against — one source, so a student is never graded against a limit they
    weren't told about."""
    return [
        {
            "channel": c.key, "label": c.label, "unit": c.unit, "subsystem": c.subsystem,
            "low": c.low, "high": c.high,
        }
        for c in CHANNELS
        if c.low is not None or c.high is not None
    ]

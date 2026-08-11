"""Live telemetry — the same wave shapes as SatKit's
`simulation.py::generate_space_environment`, but as a pure function of
elapsed time instead of a global `while True: sleep(2)` loop mutating one
shared object.

That rewrite isn't cosmetic — it fixes two real bugs in the source rather
than porting them: every user watched the *same* simulated satellite
(one shared `TelemetryState` object for the whole server), and a stray
`hardware-upload` call could set `is_active = False` and kill it
permanently with no way back. Computing telemetry fresh from
`elapsed_seconds` per attempt means two students never see each other's
satellite, and there's no shared mutable state to kill in the first
place.

SatKit ticked every 2 seconds, advancing an internal `time_ticker` by
0.05 each tick — `t = elapsed_seconds * 0.025` reproduces that exact
rate as a pure function. `yaw` was a running increment (not a wave) in
the original — `elapsed_seconds * 0.75` reproduces the same 1.5-per-tick
rotation. `solar_current` is new: SatKit's dict declared the field but
its tick loop never actually set it (a third dead field, on top of the
already-known camelCase/snake_case split) — a flat 0 forever would look
broken on a live gauge, so a simple correlated wave is authored here
instead of ported.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class TelemetrySnapshot:
    pitch: float
    roll: float
    yaw: float
    battery_voltage: float
    battery_current: float
    battery_percentage: int
    panel_temp: float
    system_temp: float
    solar_current: float
    imu_x: float
    imu_y: float
    imu_z: float
    reaction_wheel_speed: float
    signal_strength: float
    humidity: float
    light: float


def compute_telemetry(elapsed_seconds: float) -> TelemetrySnapshot:
    t = max(0.0, elapsed_seconds) * 0.025
    yaw = (max(0.0, elapsed_seconds) * 0.75) % 360.0

    return TelemetrySnapshot(
        pitch=round(math.sin(t) * 25.0, 3),
        roll=round(math.cos(t) * 15.0, 3),
        yaw=round(yaw, 3),
        battery_voltage=round(3.7 + (math.sin(t * 2) * 0.25), 3),
        battery_current=round(0.25 + max(0.0, math.cos(t) * 0.35), 3),
        battery_percentage=int(88.0 + (math.sin(t * 0.2) * 11.0)),
        panel_temp=round(25.0 + (math.sin(t) * 10.0), 2),
        system_temp=round(32.4 + (math.sin(t * 0.5) * 2.0), 2),
        solar_current=round(max(0.0, math.sin(t) * 0.5), 3),
        imu_x=round(0.02 + (math.sin(t * 3) * 0.05), 4),
        imu_y=round(-0.01 + (math.cos(t * 2) * 0.04), 4),
        imu_z=round(0.98 + (math.sin(t) * 0.02), 4),
        reaction_wheel_speed=round(1200.0 + (math.sin(t) * 150.0), 2),
        signal_strength=round(-68.0 + (math.sin(t * 0.5) * 7.0), 2),
        humidity=round(42.0 + (math.cos(t * 0.8) * 3.5), 2),
        light=round(max(5.0, 500.0 + (math.sin(t * 0.4) * 450.0)), 2),
    )

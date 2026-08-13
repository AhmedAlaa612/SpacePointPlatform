"""The orbit clock (Operate v2, Stage 7C-1) — where the mission's sense of
time comes from.

Everything the student sees is anchored here. In v1 telemetry was a
function of wall-clock elapsed seconds and nothing else, so the live
readouts were decorative: no anomaly, no score and no threshold ever read
them. Now a session is `orbits` laps of a real orbital period, and the
spacecraft's position in that lap decides whether the solar array is
generating, whether the ground station is in view, and whether the
satellite is flying through the radiation belt that causes upsets. Power,
comms and fault behaviour all fall out of this one function.

This is deliberately the same architectural move that makes the design
mission good — Madar's CONOPS active-time matrix is one shared truth
feeding six derived budgets (MISSIONS_REPORT.md §1.4). Here one orbit
timeline feeds telemetry, anomalies, objectives and the debrief.

Fidelity is teaching-grade and the assumptions are stated on screen
(MISSIONS_OPERATE_V2_PLAN.md D-c) rather than hidden, which is the
discipline that report asked for on Madar's link budget:

  * circular orbit, no drag decay, no J2 precession within a session
  * a fixed eclipse fraction rather than a real beta-angle model
  * one ground station, with pass windows at a fixed point in each lap
    instead of a propagated ground track
  * elevation modelled as a half-sine across the pass, which is close
    enough for a link that rises, peaks and sets

Period and velocity, though, are computed from real orbital mechanics
rather than hardcoded — SatKit displayed a literal "7.6 km/s" next to a
literal "97.5 deg", and both turn out to be right for this altitude,
which is a decent sign the intern knew the domain even where the code
didn't.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

MU_EARTH_KM3_S2 = 398_600.4418
R_EARTH_KM = 6_371.0

# Link floor with no station in view. Real receivers report their noise
# floor here rather than nothing at all, and a student watching the number
# climb out of the floor is watching the pass begin.
NO_PASS_SIGNAL_DBM = -120.0
PEAK_PASS_SIGNAL_DBM = -68.0


@dataclass(frozen=True)
class OrbitModel:
    """The flight plan. Fractions are of one orbital period, so a window
    stays put relative to the lap no matter what altitude is chosen."""

    altitude_km: float = 550.0
    orbits: int = 3
    # Fraction of each lap spent in Earth's shadow. ~0.35 is typical for a
    # sun-synchronous orbit that isn't dawn-dusk; a dawn-dusk SSO would be
    # near zero and would remove the power lesson entirely.
    eclipse_fraction: float = 0.35
    # Ground-station pass: ~8 minutes of a ~95-minute lap.
    pass_start_fraction: float = 0.42
    pass_duration_fraction: float = 0.084
    # South Atlantic Anomaly crossing — elevated radiation, where single
    # event upsets actually happen.
    saa_start_fraction: float = 0.20
    saa_duration_fraction: float = 0.063
    # Sim seconds per real second. A ~95 min lap at 18x is ~5.3 real
    # minutes, so a 3-orbit session runs about 16 minutes — the right
    # length for a class, and short enough that a retry is cheap.
    time_compression: float = 18.0
    ground_station: str = "Dubai GS"

    @property
    def semi_major_axis_km(self) -> float:
        return R_EARTH_KM + self.altitude_km

    @property
    def period_seconds(self) -> float:
        a = self.semi_major_axis_km
        return 2.0 * math.pi * math.sqrt((a**3) / MU_EARTH_KM3_S2)

    @property
    def velocity_km_s(self) -> float:
        return math.sqrt(MU_EARTH_KM3_S2 / self.semi_major_axis_km)

    @property
    def inclination_deg(self) -> float:
        """Sun-synchronous inclination for this altitude. The SSO condition
        makes nodal precession match Earth's mean motion about the Sun; the
        closed form needs J2, and this is the standard result for low
        Earth orbit — ~97.6 deg at 550 km, rising slowly with altitude."""
        a = self.semi_major_axis_km
        j2 = 1.08263e-3
        # cos(i) = -(2/3) * (a/R)^(7/2) * (n_sun / (J2 * n)) ... collapsed
        # to the standard numeric form for a circular LEO.
        n = math.sqrt(MU_EARTH_KM3_S2 / (a**3))  # rad/s
        n_sun = 1.99106e-7  # rad/s, Earth's mean motion about the Sun
        cos_i = -(2.0 * n_sun * (a / R_EARTH_KM) ** 2) / (3.0 * j2 * n)
        cos_i = max(-1.0, min(1.0, cos_i))
        return math.degrees(math.acos(cos_i))

    @property
    def session_seconds(self) -> float:
        """Total sim seconds in the session — how long the flight lasts."""
        return self.period_seconds * self.orbits

    @property
    def real_seconds(self) -> float:
        """How long the session takes in wall-clock seconds."""
        return self.session_seconds / self.time_compression


@dataclass(frozen=True)
class OrbitPhase:
    """Where the spacecraft is in its lap, at one instant.

    `sunlit`, `in_pass` and `in_saa` overlap on purpose — a pass can happen
    in eclipse, and that combination is exactly the situation the power
    lesson is about (the transmitter is your biggest load and the array is
    giving you nothing).
    """

    t: float
    orbit_number: int  # 1-based
    orbit_fraction: float  # 0..1 through the current lap
    sunlit: bool
    in_pass: bool
    in_saa: bool
    pass_progress: float  # 0..1 across the current pass, else 0
    elevation_deg: float  # station elevation, 0 outside a pass
    seconds_to_next_aos: float  # to the next pass start; 0 while in one
    seconds_to_los: float  # to the end of the current pass; 0 outside one
    seconds_to_eclipse: float  # to the next shadow entry; 0 while in it
    seconds_to_sunrise: float  # to the next shadow exit; 0 while sunlit

    @property
    def label(self) -> str:
        """One phrase for the flight-status header. Ordered by what an
        operator would care about most in the moment — a pass is the thing
        you plan around, eclipse is the thing you survive."""
        if self.in_pass:
            return "Ground station pass"
        if self.in_saa:
            return "SAA crossing"
        return "Eclipse" if not self.sunlit else "Sunlit"


def _window(fraction: float, start: float, duration: float) -> tuple[bool, float]:
    """Is `fraction` inside the wrapped window, and how far through it?"""
    end = start + duration
    if end <= 1.0:
        inside = start <= fraction < end
    else:  # window wraps past the end of the lap
        inside = fraction >= start or fraction < (end - 1.0)
    if not inside:
        return False, 0.0
    offset = fraction - start
    if offset < 0:
        offset += 1.0
    return True, offset / duration if duration > 0 else 0.0


def _time_until(fraction: float, target: float, period: float) -> float:
    delta = target - fraction
    if delta < 0:
        delta += 1.0
    return delta * period


def phase_at(model: OrbitModel, t: float) -> OrbitPhase:
    """The whole orbit clock, as a pure function of sim seconds."""
    t = max(0.0, t)
    period = model.period_seconds
    orbit_number = int(t // period) + 1
    frac = (t % period) / period

    sunlit = frac < (1.0 - model.eclipse_fraction)
    eclipse_start = 1.0 - model.eclipse_fraction

    in_pass, pass_progress = _window(frac, model.pass_start_fraction, model.pass_duration_fraction)
    in_saa, _ = _window(frac, model.saa_start_fraction, model.saa_duration_fraction)

    # Elevation follows a half-sine across the window: 0 at AOS, max at
    # the midpoint, 0 at LOS. Real passes are asymmetric and depend on how
    # far off-zenith the track is; this is the shape that matters.
    elevation = math.sin(math.pi * pass_progress) * 82.0 if in_pass else 0.0

    return OrbitPhase(
        t=t,
        orbit_number=orbit_number,
        orbit_fraction=frac,
        sunlit=sunlit,
        in_pass=in_pass,
        in_saa=in_saa,
        pass_progress=pass_progress if in_pass else 0.0,
        elevation_deg=round(elevation, 2),
        seconds_to_next_aos=0.0 if in_pass else _time_until(frac, model.pass_start_fraction, period),
        seconds_to_los=(1.0 - pass_progress) * model.pass_duration_fraction * period if in_pass else 0.0,
        seconds_to_eclipse=0.0 if not sunlit else _time_until(frac, eclipse_start, period),
        seconds_to_sunrise=_time_until(frac, 0.0, period) if not sunlit else 0.0,
    )


def signal_strength_dbm(phase: OrbitPhase) -> float:
    """Received signal at the ground station. Outside a pass this is the
    receiver noise floor; inside one it tracks elevation, so the number
    rises through AOS, peaks overhead and falls away at LOS. A student
    who watches this learns to plan work around the window rather than
    wonder why a downlink command did nothing."""
    if not phase.in_pass:
        return NO_PASS_SIGNAL_DBM
    span = PEAK_PASS_SIGNAL_DBM - NO_PASS_SIGNAL_DBM
    return round(NO_PASS_SIGNAL_DBM + span * math.sin(math.pi * phase.pass_progress), 2)


def pass_windows(model: OrbitModel) -> list[dict]:
    """Every pass in the session, for the timeline strip and the debrief."""
    period = model.period_seconds
    out = []
    for orbit in range(model.orbits):
        start = orbit * period + model.pass_start_fraction * period
        out.append({
            "orbit": orbit + 1,
            "start_t": round(start, 1),
            "end_t": round(start + model.pass_duration_fraction * period, 1),
            "station": model.ground_station,
        })
    return out


def eclipse_windows(model: OrbitModel) -> list[dict]:
    period = model.period_seconds
    start_frac = 1.0 - model.eclipse_fraction
    return [
        {
            "orbit": orbit + 1,
            "start_t": round(orbit * period + start_frac * period, 1),
            "end_t": round((orbit + 1) * period, 1),
        }
        for orbit in range(model.orbits)
    ]


def saa_windows(model: OrbitModel) -> list[dict]:
    period = model.period_seconds
    return [
        {
            "orbit": orbit + 1,
            "start_t": round(orbit * period + model.saa_start_fraction * period, 1),
            "end_t": round(orbit * period + (model.saa_start_fraction + model.saa_duration_fraction) * period, 1),
        }
        for orbit in range(model.orbits)
    ]


def orbit_summary(model: OrbitModel) -> dict:
    """The numbers the briefing and the flight-status header show. All
    derived — nothing here is a literal, which is the whole point."""
    return {
        "altitude_km": round(model.altitude_km, 1),
        "period_minutes": round(model.period_seconds / 60.0, 1),
        "velocity_km_s": round(model.velocity_km_s, 2),
        "inclination_deg": round(model.inclination_deg, 1),
        "eclipse_fraction": model.eclipse_fraction,
        "eclipse_minutes": round(model.period_seconds * model.eclipse_fraction / 60.0, 1),
        "pass_minutes": round(model.period_seconds * model.pass_duration_fraction / 60.0, 1),
        "orbits": model.orbits,
        "session_minutes": round(model.session_seconds / 60.0, 1),
        "real_minutes": round(model.real_seconds / 60.0, 1),
        "time_compression": model.time_compression,
        "ground_station": model.ground_station,
    }


def model_from_config(config: dict) -> OrbitModel:
    """Variant `config.orbit` overrides, all optional."""
    raw = (config or {}).get("orbit", {}) or {}
    defaults = OrbitModel()
    return OrbitModel(
        altitude_km=float(raw.get("altitude_km", defaults.altitude_km)),
        orbits=int(raw.get("orbits", defaults.orbits)),
        eclipse_fraction=float(raw.get("eclipse_fraction", defaults.eclipse_fraction)),
        pass_start_fraction=float(raw.get("pass_start_fraction", defaults.pass_start_fraction)),
        pass_duration_fraction=float(raw.get("pass_duration_fraction", defaults.pass_duration_fraction)),
        saa_start_fraction=float(raw.get("saa_start_fraction", defaults.saa_start_fraction)),
        saa_duration_fraction=float(raw.get("saa_duration_fraction", defaults.saa_duration_fraction)),
        time_compression=float(raw.get("time_compression", defaults.time_compression)),
        ground_station=str(raw.get("ground_station", defaults.ground_station)),
    )

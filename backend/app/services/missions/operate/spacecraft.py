"""The spacecraft simulator (Operate v2, Stage 7C-2) — one physical state
that the orbit drives and the student's commands change.

**The architectural idea, because it explains every other file here:** the
state is never stored. It is recomputed from scratch on every read by
replaying the ordered command log from t=0 over the orbit clock.

    state(t) = simulate(orbit, params, commands)      # pure

Three things fall out of that, all of which we want:

* **No shared mutable state.** SatKit's whole simulation was one module
  level object every user on the server saw (K2), and one unauthenticated
  call could set `is_active = False` and kill it permanently with no way
  back (K3). The Stage 7B port fixed both by making telemetry a pure
  function of elapsed time; this keeps that property while adding a state
  that actually evolves.
* **Trivially testable.** A list of `(sim_t, command)` pairs goes in, an
  asserted state comes out. No database, no clock, no fixtures.
* **The debrief is free.** Replaying the flight is the same function with
  a different stop time, so `debrief.py` needs no separate machinery and
  can never disagree with what the student saw live.

Faults are not a script bolted onto the physics — they *are* the physics,
in two flavours, and the split is the pedagogy:

* **Injected** (`seu`, `beacon_lock`) — things that happen to you. Scheduled
  deterministically per variant, unavoidable, and the only correct answer
  is to notice and respond.
* **Emergent** (`brownout`, `wheel_saturation`, `storage_full`,
  `payload_overtemp`, `safe_mode`) — consequences of how *you* flew. A
  student who manages power and duty-cycles the payload simply never sees
  a brownout, which is precisely what good operations looks like.

Numbers are teaching-grade and deliberately tight (a 3U CubeSat with
body-mounted cells really does run a marginal power budget). The point is
that a payload left running through a 33-minute eclipse costs you the
mission, which is a real lesson and not one you can learn from a budget
table. Assumptions are surfaced on screen, per D-c.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.services.missions.operate.orbit import (
    OrbitModel,
    OrbitPhase,
    phase_at,
    signal_strength_dbm,
)

# Sim seconds per integration step. Every time constant in this model is
# hundreds to thousands of seconds, so 5 s is far finer than anything it
# needs to resolve, and it keeps a full 4-orbit replay to a few thousand
# steps — cheap enough to redo on every 2-second poll.
STEP_SECONDS = 10.0

PAYLOAD_ON = "ON"
PAYLOAD_STANDBY = "STANDBY"
PAYLOAD_OFF = "OFF"

MODE_NOMINAL = "NOMINAL"
MODE_SAFE = "SAFE"

# Attitude error above which the antenna is no longer pointing well enough
# to close the link. Desaturating puts you over it on purpose.
POINTING_LIMIT_DEG = 5.0


@dataclass(frozen=True)
class SpacecraftParams:
    """The vehicle. Every field is overridable from `variant.config.spacecraft`,
    and Stage 7C-9 fills them from the student's own passed design attempt so
    they fly the satellite they built."""

    # --- power ---------------------------------------------------------
    battery_capacity_wh: float = 20.0
    initial_soc: float = 0.80
    # Generation while sunlit at nominal pointing. Body-mounted cells on a
    # 3U give roughly this; deployables would give 2-3x and would remove
    # the power lesson, so the default vehicle deliberately doesn't have
    # them. Sized so that a payload left running is net-negative even in
    # daylight, a duty-cycled payload roughly breaks even, and a safed
    # spacecraft recovers over about one and a half orbits. Those three
    # behaviours are the whole power lesson.
    solar_array_w: float = 5.5
    bus_idle_w: float = 2.0
    payload_active_w: float = 6.0
    payload_standby_w: float = 1.5
    transmitter_w: float = 8.0
    desat_w: float = 1.5
    soc_warn: float = 0.40
    soc_safe_mode: float = 0.25
    soc_exit_safe: float = 0.50

    # --- data ----------------------------------------------------------
    storage_capacity_mb: float = 120.0
    science_take_mb: float = 20.0
    downlink_mbps: float = 1.0
    storage_warn_fraction: float = 0.80

    # --- attitude ------------------------------------------------------
    wheel_initial_rpm: float = 1200.0
    wheel_warn_rpm: float = 4500.0
    wheel_max_rpm: float = 6000.0
    # Gravity-gradient and aerodynamic torque have to go somewhere, and on
    # a wheel-controlled spacecraft they go into wheel speed. Sized so a
    # three-orbit session saturates if you never desaturate.
    wheel_accum_rpm_per_s: float = 0.28
    desat_rate_rpm_per_s: float = 20.0
    desat_duration_s: float = 180.0

    # --- thermal -------------------------------------------------------
    payload_temp_limit_c: float = 55.0
    thermal_tau_s: float = 400.0
    payload_tau_s: float = 700.0

    # --- CDHS ----------------------------------------------------------
    reboot_downtime_s: float = 120.0

    @classmethod
    def from_config(cls, config: dict) -> "SpacecraftParams":
        raw = (config or {}).get("spacecraft", {}) or {}
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: float(v) for k, v in raw.items() if k in known})


# --------------------------------------------------------------------------
# Faults
# --------------------------------------------------------------------------

@dataclass
class FaultOccurrence:
    """One raise/clear cycle of one fault. The unit the debrief and the
    anomaly half of the score both work in."""

    key: str
    raised_t: float
    response_window_s: float
    cleared_t: float | None = None
    cleared_by: str | None = None  # the command that cleared it

    @property
    def active(self) -> bool:
        return self.cleared_t is None

    @property
    def response_seconds(self) -> float | None:
        return None if self.cleared_t is None else self.cleared_t - self.raised_t

    @property
    def outcome(self) -> str:
        """`resolved` · `late` · `unresolved` — the three grades an anomaly
        response can earn. `late` means you did fix it, but only after the
        consequence had already landed.

        A fault that went away on its own scores **unresolved**, even
        though the timeline correctly shows it as cleared. A payload that
        cooled off because the spacecraft flew into eclipse was not an act
        of operations, and crediting it would reward waiting — the exact
        failure the v1 scoring had.
        """
        if self.cleared_t is None or self.cleared_by is None:
            return "unresolved"
        return "resolved" if (self.cleared_t - self.raised_t) <= self.response_window_s else "late"

    @property
    def self_cleared(self) -> bool:
        return self.cleared_t is not None and self.cleared_by is None


@dataclass
class SpacecraftState:
    """Everything about the vehicle at one instant. Telemetry is a *view*
    of this (`telemetry.py`), never a parallel source of truth."""

    t: float = 0.0
    phase: OrbitPhase | None = None

    # power
    battery_wh: float = 16.0
    battery_soc: float = 0.80
    net_power_w: float = 0.0
    generation_w: float = 0.0
    load_w: float = 0.0

    # data
    storage_used_mb: float = 0.0
    downlinked_mb: float = 0.0
    science_takes: int = 0
    science_dropped: int = 0

    # attitude
    wheel_rpm: float = 1200.0
    attitude_error_deg: float = 0.5
    desat_until_t: float = -1.0

    # thermal
    panel_temp_c: float = 20.0
    payload_temp_c: float = 22.0
    system_temp_c: float = 30.0

    # modes and equipment
    mode: str = MODE_NOMINAL
    payload_state: str = PAYLOAD_ON
    transmitter_on: bool = False

    # CDHS
    obc_uptime_s: float = 0.0
    obc_upsets: int = 0
    seu_pending: bool = False
    obc_wedged: bool = False
    obc_busy_until_t: float = -1.0

    # comms
    beacon_locked: bool = True
    packets_received: int = 0

    # accumulated history the objectives read
    min_soc_seen: float = 1.0
    max_payload_temp_c: float = 0.0
    safe_mode_entries: int = 0
    downlink_seconds: float = 0.0

    # Copied off `SpacecraftParams` at construction so a state object can
    # answer "how full is the memory" on its own — the console and the
    # objectives both ask, and neither should have to carry params around.
    science_take_mb_hint: float = 20.0
    storage_capacity_hint: float = 120.0

    faults: list[FaultOccurrence] = field(default_factory=list)
    log: list[dict] = field(default_factory=list)  # autonomous spacecraft events

    # Previous-step phase flags, so the log can report *transitions*
    # ("entering eclipse") rather than states ("in eclipse"), which is
    # what an operator actually needs to react to.
    prev_sunlit: bool | None = None
    prev_in_pass: bool | None = None
    prev_in_saa: bool | None = None

    def active_fault(self, key: str) -> FaultOccurrence | None:
        for f in reversed(self.faults):
            if f.key == key and f.active:
                return f
        return None

    @property
    def science_takes_downlinked(self) -> int:
        if self.science_take_mb_hint <= 0:
            return 0
        return int(self.downlinked_mb // self.science_take_mb_hint)

    @property
    def storage_fraction(self) -> float:
        return self.storage_used_mb / self.storage_capacity_hint if self.storage_capacity_hint else 0.0

    @property
    def link_ok(self) -> bool:
        """Can we actually close the link right now? Four independent ways
        to say no, and each one is a different lesson."""
        return (
            self.phase is not None
            and self.phase.in_pass
            and self.beacon_locked
            and self.attitude_error_deg < POINTING_LIMIT_DEG
            and self.mode != MODE_SAFE
            and not self.obc_wedged
        )


# Response windows: how long the student has from the fault being
# observable to it counting as a timely response. Sized against how fast
# the underlying physics actually bites.
RESPONSE_WINDOWS = {
    "brownout": 600.0,  # ~10 sim min before safe mode is unavoidable
    "wheel_saturation": 900.0,
    "seu": 600.0,
    "beacon_lock": 240.0,  # a pass is only ~480 s; half of it is the window
    "storage_full": 900.0,
    "payload_overtemp": 600.0,
    "safe_mode": 1200.0,
}


def _raise_fault(state: SpacecraftState, key: str, message: str) -> None:
    if state.active_fault(key) is not None:
        return
    state.faults.append(FaultOccurrence(key=key, raised_t=state.t, response_window_s=RESPONSE_WINDOWS[key]))
    _log(state, "ERROR", message)


def _clear_fault(state: SpacecraftState, key: str, by: str | None = None) -> None:
    fault = state.active_fault(key)
    if fault is None:
        return
    fault.cleared_t = state.t
    fault.cleared_by = by
    _log(state, "INFO", f"{key.replace('_', ' ').upper()}: condition cleared")


def _log(state: SpacecraftState, level: str, message: str) -> None:
    """The spacecraft event log — things the vehicle reports on its own,
    distinct from the command transcript. This is the channel SatKit had
    (`mission_logs`) and the Stage 7B port dropped, and it's the student's
    primary alert that something needs attention."""
    state.log.append({"t": round(state.t, 1), "level": level, "message": message})


# --------------------------------------------------------------------------
# Injected faults — scheduled, unavoidable, external
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class InjectedFault:
    key: str
    at_t: float
    message: str


def schedule_injected_faults(
    orbit: OrbitModel, config: dict, *, seed: int, concurrent: bool = False,
) -> list[InjectedFault]:
    """Which external events happen, and when.

    D-b: Cadet is fixed so a retry drills the same scenario, which is
    legitimate training. Engineer and above shuffle *which orbit* each
    event lands on from a per-attempt seed, so a second run isn't a
    memorisation exercise. The shuffle is still deterministic — same
    attempt, same flight, forever — which is what keeps grading fair and
    the replay honest.

    D-f: `concurrent` pulls the events onto the same orbit so a five-person
    crew has five things happening at once rather than four people watching
    one person work. It is an explicit argument rather than a config key
    because the config's `crew_concurrency` means "this variant *allows*
    it", which is only the same thing on a team attempt — the caller
    (`verifiers/operate.FlightContext`) is the one that knows.
    """
    period = orbit.period_seconds
    plan = (config or {}).get("injected_faults", ["seu", "beacon_lock"])
    shuffle = bool((config or {}).get("shuffle_faults", False))

    candidates = list(range(1, orbit.orbits + 1))
    out: list[InjectedFault] = []

    # A key can appear more than once — Flight Director schedules a second
    # upset precisely so the "when is REBOOT_OBC correct" lesson can fire.
    # Repeats always move to a later orbit; two upsets at the same instant
    # would latch the processor up with no chance to react, which teaches
    # nothing.
    distinct = list(dict.fromkeys(plan))
    seen: dict[str, int] = {}

    for key in plan:
        repeat = seen.get(key, 0)
        seen[key] = repeat + 1
        i = distinct.index(key)

        if concurrent:
            base = min(orbit.orbits, 2)
        elif shuffle:
            base = candidates[(seed + i * 7) % len(candidates)]
        else:
            base = min(orbit.orbits, i + 1)
        orbit_no = min(orbit.orbits, base + repeat)
        if repeat and orbit_no == base:  # already at the last orbit — step back instead
            orbit_no = max(1, base - repeat)

        if key == "seu":
            # SEUs happen in the South Atlantic Anomaly, so it fires when
            # the spacecraft is actually there rather than at an arbitrary
            # clock time. That's the point of modelling the SAA at all.
            at = (orbit_no - 1) * period + (orbit.saa_start_fraction + orbit.saa_duration_fraction / 2) * period
            out.append(InjectedFault("seu", at, "CDHS: single event upset detected — OBC uptime counter reset"))
        elif key == "beacon_lock":
            # At AOS, so the student loses the pass unless they fix it fast.
            at = (orbit_no - 1) * period + orbit.pass_start_fraction * period + 20.0
            out.append(InjectedFault(
                "beacon_lock", at, "COMMS: ground station reports no beacon lock — downlink unavailable",
            ))

    return sorted(out, key=lambda f: f.at_t)


# --------------------------------------------------------------------------
# Command effects
# --------------------------------------------------------------------------

@dataclass
class CommandOutcome:
    accepted: bool
    message: str
    penalty: str | None = None  # penalty key, if this was a harmful action


def _ts(state: SpacecraftState) -> str:
    total = int(state.t)
    return f"T+{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def apply_command(
    state: SpacecraftState, params: SpacecraftParams, *, base: str, arg: str,
) -> CommandOutcome:
    """One telecommand against the vehicle. Returns what the ground station
    reports back, which is the only feedback channel the student has.

    Every rejection here is a lesson: commanding a downlink with no station
    in view, or trying to leave safe mode before the battery has recovered,
    fails for the reason a real spacecraft would fail.
    """
    ts = _ts(state)

    # HELP and STATUS are ground-segment functions — they read what the
    # station already has and never touch the vehicle, so they work even
    # when the spacecraft is safed, wedged or rebooting. That's realistic
    # and it also means a confused student is never locked out of the one
    # thing that would unconfuse them.
    if base == "HELP":
        from app.services.missions.operate.commands import help_text
        return CommandOutcome(True, f"[{ts}] AVAILABLE GROUND TELECOMMANDS // {help_text()}")

    if base == "STATUS":
        p = state.phase
        return CommandOutcome(True, (
            f"[{ts}] BATT {state.battery_soc * 100:.0f}% ({state.net_power_w:+.1f}W) | "
            f"MODE {state.mode} | PAYLOAD {state.payload_state} | "
            f"WHEEL {state.wheel_rpm:.0f} RPM | PTG {state.attitude_error_deg:.1f}deg | "
            f"MEM {state.storage_used_mb:.0f}/{params.storage_capacity_mb:.0f} MB | "
            f"DOWNLINKED {state.downlinked_mb:.0f} MB | "
            f"{'IN PASS' if p and p.in_pass else 'NO STATION IN VIEW'}"
        ))

    # --- the OBC has to be able to hear you at all ----------------------
    if state.obc_wedged and base != "REBOOT_OBC":
        return CommandOutcome(False, f"[{ts}] NO RESPONSE — OBC latched up. Command not acknowledged.")
    if state.obc_busy_until_t > state.t:
        remaining = int(state.obc_busy_until_t - state.t)
        return CommandOutcome(False, f"[{ts}] OBC REBOOTING — link returns in {remaining}s. Command dropped.")
    # A pending upset corrupts roughly every third uplink until the
    # watchdog is reset. Deterministic on command count, so the replay and
    # the tests agree.
    if state.seu_pending and base not in ("RESET_WDT", "REBOOT_OBC", "HELP", "STATUS"):
        if (len(state.log) % 3) == 0:
            return CommandOutcome(False, f"[{ts}] UPLINK CRC FAIL — corrupted command register. Retry or RESET_WDT.")

    if state.mode == MODE_SAFE and base not in ("HELP", "STATUS", "EXIT_SAFE_MODE", "DOWNLOAD_TM", "RESET_WDT"):
        return CommandOutcome(
            False, f"[{ts}] REJECTED — spacecraft is in SAFE MODE. Restore power, then EXIT_SAFE_MODE.",
        )

    # --- CDHS -----------------------------------------------------------
    if base == "RESET_WDT":
        if state.seu_pending:
            state.seu_pending = False
            _clear_fault(state, "seu", "RESET_WDT")
            return CommandOutcome(True, f"[{ts}] OBC: WATCHDOG RESET // UPSET CLEARED, COMMAND REGISTER HEALTHY [0x00]")
        return CommandOutcome(True, f"[{ts}] OBC: WATCHDOG TIMER RESET SUCCESSFUL // COUNTER REGISTERS CLEAR [0x00]")

    if base == "REBOOT_OBC":
        if state.obc_wedged:
            state.obc_wedged = False
            state.seu_pending = False
            state.obc_busy_until_t = state.t + params.reboot_downtime_s
            state.obc_uptime_s = 0.0
            _clear_fault(state, "seu", "REBOOT_OBC")
            _log(state, "WARNING", "CDHS: cold reboot commanded — latch-up cleared, bus down for 120s")
            return CommandOutcome(True, f"[{ts}] CDHS: COLD REBOOT INITIATED. LATCH-UP CLEARED. LINK RETURNS IN 120s.")
        # Not latched up: this is the reach-for-the-big-red-button move,
        # and it costs a real two minutes of the flight. SatKit punished
        # REBOOT_OBC unconditionally; the lesson here is that the rule is
        # conditional, not that rebooting is always wrong.
        state.obc_busy_until_t = state.t + params.reboot_downtime_s
        state.obc_uptime_s = 0.0
        state.transmitter_on = False
        _log(state, "WARNING", "CDHS: unnecessary reboot commanded — 120s of flight time lost")
        return CommandOutcome(
            False,
            f"[{ts}] CRITICAL: OBC REBOOTING WITH NO FAULT LATCHED. GROUND LINK SEVERED FOR 120s.",
            penalty="needless_reboot",
        )

    # --- EPS ------------------------------------------------------------
    if base == "EPS_LOAD_SHED":
        state.payload_state = PAYLOAD_OFF
        state.transmitter_on = False
        _clear_fault(state, "brownout", "EPS_LOAD_SHED")
        return CommandOutcome(True, f"[{ts}] EPS: NON-ESSENTIAL LOADS SHED // PAYLOAD AND TX OFF, BUS ON ESSENTIALS")

    if base == "EPS_RECONFIG":
        _clear_fault(state, "brownout", "EPS_RECONFIG")
        return CommandOutcome(True, f"[{ts}] EPS: POWER BUS RECONFIGURED // CHARGE CONTROLLER RESTORED TO NOMINAL")

    if base == "EXIT_SAFE_MODE":
        if state.mode != MODE_SAFE:
            return CommandOutcome(False, f"[{ts}] NO-OP: spacecraft is not in safe mode.")
        if state.battery_soc < params.soc_exit_safe:
            return CommandOutcome(
                False,
                f"[{ts}] REJECTED — battery at {state.battery_soc * 100:.0f}%, "
                f"need {params.soc_exit_safe * 100:.0f}% to leave safe mode. Let it charge.",
                penalty="premature_safe_exit",
            )
        state.mode = MODE_NOMINAL
        _clear_fault(state, "safe_mode", "EXIT_SAFE_MODE")
        _log(state, "INFO", "MODE: nominal operations resumed")
        return CommandOutcome(True, f"[{ts}] MODE: SAFE MODE EXITED // NADIR POINTING REACQUIRED, LOADS AVAILABLE")

    # --- payload --------------------------------------------------------
    if base == "PAYLOAD_ON":
        state.payload_state = PAYLOAD_ON
        return CommandOutcome(True, f"[{ts}] PAYLOAD: INSTRUMENT POWERED // WARM-UP COMPLETE, READY TO COLLECT")
    if base == "PAYLOAD_OFF":
        state.payload_state = PAYLOAD_OFF
        _clear_fault(state, "brownout", "PAYLOAD_OFF")
        _clear_fault(state, "payload_overtemp", "PAYLOAD_OFF")
        return CommandOutcome(True, f"[{ts}] PAYLOAD: INSTRUMENT POWERED DOWN // LOAD REMOVED FROM BUS")
    if base == "PAYLOAD_STANDBY":
        state.payload_state = PAYLOAD_STANDBY
        _clear_fault(state, "payload_overtemp", "PAYLOAD_STANDBY")
        return CommandOutcome(True, f"[{ts}] PAYLOAD: STANDBY // HEATERS IDLE, INSTRUMENT COOLING")
    if base == "PAYLOAD_RESET":
        _clear_fault(state, "payload_overtemp", "PAYLOAD_RESET")
        return CommandOutcome(True, f"[{ts}] PAYLOAD: INSTRUMENT CONTROLLER RESET // SENSOR ARRAY BACK ONLINE")

    if base in ("COLLECT_SAMPLE", "QUEUE_SCIENCE"):
        if state.payload_state != PAYLOAD_ON:
            return CommandOutcome(False, f"[{ts}] REJECTED — payload is {state.payload_state}. PAYLOAD_ON first.")
        if state.storage_used_mb + params.science_take_mb > params.storage_capacity_mb:
            state.science_dropped += 1
            _log(state, "ERROR", "PAYLOAD: science take dropped — mass memory full")
            return CommandOutcome(
                False,
                f"[{ts}] DATA LOSS — mass memory full ({state.storage_used_mb:.0f}/"
                f"{params.storage_capacity_mb:.0f} MB). Downlink before collecting more.",
                penalty="data_loss",
            )
        state.storage_used_mb += params.science_take_mb
        state.science_takes += 1
        return CommandOutcome(
            True,
            f"[{ts}] PAYLOAD: SCIENCE TAKE {state.science_takes} CAPTURED // "
            f"{params.science_take_mb:.0f} MB BUFFERED ({state.storage_used_mb:.0f}/{params.storage_capacity_mb:.0f} MB)",
        )

    # --- ADCS -----------------------------------------------------------
    if base == "ADCS_DESAT":
        if state.desat_until_t > state.t:
            return CommandOutcome(False, f"[{ts}] NO-OP: magnetorquer desaturation already running.")
        state.desat_until_t = state.t + params.desat_duration_s
        note = ""
        if state.phase is not None and state.phase.in_pass:
            note = " // WARNING: ATTITUDE PERTURBED DURING PASS — DOWNLINK WILL DROP"
        _log(state, "INFO", "ADCS: magnetorquer desaturation started")
        return CommandOutcome(True, f"[{ts}] ADCS: MOMENTUM DUMP INITIATED // MAGNETORQUERS ACTIVE 180s{note}")

    if base == "ADCS_RECALIBRATE":
        return CommandOutcome(True, f"[{ts}] ADCS: GYROSCOPE RECALIBRATION COMPLETE // ATTITUDE ESTIMATE REFRESHED")

    # --- COMMS ----------------------------------------------------------
    if base == "UPDATE_BEACON":
        if not arg.strip():
            return CommandOutcome(
                False, f"[{ts}] SYNTAX ERROR — UPDATE_BEACON requires a period, e.g. UPDATE_BEACON 30",
            )
        state.beacon_locked = True
        _clear_fault(state, "beacon_lock", "UPDATE_BEACON")
        return CommandOutcome(
            True, f"[{ts}] TRX: BEACON RECONFIGURED, PERIOD {arg.strip()} // GROUND STATION REPORTS LOCK",
        )

    if base == "DOWNLINK_SCIENCE":
        if state.phase is None or not state.phase.in_pass:
            aos = int(state.phase.seconds_to_next_aos) if state.phase else 0
            return CommandOutcome(
                False,
                f"[{ts}] REJECTED — no station in view. Next AOS in {aos // 60}m {aos % 60}s.",
                penalty="downlink_out_of_pass",
            )
        if state.storage_used_mb <= 0:
            return CommandOutcome(False, f"[{ts}] NO-OP: mass memory empty, nothing to downlink.")
        state.transmitter_on = True
        return CommandOutcome(
            True, f"[{ts}] TRX: TRANSMITTER ON // DOWNLINKING {state.storage_used_mb:.0f} MB AT "
                   f"{params.downlink_mbps:.1f} Mbps",
        )

    if base == "DOWNLINK_STOP":
        state.transmitter_on = False
        return CommandOutcome(True, f"[{ts}] TRX: TRANSMITTER OFF // {state.downlinked_mb:.0f} MB DOWNLINKED TOTAL")

    if base == "DOWNLOAD_TM":
        if state.phase is None or not state.phase.in_pass:
            aos = int(state.phase.seconds_to_next_aos) if state.phase else 0
            return CommandOutcome(
                False,
                f"[{ts}] REJECTED — no station in view. Next AOS in {aos // 60}m {aos % 60}s.",
                penalty="downlink_out_of_pass",
            )
        return CommandOutcome(True, f"[{ts}] TRX: HOUSEKEEPING TELEMETRY DUMPED // PACKETS 0x001 THROUGH 0x14F")

    return CommandOutcome(False, f"[{ts}] ERROR: UNRECOGNIZED UPLINK MACRO. TYPE 'HELP' FOR SYSTEM TELECOMMANDS.")


# --------------------------------------------------------------------------
# The integration step
# --------------------------------------------------------------------------

def _lag(current: float, target: float, dt: float, tau: float) -> float:
    """First-order thermal lag. Nothing on a spacecraft changes temperature
    instantly, and the lag is why *duty-cycling* the payload works where
    just turning it off at the last moment doesn't."""
    return current + (target - current) * (1.0 - math.exp(-dt / tau))


def _phase_events(state: SpacecraftState, phase: OrbitPhase, orbit: OrbitModel) -> None:
    """The spacecraft narrating its own orbit.

    This is the channel SatKit had as `mission_logs` and the v1 port
    dropped entirely, and it's what makes the console watchable rather than
    a wall of numbers: a student learns the rhythm of an orbit — sunrise,
    pass, sunset — by being told about it, and then starts anticipating it.
    The eclipse warning in particular is the difference between a power
    lesson and a power ambush.
    """
    if state.prev_in_pass is not None and phase.in_pass != state.prev_in_pass:
        if phase.in_pass:
            _log(state, "INFO", f"COMMS: AOS — {orbit.ground_station} acquired, "
                                f"pass window open for {orbit.period_seconds * orbit.pass_duration_fraction / 60:.0f} min")
        else:
            _log(state, "INFO", f"COMMS: LOS — {orbit.ground_station} out of view, "
                                f"{state.downlinked_mb:.0f} MB downlinked so far")
    if state.prev_sunlit is not None and phase.sunlit != state.prev_sunlit:
        if phase.sunlit:
            _log(state, "INFO", f"EPS: sunrise — array generating, battery at {state.battery_soc * 100:.0f}%")
        else:
            _log(state, "WARNING", f"EPS: eclipse entry — no generation for "
                                   f"{orbit.period_seconds * orbit.eclipse_fraction / 60:.0f} min, "
                                   f"battery at {state.battery_soc * 100:.0f}%, drawing {state.load_w:.1f}W")
    if state.prev_in_saa is not None and phase.in_saa and not state.prev_in_saa:
        _log(state, "INFO", "CDHS: entering South Atlantic Anomaly — elevated upset risk")

    state.prev_sunlit = phase.sunlit
    state.prev_in_pass = phase.in_pass
    state.prev_in_saa = phase.in_saa


def _step(state: SpacecraftState, params: SpacecraftParams, orbit: OrbitModel, dt: float) -> None:
    phase = phase_at(orbit, state.t)
    state.phase = phase
    _phase_events(state, phase, orbit)

    # --- safe mode forces a configuration -------------------------------
    if state.mode == MODE_SAFE:
        state.payload_state = PAYLOAD_OFF
        state.transmitter_on = False

    rebooting = state.obc_busy_until_t > state.t
    if rebooting:
        state.transmitter_on = False

    # --- power ----------------------------------------------------------
    pointing_factor = 1.0
    if state.attitude_error_deg > POINTING_LIMIT_DEG:
        pointing_factor = max(0.25, math.cos(math.radians(min(state.attitude_error_deg, 75.0))))
    state.generation_w = (params.solar_array_w * pointing_factor) if phase.sunlit else 0.0

    load = params.bus_idle_w
    if state.payload_state == PAYLOAD_ON:
        load += params.payload_active_w
    elif state.payload_state == PAYLOAD_STANDBY:
        load += params.payload_standby_w
    if state.transmitter_on and phase.in_pass:
        load += params.transmitter_w
    if state.desat_until_t > state.t:
        load += params.desat_w
    state.load_w = load
    state.net_power_w = state.generation_w - load

    state.battery_wh = max(0.0, min(params.battery_capacity_wh, state.battery_wh + state.net_power_w * dt / 3600.0))
    state.battery_soc = state.battery_wh / params.battery_capacity_wh
    state.min_soc_seen = min(state.min_soc_seen, state.battery_soc)

    # --- attitude -------------------------------------------------------
    if state.desat_until_t > state.t:
        state.wheel_rpm = max(0.0, state.wheel_rpm - params.desat_rate_rpm_per_s * dt)
    else:
        state.wheel_rpm += params.wheel_accum_rpm_per_s * dt
    state.wheel_rpm = min(state.wheel_rpm, params.wheel_max_rpm)

    if state.wheel_rpm >= params.wheel_max_rpm:
        error = 25.0  # wheels saturated: no control authority left
    else:
        over = max(0.0, state.wheel_rpm - params.wheel_warn_rpm)
        span = max(1.0, params.wheel_max_rpm - params.wheel_warn_rpm)
        error = 0.5 + (over / span) * 6.0
    if state.desat_until_t > state.t:
        error += 6.0  # magnetorquers perturb pointing while they work
    if state.mode == MODE_SAFE:
        error = max(error, 12.0)  # sun-pointing, not nadir — no downlink
    state.attitude_error_deg = round(error, 2)

    # --- thermal --------------------------------------------------------
    panel_target = 45.0 if phase.sunlit else -20.0
    state.panel_temp_c = _lag(state.panel_temp_c, panel_target, dt, params.thermal_tau_s)

    payload_target = 18.0 + (8.0 if phase.sunlit else -8.0)
    if state.payload_state == PAYLOAD_ON:
        payload_target += 34.0
    elif state.payload_state == PAYLOAD_STANDBY:
        payload_target += 10.0
    state.payload_temp_c = _lag(state.payload_temp_c, payload_target, dt, params.payload_tau_s)
    state.max_payload_temp_c = max(state.max_payload_temp_c, state.payload_temp_c)

    state.system_temp_c = _lag(state.system_temp_c, 20.0 + (15.0 if phase.sunlit else 0.0), dt, params.thermal_tau_s)

    # --- comms ----------------------------------------------------------
    if phase.in_pass and state.beacon_locked and not rebooting:
        state.packets_received += int(4 * dt)

    if state.link_ok and state.transmitter_on and state.storage_used_mb > 0:
        mb = (params.downlink_mbps / 8.0) * dt
        moved = min(mb, state.storage_used_mb)
        state.storage_used_mb -= moved
        state.downlinked_mb += moved
        state.downlink_seconds += dt
    if not phase.in_pass:
        state.transmitter_on = False  # LOS: nothing to transmit to

    # --- CDHS -----------------------------------------------------------
    state.obc_uptime_s = 0.0 if rebooting else state.obc_uptime_s + dt

    # --- emergent faults ------------------------------------------------
    # Raised from the state itself, not from a script. A student who flies
    # well never sees most of these, which is the correct outcome.
    if state.battery_soc < params.soc_warn and state.net_power_w < 0 and state.mode != MODE_SAFE:
        _raise_fault(
            state, "brownout",
            f"EPS: battery at {state.battery_soc * 100:.0f}% and falling — negative power balance",
        )
    elif state.battery_soc >= params.soc_warn:
        _clear_fault(state, "brownout")

    if state.battery_soc < params.soc_safe_mode and state.mode != MODE_SAFE:
        state.mode = MODE_SAFE
        state.safe_mode_entries += 1
        _raise_fault(state, "safe_mode", "MODE: undervoltage — spacecraft entered SAFE MODE autonomously")

    if state.wheel_rpm >= params.wheel_warn_rpm:
        _raise_fault(
            state, "wheel_saturation",
            f"ADCS: reaction wheel at {state.wheel_rpm:.0f} RPM — approaching saturation",
        )
    elif state.wheel_rpm < params.wheel_warn_rpm * 0.85:
        _clear_fault(state, "wheel_saturation", "ADCS_DESAT")

    if state.storage_used_mb >= params.storage_capacity_mb * params.storage_warn_fraction:
        _raise_fault(
            state, "storage_full",
            f"CDHS: mass memory {state.storage_used_mb / params.storage_capacity_mb * 100:.0f}% full",
        )
    elif state.storage_used_mb < params.storage_capacity_mb * 0.5:
        _clear_fault(state, "storage_full", "DOWNLINK_SCIENCE")

    if state.payload_temp_c >= params.payload_temp_limit_c:
        _raise_fault(
            state, "payload_overtemp",
            f"PAYLOAD: instrument at {state.payload_temp_c:.0f}C — above {params.payload_temp_limit_c:.0f}C limit",
        )
    elif state.payload_temp_c < params.payload_temp_limit_c - 8.0:
        _clear_fault(state, "payload_overtemp")

    state.t += dt


def _inject(state: SpacecraftState, fault: InjectedFault, params: SpacecraftParams) -> None:
    if fault.key == "seu":
        state.obc_upsets += 1
        state.obc_uptime_s = 0.0
        if state.seu_pending:
            # They ignored the first one. A second upset on an already
            # degraded bus latches the processor up, and now — and only
            # now — REBOOT_OBC is the correct action.
            state.obc_wedged = True
            _log(state, "ERROR", "CDHS: second upset on a degraded bus — OBC LATCHED UP. Cold reboot required.")
        else:
            state.seu_pending = True
        _raise_fault(state, "seu", fault.message)
    elif fault.key == "beacon_lock":
        state.beacon_locked = False
        state.transmitter_on = False
        _raise_fault(state, "beacon_lock", fault.message)


# --------------------------------------------------------------------------
# The replay
# --------------------------------------------------------------------------

@dataclass
class SimResult:
    state: SpacecraftState
    trace: list[dict]
    command_results: list[CommandOutcome]


def simulate(
    *,
    orbit: OrbitModel,
    params: SpacecraftParams,
    commands: list[dict],
    until_t: float,
    injected: list[InjectedFault],
    trace_points: int = 0,
) -> SimResult:
    """Replay the flight from t=0 to `until_t`.

    `commands` are `{"sim_t": float, "base": str, "arg": str}` in issue
    order — the same list the attempt's event log stores, so what the
    student saw and what the debrief shows can never diverge.

    `trace_points > 0` samples the flight evenly for the debrief charts.
    """
    until_t = max(0.0, min(until_t, orbit.session_seconds))
    state = SpacecraftState(
        battery_wh=params.battery_capacity_wh * params.initial_soc,
        battery_soc=params.initial_soc,
        wheel_rpm=params.wheel_initial_rpm,
        min_soc_seen=params.initial_soc,
        science_take_mb_hint=params.science_take_mb,
        storage_capacity_hint=params.storage_capacity_mb,
    )
    state.phase = phase_at(orbit, 0.0)
    _log(state, "INFO", f"FLIGHT: session started — {orbit.orbits} orbits, station {orbit.ground_station}")

    pending = sorted(commands, key=lambda c: c.get("sim_t", 0.0))
    cmd_i = 0
    inj = sorted(injected, key=lambda f: f.at_t)
    inj_i = 0

    trace: list[dict] = []
    trace_every = (until_t / trace_points) if trace_points > 0 else None
    next_trace = 0.0

    results: list[CommandOutcome] = []
    guard = 0
    while state.t < until_t and guard < 100_000:
        guard += 1

        while inj_i < len(inj) and inj[inj_i].at_t <= state.t:
            _inject(state, inj[inj_i], params)
            inj_i += 1

        while cmd_i < len(pending) and pending[cmd_i].get("sim_t", 0.0) <= state.t:
            c = pending[cmd_i]
            results.append(apply_command(state, params, base=c.get("base", ""), arg=c.get("arg", "")))
            cmd_i += 1

        if trace_every is not None and state.t >= next_trace:
            trace.append(_trace_point(state, params))
            next_trace += trace_every

        _step(state, params, orbit, max(0.001, min(STEP_SECONDS, until_t - state.t)))

    # Anything scheduled or issued exactly at the stop time still counts.
    while inj_i < len(inj) and inj[inj_i].at_t <= until_t:
        _inject(state, inj[inj_i], params)
        inj_i += 1
    while cmd_i < len(pending) and pending[cmd_i].get("sim_t", 0.0) <= until_t:
        c = pending[cmd_i]
        results.append(apply_command(state, params, base=c.get("base", ""), arg=c.get("arg", "")))
        cmd_i += 1

    state.t = until_t
    state.phase = phase_at(orbit, until_t)
    if trace_every is not None:
        trace.append(_trace_point(state, params))

    return SimResult(state=state, trace=trace, command_results=results)


def _trace_point(state: SpacecraftState, params: SpacecraftParams) -> dict:
    p = state.phase
    return {
        "t": round(state.t, 1),
        "soc": round(state.battery_soc * 100, 1),
        "wheel_rpm": round(state.wheel_rpm, 0),
        "payload_temp": round(state.payload_temp_c, 1),
        "panel_temp": round(state.panel_temp_c, 1),
        "signal": signal_strength_dbm(p) if p else -120.0,
        "storage": round(state.storage_used_mb, 1),
        "downlinked": round(state.downlinked_mb, 1),
        "sunlit": bool(p.sunlit) if p else True,
        "in_pass": bool(p.in_pass) if p else False,
    }


def project_state(
    *, orbit: OrbitModel, params: SpacecraftParams, commands: list[dict], at_t: float,
    injected: list[InjectedFault],
) -> SpacecraftState:
    """The live read — the whole flight replayed up to now."""
    return simulate(
        orbit=orbit, params=params, commands=commands, until_t=at_t, injected=injected,
    ).state


__all__ = [
    "MODE_NOMINAL", "MODE_SAFE", "PAYLOAD_OFF", "PAYLOAD_ON", "PAYLOAD_STANDBY",
    "POINTING_LIMIT_DEG", "CommandOutcome", "FaultOccurrence", "InjectedFault",
    "SimResult", "SpacecraftParams", "SpacecraftState", "apply_command",
    "project_state", "schedule_injected_faults", "simulate",
]

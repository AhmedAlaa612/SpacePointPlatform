"""The anomaly library (Operate v2, Stage 7C-3/7C-7).

Seven failure modes drawn from things that actually go wrong on CubeSats.
Each is one authored record carrying both halves of the mission: what the
simulator does about it, and what the student is taught about it. Writing
a new anomaly writes its own lesson — the Ops Handbook (§5.2 of the plan)
is a rendering of this file, not a second document that can drift out of
sync with the code.

**Injected vs emergent** is the organising idea, and it is the difference
between an exercise and a drill:

* *Injected* faults happen **to** you. They are scheduled deterministically
  per variant (`spacecraft.schedule_injected_faults`), you cannot prevent
  them, and the only correct answer is to notice quickly and respond
  correctly.
* *Emergent* faults happen **because of** you. Nothing schedules a
  brownout — it is what a negative power balance eventually produces. A
  student who duty-cycles the payload never sees one, and that is the
  correct outcome, not a missing feature.

That split also fixes the deepest problem with the v1 port: there, the
health lights named the failing subsystem, so "diagnosis" was reading a
label. Here the student sees a battery percentage falling and an array
current of zero, and has to work out that they are in eclipse with the
payload still running.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnomalySpec:
    key: str
    title: str
    subsystem: str
    origin: str  # "injected" | "emergent"
    # What the student can actually see. These are `telemetry.CHANNELS`
    # keys, so the handbook can point at the exact readout to watch.
    symptom_channels: tuple[str, ...]
    symptom: str
    meaning: str
    action: str
    if_ignored: str
    commands: tuple[str, ...]
    # Weight in the anomaly half of the score. Losing a whole ground
    # station pass costs more than a warm instrument.
    weight: float = 1.0


LIBRARY: tuple[AnomalySpec, ...] = (
    AnomalySpec(
        key="seu",
        title="Single event upset",
        subsystem="CDHS",
        origin="injected",
        symptom_channels=("obc_uptime_s",),
        symptom="OBC uptime resets to zero, and roughly every third command comes back "
                "'UPLINK CRC FAIL'.",
        meaning="A charged particle flipped a bit in the processor — you are crossing the "
                "South Atlantic Anomaly, where Earth's radiation belt dips closest to the "
                "surface. This is routine in low Earth orbit, not a broken spacecraft.",
        action="RESET_WDT clears the upset and restores the command register. Do it "
               "promptly: a second upset on an already-degraded bus latches the processor "
               "up, and then only a cold REBOOT_OBC recovers it — at the cost of 120 "
               "seconds of flight time.",
        if_ignored="A second upset latches up the OBC. It stops accepting commands entirely "
                   "until you reboot it, and you lose whatever was happening at the time.",
        commands=("RESET_WDT", "REBOOT_OBC"),
        weight=1.2,
    ),
    AnomalySpec(
        key="beacon_lock",
        title="Beacon lock failure",
        subsystem="COMMS",
        origin="injected",
        symptom_channels=("signal_strength", "packets_received"),
        symptom="Signal strength climbs normally as the pass begins, but the packet counter "
                "stays frozen and the link reads 'No beacon lock'.",
        meaning="The spacecraft is transmitting and the station can hear the carrier, but "
                "the beacon period drifted and the receiver can't synchronise to it. You "
                "have a radio link and no data link — they are not the same thing.",
        action="UPDATE_BEACON with a period, e.g. `UPDATE_BEACON 30`. The argument is "
               "required; the command does nothing without it.",
        if_ignored="You lose the entire pass. Passes are about eight minutes long and the "
                   "next one is an orbit and a half away, so this is the most expensive "
                   "minute of inattention available to you.",
        commands=("UPDATE_BEACON",),
        weight=1.5,
    ),
    AnomalySpec(
        key="brownout",
        title="Negative power balance",
        subsystem="EPS",
        origin="emergent",
        symptom_channels=("battery_soc", "net_power_w", "solar_current"),
        symptom="Battery charge falling steadily, power balance negative, array current at "
                "zero.",
        meaning="You are in eclipse — roughly a third of every orbit — and the loads you "
                "left running are draining the battery with nothing coming in. The payload "
                "is almost always the culprit: it is your single biggest discretionary load.",
        action="PAYLOAD_OFF before you enter shadow, or EPS_LOAD_SHED to drop everything "
               "non-essential at once. Watch the 'time to eclipse' countdown in the flight "
               "header and get ahead of it rather than reacting to it.",
        if_ignored="Below 25% the spacecraft safes itself autonomously: payload off, "
                   "transmitter off, sun-pointing instead of nadir. You then need about an "
                   "orbit and a half of charging before it will let you back out.",
        commands=("PAYLOAD_OFF", "EPS_LOAD_SHED", "PAYLOAD_STANDBY"),
        weight=1.3,
    ),
    AnomalySpec(
        key="wheel_saturation",
        title="Reaction wheel saturation",
        subsystem="ADCS",
        origin="emergent",
        symptom_channels=("wheel_rpm", "attitude_error_deg"),
        symptom="Wheel RPM climbing steadily toward 6000, and pointing error creeping up "
                "with it.",
        meaning="Gravity-gradient and aerodynamic torque act on the spacecraft constantly. "
                "A reaction wheel absorbs that momentum by spinning faster, but it cannot "
                "do so forever — once it saturates, it has no control authority left and "
                "the spacecraft simply drifts.",
        action="ADCS_DESAT runs the magnetorquers against Earth's magnetic field to dump "
               "momentum overboard. It takes 180 seconds and it perturbs pointing while it "
               "works, so do it between passes — never during one.",
        if_ignored="At saturation you lose attitude control. Pointing error goes to 25 "
                   "degrees, the antenna no longer looks at the ground station, and every "
                   "remaining pass downlinks nothing at all.",
        commands=("ADCS_DESAT",),
        weight=1.3,
    ),
    AnomalySpec(
        key="storage_full",
        title="Mass memory saturation",
        subsystem="CDHS",
        origin="emergent",
        symptom_channels=("storage_used_mb",),
        symptom="Mass memory above 80% and still climbing.",
        meaning="You are collecting science faster than you are getting it to the ground. "
                "This is the data budget: generation is cheap and continuous, downlink is "
                "expensive and only available for eight minutes at a time.",
        action="DOWNLINK_SCIENCE during your next pass, and stop collecting until you have "
               "room. Plan collection around the pass schedule rather than the other way "
               "round.",
        if_ignored="New science takes are refused outright and the data is lost. You cannot "
                   "recover a take you never captured, so the mission objective can become "
                   "unreachable.",
        commands=("DOWNLINK_SCIENCE",),
        weight=1.0,
    ),
    AnomalySpec(
        key="payload_overtemp",
        title="Instrument over-temperature",
        subsystem="PAYLOAD",
        origin="emergent",
        symptom_channels=("payload_temp_c",),
        symptom="Instrument temperature above 55 C after a long sunlit arc.",
        meaning="The instrument dissipates heat whenever it is powered, and a CubeSat has "
                "no active cooling — only radiators and thermal mass. Leaving it on through "
                "a full 62-minute sunlit arc is what overheats it.",
        action="PAYLOAD_STANDBY or PAYLOAD_OFF and let it radiate. Duty-cycle the "
               "instrument: power it for the collection you need, then idle it.",
        if_ignored="The instrument derates and the science it returns is degraded. Nothing "
                   "dramatic happens on the console, which is exactly why thermal problems "
                   "get missed.",
        commands=("PAYLOAD_STANDBY", "PAYLOAD_OFF", "PAYLOAD_RESET"),
        weight=0.8,
    ),
    AnomalySpec(
        key="safe_mode",
        title="Autonomous safe mode",
        subsystem="EPS",
        origin="emergent",
        symptom_channels=("battery_soc",),
        symptom="Mode reads SAFE. Payload and transmitter are off and will not turn on; "
                "most commands come back REJECTED.",
        meaning="The spacecraft protected itself. Below 25% state of charge the flight "
                "software sheds every non-essential load and turns the vehicle to point at "
                "the Sun. It is doing the right thing — this is a symptom, not a fault.",
        action="You cannot command your way out of this. Let the battery charge back above "
               "50%, then EXIT_SAFE_MODE. Trying earlier is refused, and on a real "
               "spacecraft trying repeatedly is how you turn a recoverable day into a lost "
               "one.",
        if_ignored="Nothing works. No science, no downlink, no objectives — for as long as "
                   "it takes.",
        commands=("EXIT_SAFE_MODE",),
        weight=1.0,
    ),
)

BY_KEY: dict[str, AnomalySpec] = {a.key: a for a in LIBRARY}


def handbook(*, disclosure: str) -> list[dict]:
    """The Ops Handbook (plan §5.2) — the anomaly library rendered as the
    flight rules document an operator actually works from.

    D-d: it is available *during* flight at every difficulty, because real
    flight teams fly with their rules open and treating that as cheating
    would teach the wrong lesson. What difficulty controls is how much of
    it is written down for you:

    * `full`      — symptom, meaning, action, consequence. Cadet.
    * `symptoms`  — symptom and meaning; you work out the response. Engineer.
    * `reference` — the fault exists and here is what to watch. You are the
                    flight director. Flight Director.
    """
    out = []
    for spec in LIBRARY:
        entry = {
            "key": spec.key,
            "title": spec.title,
            "subsystem": spec.subsystem,
            "origin": spec.origin,
            "symptom_channels": list(spec.symptom_channels),
            "symptom": spec.symptom,
        }
        if disclosure in ("full", "symptoms"):
            entry["meaning"] = spec.meaning
        if disclosure == "full":
            entry["action"] = spec.action
            entry["if_ignored"] = spec.if_ignored
            entry["commands"] = list(spec.commands)
        out.append(entry)
    return out


def weight_for(key: str) -> float:
    spec = BY_KEY.get(key)
    return spec.weight if spec else 1.0


def title_for(key: str) -> str:
    spec = BY_KEY.get(key)
    return spec.title if spec else key.replace("_", " ").title()


def subsystem_for(key: str) -> str:
    spec = BY_KEY.get(key)
    return spec.subsystem if spec else "CDHS"


def teaching_for(key: str) -> dict:
    """Full disclosure, used by the debrief regardless of difficulty — once
    the flight is over, withholding the explanation serves nobody."""
    spec = BY_KEY.get(key)
    if spec is None:
        return {}
    return {
        "title": spec.title,
        "symptom": spec.symptom,
        "meaning": spec.meaning,
        "action": spec.action,
        "if_ignored": spec.if_ignored,
        "commands": list(spec.commands),
    }

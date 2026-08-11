"""Seed the design mission (CubeSat mission design, ported from Madar) —
the ONE `missions` row, its three difficulty variants, and the shared
component library students pick from.

    python scripts/missions_seed_design.py [--dry-run]

MISSIONS_REPORT.md Ch.3's naming trap, stated plainly for whoever edits
this next: **all of Madar is one mission.** Not one per student, not one
per subsystem. This script creates exactly one `missions` row
(`kind='design'`), three `mission_variants` rows (Cadet/Engineer/Flight
Director — the pass/fail thresholds a student can never edit, P7-6), and
fifteen `design_component_library` rows (the component catalogue,
transcribed from Madar's own `seed.py`, with dimensions parsed once here
into three numeric columns instead of the free-text string that produced
F3 — every seeded dimension used "×" (U+00D7), which Madar's parser never
handled).

Idempotent: re-running skips anything already present (mission by slug,
variants by (mission, position), components by name). Deliberately not a
migration, same reasoning as `seed_inventory.py` — this is reference data,
somebody's decision, not schema, and must not silently re-apply on deploy.
"""

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.models.missions.design import DesignComponentLibrary  # noqa: E402
from app.models.missions.mission import Mission, MissionVariant  # noqa: E402
from app.models.user import User  # noqa: E402

MISSION_SLUG = "cubesat-design"

# Engineer matches Madar's own default MissionConstraint values exactly —
# this becomes the "standard" difficulty. Cadet is easier (looser margins,
# bigger budgets, closer/simpler link); Flight Director is harder (tighter
# margins, smaller budgets, farther/stricter link). power_per_solar_cell_w
# is a physical constant, not a difficulty knob, so it doesn't vary.
VARIANTS = [
    dict(
        label="Cadet", position=1, points=100,
        config=dict(
            max_storage_kb=2_097_152.0, required_storage_margin_kb=0.0,
            power_per_solar_cell_w=1.1, maximum_budget_aed=3000.0,
            assumed_distance_km=400.0, transmit_power_dbm=30.0,
            good_link_margin_threshold_db=0.0, weak_link_margin_threshold_db=-5.0,
        ),
    ),
    dict(
        label="Engineer", position=2, points=200,
        config=dict(
            max_storage_kb=1_048_576.0, required_storage_margin_kb=104_857.6,
            power_per_solar_cell_w=1.1, maximum_budget_aed=2000.0,
            assumed_distance_km=500.0, transmit_power_dbm=30.0,
            good_link_margin_threshold_db=3.0, weak_link_margin_threshold_db=0.0,
        ),
    ),
    dict(
        label="Flight Director", position=3, points=350,
        config=dict(
            max_storage_kb=524_288.0, required_storage_margin_kb=157_286.4,
            power_per_solar_cell_w=1.1, maximum_budget_aed=1500.0,
            assumed_distance_km=700.0, transmit_power_dbm=30.0,
            good_link_margin_threshold_db=6.0, weak_link_margin_threshold_db=2.0,
        ),
    ),
]

# Transcribed verbatim from missionportal/backend/seed.py, dims parsed once
# here (L, W, H in mm) instead of left as a "50×50×30" string (F3).
COMPONENTS = [
    dict(component_name="Nano Star Tracker", subsystem="ADCS", example_role="Attitude determination",
         scaled_description="Compact star tracker for precise 3-axis orientation using star pattern recognition.",
         length_mm=50.0, width_mm=50.0, height_mm=30.0, scaled_mass_g=85.0, voltage_v=5.0, current_ma=250.0,
         data_size="12 KB/s", assumed_cost_usd=4500.0, temperature_range="-20 to +60C",
         key_specs="Accuracy: 2 arcsec, Update rate: 4 Hz", component_code="ADCS-ST-001"),
    dict(component_name="MEMS Reaction Wheel", subsystem="ADCS", example_role="Attitude control",
         scaled_description="Miniaturized reaction wheel providing precise torque for CubeSat attitude maneuvers.",
         length_mm=44.0, width_mm=44.0, height_mm=20.0, scaled_mass_g=120.0, voltage_v=5.0, current_ma=400.0,
         data_size="1 KB/s", assumed_cost_usd=2800.0, temperature_range="-30 to +70C",
         key_specs="Max torque: 1 mNm, Max speed: 7000 RPM", component_code="ADCS-RW-001"),
    dict(component_name="IMU Module", subsystem="ADCS", example_role="Rate sensing",
         scaled_description="6-DOF inertial measurement unit combining 3-axis gyroscope and 3-axis accelerometer.",
         length_mm=25.0, width_mm=25.0, height_mm=10.0, scaled_mass_g=15.0, voltage_v=3.3, current_ma=50.0,
         data_size="2 KB/s", assumed_cost_usd=350.0, temperature_range="-40 to +85C",
         key_specs="Gyro: +/-500 deg/s, Accel: +/-16g", component_code="ADCS-IMU-001"),
    dict(component_name="OBC (On-Board Computer)", subsystem="CDHS", example_role="Mission computer",
         scaled_description="Radiation-tolerant ARM-based OBC for mission data handling and task scheduling.",
         length_mm=96.0, width_mm=90.0, height_mm=12.0, scaled_mass_g=94.0, voltage_v=3.3, current_ma=300.0,
         data_size="100 MB storage", assumed_cost_usd=3200.0, temperature_range="-40 to +85C",
         key_specs="ARM Cortex-M7, 256 MB RAM, 8 GB Flash", component_code="CDHS-OBC-001"),
    dict(component_name="Solid-State Recorder", subsystem="CDHS", example_role="Data storage",
         scaled_description="High-capacity solid-state storage module for mission data buffering before downlink.",
         length_mm=70.0, width_mm=50.0, height_mm=15.0, scaled_mass_g=60.0, voltage_v=3.3, current_ma=150.0,
         data_size="32 GB capacity", assumed_cost_usd=1200.0, temperature_range="-25 to +75C",
         key_specs="Write: 150 MB/s, Read: 300 MB/s", component_code="CDHS-SSR-001"),
    dict(component_name="Triple-Junction Solar Panel", subsystem="EPS", example_role="Power generation",
         scaled_description="High-efficiency GaAs triple-junction solar cell panel for CubeSat power generation.",
         length_mm=100.0, width_mm=82.0, height_mm=3.0, scaled_mass_g=55.0, voltage_v=5.0, current_ma=800.0,
         data_size="N/A", assumed_cost_usd=1800.0, temperature_range="-180 to +120C",
         key_specs="Efficiency: 29.5%, Voc: 5.2V", component_code="EPS-SP-001"),
    dict(component_name="Li-Ion Battery Pack", subsystem="EPS", example_role="Energy storage",
         scaled_description="Rechargeable lithium-ion battery pack with integrated protection and balancing circuits.",
         length_mm=90.0, width_mm=72.0, height_mm=18.0, scaled_mass_g=120.0, voltage_v=8.2, current_ma=2600.0,
         data_size="N/A", assumed_cost_usd=950.0, temperature_range="-20 to +60C",
         key_specs="Capacity: 20 Wh, Cycle life: >500", component_code="EPS-BAT-001"),
    dict(component_name="EPS Controller", subsystem="EPS", example_role="Power management",
         scaled_description="Smart power management unit with MPPT, battery charging and regulated power rails.",
         length_mm=96.0, width_mm=90.0, height_mm=15.0, scaled_mass_g=75.0, voltage_v=5.0, current_ma=200.0,
         data_size="1 KB/s telemetry", assumed_cost_usd=2200.0, temperature_range="-40 to +85C",
         key_specs="MPPT efficiency: 97%, 3.3V/5V/12V rails", component_code="EPS-CTRL-001"),
    dict(component_name="UHF Transceiver", subsystem="COMMS", example_role="Telemetry & Telecommand",
         scaled_description="Half-duplex UHF transceiver for reliable ground station uplink/downlink in LEO.",
         length_mm=96.0, width_mm=90.0, height_mm=15.0, scaled_mass_g=76.0, voltage_v=5.0, current_ma=450.0,
         data_size="9.6 kbps", assumed_cost_usd=1500.0, temperature_range="-40 to +85C",
         key_specs="Freq: 435-438 MHz, Power: 0.5W, Half-duplex", component_code="COMMS-UHF-001"),
    dict(component_name="S-Band Downlink Module", subsystem="COMMS", example_role="High-speed downlink",
         scaled_description="S-band transmitter for high-throughput payload data downlink from LEO satellites.",
         length_mm=96.0, width_mm=90.0, height_mm=20.0, scaled_mass_g=100.0, voltage_v=5.0, current_ma=1200.0,
         data_size="1 Mbps", assumed_cost_usd=4800.0, temperature_range="-30 to +70C",
         key_specs="Freq: 2.0-2.4 GHz, Power: 1W, OQPSK", component_code="COMMS-SBAND-001"),
    dict(component_name="RGB Earth Imager", subsystem="Payload", example_role="Earth observation",
         scaled_description="3-band visible light imager with 5m ground resolution for Earth observation missions.",
         length_mm=80.0, width_mm=80.0, height_mm=100.0, scaled_mass_g=300.0, voltage_v=5.0, current_ma=600.0,
         data_size="50 MB/image", assumed_cost_usd=12000.0, temperature_range="-10 to +50C",
         key_specs="GSD: 5m, FOV: 6deg, 12-bit, 4096x4096 px", component_code="PL-CAM-001"),
    dict(component_name="AIS Receiver", subsystem="Payload", example_role="Maritime tracking",
         scaled_description="Automatic Identification System receiver for maritime vessel tracking from LEO.",
         length_mm=70.0, width_mm=50.0, height_mm=15.0, scaled_mass_g=80.0, voltage_v=3.3, current_ma=200.0,
         data_size="10 KB/min", assumed_cost_usd=3500.0, temperature_range="-40 to +85C",
         key_specs="Channels: A+B, Detection: >90% per pass", component_code="PL-AIS-001"),
    dict(component_name="3U CubeSat Structure", subsystem="Structure", example_role="Main chassis",
         scaled_description="PC/104-compatible 3U CubeSat aluminum structure with deployable solar panel mounts.",
         length_mm=100.0, width_mm=100.0, height_mm=340.0, scaled_mass_g=250.0, voltage_v=0.0, current_ma=0.0,
         data_size="N/A", assumed_cost_usd=1800.0, temperature_range="-150 to +150C",
         key_specs="Al 6061-T6, Rails per CDS spec, Mass budget margin", component_code="STR-3U-001"),
    dict(component_name="Multi-Layer Insulation (MLI)", subsystem="Thermal", example_role="Passive thermal control",
         scaled_description="Aluminized mylar MLI blanket for passive thermal insulation in orbital thermal cycling.",
         length_mm=300.0, width_mm=300.0, height_mm=5.0, scaled_mass_g=20.0, voltage_v=0.0, current_ma=0.0,
         data_size="N/A", assumed_cost_usd=200.0, temperature_range="-200 to +200C",
         key_specs="Layers: 15, Effective emittance: 0.01", component_code="THM-MLI-001"),
    dict(component_name="Heater Panel", subsystem="Thermal", example_role="Active thermal control",
         scaled_description="Kapton-based resistive heater panel for battery and electronics cold survival heating.",
         length_mm=100.0, width_mm=80.0, height_mm=1.0, scaled_mass_g=10.0, voltage_v=5.0, current_ma=600.0,
         data_size="N/A", assumed_cost_usd=120.0, temperature_range="-200 to +130C",
         key_specs="Power: 3W, Temp sensor integrated, 12V option", component_code="THM-HTR-001"),
]


async def seed(db: AsyncSession, *, dry_run: bool) -> None:
    created = {"mission": 0, "variants": 0, "components": 0}
    skipped = {"mission": 0, "variants": 0, "components": 0}

    author = (await db.execute(select(User).where(User.roles.contains(["operations"])))).scalars().first()
    if author is None:
        print("No 'operations' user found — cannot set missions.authored_by. Create one first.")
        return

    mission = (await db.execute(select(Mission).where(Mission.slug == MISSION_SLUG))).scalars().first()
    if mission is None:
        mission = Mission(
            id=uuid.uuid4(), title="CubeSat Mission Design", slug=MISSION_SLUG,
            summary="Design a satellite from the ground up: pick components, work out your CONOPS, "
                     "and balance data, power, link, mass, and cost budgets until your design is flight-ready.",
            description="A nine-step systems-engineering exercise ported from the SpacePoint Mission Portal. "
                         "Solo or as a team, iterate freely — nothing is graded until you mark your design complete.",
            kind="design", team_policy="either", status="published", access_mode="open",
            authored_by=author.id, track="Spacecraft systems",
        )
        db.add(mission)
        created["mission"] += 1
        await db.flush()
    else:
        skipped["mission"] += 1

    for v in VARIANTS:
        existing = (await db.execute(select(MissionVariant).where(
            MissionVariant.mission_id == mission.id, MissionVariant.position == v["position"],
        ))).scalars().first()
        if existing is not None:
            skipped["variants"] += 1
            continue
        db.add(MissionVariant(id=uuid.uuid4(), mission_id=mission.id, **v))
        created["variants"] += 1
    await db.flush()

    for c in COMPONENTS:
        existing = (await db.execute(
            select(DesignComponentLibrary).where(DesignComponentLibrary.component_name == c["component_name"])
        )).scalars().first()
        if existing is not None:
            skipped["components"] += 1
            continue
        db.add(DesignComponentLibrary(id=uuid.uuid4(), **c))
        created["components"] += 1
    await db.flush()

    for label in created:
        print(f"{label:12} created {created[label]:3}   already present {skipped[label]:3}")

    if dry_run:
        print("\n--dry-run: rolling back, nothing written.")
    else:
        await db.commit()
        print(f"\nCommitted. Mission slug: {MISSION_SLUG}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report what would change, write nothing")
    args = parser.parse_args()

    engine = create_async_engine(settings.DATABASE_URL)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as db:
        await seed(db, dry_run=args.dry_run)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

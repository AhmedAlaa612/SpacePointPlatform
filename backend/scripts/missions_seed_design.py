"""Seed the design mission (CubeSat mission design, ported from Madar) —
the ONE `missions` row, its three difficulty variants, and the shared
component library students pick from.

    python scripts/missions_seed_design.py [--dry-run] [--images-dir PATH]

MISSIONS_REPORT.md Ch.3's naming trap, stated plainly for whoever edits
this next: **all of Madar is one mission.** Not one per student, not one
per subsystem. This script creates exactly one `missions` row
(`kind='design'`), three `mission_variants` rows (Cadet/Engineer/Flight
Director — the pass/fail thresholds a student can never edit, P7-6), and
the `design_component_library` rows students pick from.

**2026-08-14 correction:** the 15 components this script used to seed
("Nano Star Tracker", "MEMS Reaction Wheel", ...) were transcribed from
`missionportal/backend/seed.py` — which turned out to be placeholder/dev
data, never what Madar's students actually used. Confirmed against Madar's
own live production `components` table (pulled over SSH, `SELECT
row_to_json(c) FROM components`): the real catalog is 36 components, none
of which share a name or code with the placeholder set (real kit parts —
DC motors, GPS, MPU6050, ESP32 variants, INA219, etc., not abstract
CubeSat subsystem stand-ins). COMPONENTS below is that real data, dims
parsed once here into three numeric columns (F3) same as before, plus a
`madar_image_url` per entry — either Madar's own `/static/uploads/<uuid>`
path (resolved against `--images-dir`, i.e. missionportal's
`frontend/uploads/` folder) or an external product-photo URL (fetched
directly). Matching moved from `component_name` to `component_code`: two
real components legitimately share a name ("L9110S Motor Driver", codes
`ADCS-L9110S` / `ADCS-L9110S-001`), which name-matching would have
silently collapsed into one.

**2026-08-14, same day:** this script used to also seed a second mission,
"CubeSat Design Report" (`cubesat-design-report`), a written-report
follow-on gated behind the design one. That was invented during a prior
session's "Design v2" work, not part of what Madar actually shipped —
removed from production (zero attempts existed on it, so a clean delete,
not an archive) and from here, so it can't silently reappear on the next
`--update` run.

Idempotent: re-running skips anything already present (mission by slug,
variants by (mission, position), components by code, images only fetched
for a component that doesn't already have one). Deliberately not a
migration, same reasoning as `seed_inventory.py` — this is reference data,
somebody's decision, not schema, and must not silently re-apply on deploy.
"""

import argparse
import asyncio
import re
import sys
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.models.missions.design import DesignComponentLibrary  # noqa: E402
from app.models.missions.mission import Mission, MissionVariant  # noqa: E402
from app.services import storage  # noqa: E402
from app.models.user import User  # noqa: E402

IMAGE_BUCKET = "mission-assets"

_CONTENT_TYPE_SUFFIX = {
    "image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg",
    "image/webp": "webp", "image/gif": "gif", "image/svg+xml": "svg",
}


def _fetch_external_image(url: str) -> tuple[bytes, str] | None:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
            ctype = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
            return data, ctype
    except Exception as exc:  # noqa: BLE001 — a dead source URL shouldn't fail the whole seed
        print(f"    ! image fetch failed ({url}): {exc}")
        return None


async def _attach_image(row: DesignComponentLibrary, madar_image_url: str | None, images_dir: Path | None) -> bool:
    """Best-effort: download/copy `madar_image_url` into this app's own
    storage and point `row` at it. Never raises — a missing/dead source
    image is a gap to report, not a reason to fail the seed."""
    if not madar_image_url:
        return False

    if madar_image_url.startswith("/static/uploads/"):
        fname = madar_image_url.rsplit("/", 1)[-1]
        if images_dir is None:
            print(f"    ! no --images-dir given, skipping local image {fname}")
            return False
        src = images_dir / fname
        if not src.exists():
            print(f"    ! local image missing: {src}")
            return False
        data = src.read_bytes()
        suffix = fname.rsplit(".", 1)[-1].lower()
        ctype = "image/png" if suffix == "png" else "image/jpeg"
    else:
        fetched = _fetch_external_image(madar_image_url)
        if fetched is None:
            return False
        data, ctype = fetched
        fallback_suffix = madar_image_url.rsplit(".", 1)[-1].split("?")[0][:4] or "jpg"
        suffix = _CONTENT_TYPE_SUFFIX.get(ctype, fallback_suffix)

    path = f"design-library/{row.id}.{suffix}"
    await storage.upload_to_path(IMAGE_BUCKET, path, data, ctype)
    row.image_bucket, row.image_path = IMAGE_BUCKET, path
    return True

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
            # Design v2 (7D-2): F8's battery limit and F7's downlink headroom.
            max_depth_of_discharge_pct=40.0, required_downlink_margin_fraction=0.05,
        ),
    ),
    dict(
        label="Engineer", position=2, points=200,
        config=dict(
            max_storage_kb=1_048_576.0, required_storage_margin_kb=104_857.6,
            power_per_solar_cell_w=1.1, maximum_budget_aed=2000.0,
            assumed_distance_km=500.0, transmit_power_dbm=30.0,
            good_link_margin_threshold_db=3.0, weak_link_margin_threshold_db=0.0,
            max_depth_of_discharge_pct=30.0, required_downlink_margin_fraction=0.10,
        ),
    ),
    dict(
        label="Flight Director", position=3, points=350,
        config=dict(
            max_storage_kb=524_288.0, required_storage_margin_kb=157_286.4,
            power_per_solar_cell_w=1.1, maximum_budget_aed=1500.0,
            assumed_distance_km=700.0, transmit_power_dbm=30.0,
            good_link_margin_threshold_db=6.0, weak_link_margin_threshold_db=2.0,
            max_depth_of_discharge_pct=20.0, required_downlink_margin_fraction=0.20,
        ),
    ),
]

# Real Madar production catalog (36 components), pulled 2026-08-14 via SSH from the
# live components table, not the placeholder seed.py this used to be transcribed from.
# dims parsed once here (L, W, H in mm); madar_image_url is resolved/fetched by _attach_image.
COMPONENTS = [
    dict(component_name='DC Motor (small)', subsystem='ADCS', example_role='Continuous stabilization actuator', scaled_description='Continuous spin actuator', length_mm=60.0, width_mm=50.0, height_mm=40.0, scaled_mass_g=150, voltage_v=5, current_ma=180, data_size='0.001', assumed_cost_usd=22, temperature_range='-40 to +85°C', key_specs='Continuous rotation', component_code='ADCS-SAT-002', datasheet_url='https://drive.google.com/file/d/1y_64UOB44f3Iw0JcN8kOqjbPdb1HAu6b/view?usp=drive_link', tag='TinkerCAD', madar_image_url='https://i.ytimg.com/vi/G9hMN6pthiA/maxresdefault.jpg'),
    dict(component_name='DC Motor with Encoder', subsystem='ADCS', example_role='Precise rotational control', scaled_description='High-precision motion subsystem', length_mm=70.0, width_mm=60.0, height_mm=45.0, scaled_mass_g=220, voltage_v=5, current_ma=250, data_size='0.002', assumed_cost_usd=28, temperature_range='-40 to +85°C', key_specs='Step-based precise motion', component_code='ADCS-SAT-004', datasheet_url='https://drive.google.com/file/d/16rQoDaheN54_KxhrdJDH8b4s3Gjo9YXd/view?usp=drive_link', tag='TinkerCAD', madar_image_url='https://media.cheggcdn.com/study/37f/37f88b5f-b944-44e1-b9ee-3b1b17df55f2/Screenshot405.png'),
    dict(component_name='GPS Module', subsystem='ADCS', example_role='Get satellite position', scaled_description='NEO-6MV2 GPS module used to provide latitude and longitude data', length_mm=35.0, width_mm=25.0, height_mm=8.0, scaled_mass_g=12, voltage_v=3.3, current_ma=10, data_size='64 bytes', assumed_cost_usd=6, temperature_range='-40 to +85 °C', key_specs='UART; 9600 bps default baud rate; 5 Hz max update rate', component_code='ADCS-GPS-001', datasheet_url='https://drive.google.com/file/d/1NRr1ad3hPr95HBXTgUKVEOJTKCxTusDj/view?usp=drive_link', tag='SatKit', madar_image_url='/static/uploads/c3d823be-f82b-4bdf-b113-522302d7a504.jpg'),
    dict(component_name='L9110S Motor Driver', subsystem='ADCS', example_role='Motor control', scaled_description='Controls the speed and direction of reaction wheel motors using PWM signals.', length_mm=29.0, width_mm=24.0, height_mm=12.0, scaled_mass_g=6, voltage_v=5, current_ma=800, data_size='0 KB/s', assumed_cost_usd=2, temperature_range='-20 to +80°C', key_specs='Dual H-bridge motor driver for small DC motors.', component_code='ADCS-L9110S', datasheet_url='https://www.elecrow.com/download/datasheet-l9110.pdf?srsltid=AfmBOoqTB5YWVIcEAK0k11HFBIkRefd-ihW4zIVW53yl5m5Xh4tlASPw', tag='Physical', madar_image_url='https://m.media-amazon.com/images/I/61tejpBrXLL.jpg'),
    dict(component_name='L9110S Motor Driver', subsystem='ADCS', example_role='Drive reaction wheel motor', scaled_description='Dual-channel motor driver used to control motor direction and speed', length_mm=29.0, width_mm=23.0, height_mm=10.0, scaled_mass_g=5, voltage_v=5, current_ma=17, data_size='1 byte command', assumed_cost_usd=2, temperature_range='-55 to +85 °C', key_specs='Forward/reverse motor control; TTL/CMOS input; up to 1.5-2.0 A peak per channel', component_code='ADCS-L9110S-001', datasheet_url='https://drive.google.com/file/d/1TSaqXSAUOmG7cZfm0uHZ16vU1_X-fB4w/view?usp=drive_link', tag='SatKit', madar_image_url='/static/uploads/d99429a1-e262-4f7a-937f-a918fbf3655d.png'),
    dict(component_name='LDR Sensor', subsystem='ADCS', example_role='Sun/light sensing', scaled_description='Detects light intensity to simulate sun sensing and basic attitude awareness.', length_mm=10.0, width_mm=10.0, height_mm=5.0, scaled_mass_g=1, voltage_v=3.3, current_ma=1, data_size='0.02 KB/s', assumed_cost_usd=1, temperature_range='-20 to +70°C', key_specs='Light-dependent resistor used for analog light measurement.', component_code='ADCS-LDR', datasheet_url='https://components101.com/sites/default/files/component_datasheet/LDR%20Datasheet.pdf', tag='MPKit', madar_image_url='https://probots.co.in/pub/media/catalog/product/cache/d8ddd0f9b0cd008b57085cd218b48832/l/d/ldr_sensor_module_1_.jpg'),
    dict(component_name='MPU6050 Module', subsystem='ADCS', example_role='Measure attitude and motion', scaled_description='6-axis IMU used to measure acceleration and angular velocity', length_mm=20.0, width_mm=15.0, height_mm=3.0, scaled_mass_g=2, voltage_v=3.3, current_ma=3.8, data_size='24 bytes', assumed_cost_usd=2, temperature_range='-40 to +85 °C', key_specs='3-axis gyroscope; 3-axis accelerometer; I2C; default address 0x68', component_code='ADCS-MPU6050-001', datasheet_url='https://drive.google.com/file/d/1mAn1oXZyhAR6_QaBmBZlFbMY_PEa1spH/view?usp=drive_link', tag='SatKit', madar_image_url='/static/uploads/80256d88-4e0b-4ee8-bce1-a812d1d8bc01.png'),
    dict(component_name='Magnetorquer', subsystem='ADCS', example_role='Attitude control actuator', scaled_description='Generates a magnetic field to simulate satellite detumbling and magnetic attitude control.', length_mm=60.0, width_mm=10.0, height_mm=10.0, scaled_mass_g=25, voltage_v=5, current_ma=300, data_size='0 KB/s', assumed_cost_usd=20, temperature_range='-20 to +80°C', key_specs='Electromagnetic coil used for detumbling and magnetic attitude control simulation.', component_code='ADCS-MAGTORQ', datasheet_url=None, tag='SatKit', madar_image_url='/static/uploads/ed35de50-425b-4f9c-bd60-491310841e22.png'),
    dict(component_name='Servo Motor SG90 / Micro Servo', subsystem='ADCS', example_role='Pointing/orientation actuator', scaled_description='Controlled motion unit for orientation simulation', length_mm=50.0, width_mm=40.0, height_mm=40.0, scaled_mass_g=120, voltage_v=5, current_ma=200, data_size='0.001', assumed_cost_usd=20, temperature_range='-40 to +85°C', key_specs='Controlled angular movement', component_code='ADCS-SAT-003', datasheet_url='https://drive.google.com/file/d/1ryu8xT1I77YYrFesHKqR8sSZj4mVUHX_/view?usp=drive_link', tag='TinkerCAD', madar_image_url='https://www.computersciencecafe.com/uploads/4/3/9/3/43932527/published/sevrowitharudino.png?1748694004'),
    dict(component_name='Arduino Uno', subsystem='CDHS', example_role='Main onboard computer', scaled_description='Main command and data-handling unit in enclosed subsystem form', length_mm=90.0, width_mm=90.0, height_mm=20.0, scaled_mass_g=120, voltage_v=5, current_ma=80, data_size=None, assumed_cost_usd=40, temperature_range='-40 to +80 °C', key_specs='Processor, I/O control, telemetry handling', component_code='CDHS-ST-001', datasheet_url='https://drive.google.com/file/d/1S9Tg5JtmyOneWS0BCf-R2ydlh63hmprp/view?usp=drive_link', tag='TinkerCAD', madar_image_url='https://be189.github.io/_images/labeled_arduino.svg'),
    dict(component_name='ESP32 Module', subsystem='CDHS', example_role='Main onboard computer', scaled_description='Main microcontroller used for command handling, data processing, and subsystem control', length_mm=52.0, width_mm=28.0, height_mm=5.0, scaled_mass_g=10, voltage_v=3.3, current_ma=2000, data_size='1 KB telemetry', assumed_cost_usd=5, temperature_range='-40 to +85 °C', key_specs='WiFi; Bluetooth; BLE; dual-core CPU; SPI; UART; I2C; up to 240 MHz', component_code='CDHS-ESP32-001', datasheet_url='https://drive.google.com/file/d/1j-N7EGnAD3col5GJbGYuK8xZYS8MKan1/view?usp=drive_link', tag='SatKit', madar_image_url='/static/uploads/65ae81a1-94e9-4059-b0f7-2d690a6d0016.png'),
    dict(component_name='ESP32-S3 Seeed', subsystem='CDHS', example_role='Advanced onboard computer', scaled_description='More powerful microcontroller used for advanced processing, sensor control, and communication tasks.', length_mm=21.0, width_mm=17.5, height_mm=3.5, scaled_mass_g=3, voltage_v=3.3, current_ma=240, data_size='100 KB/s', assumed_cost_usd=8, temperature_range='-40 to +85°C', key_specs='ESP32-S3 MCU, Wi-Fi, BLE, GPIO, I2C, SPI, UART, AI acceleration support.', component_code='CDH-ESP32S3SEEED', datasheet_url='https://www.electrokit.com/upload/quick/63/ad/b308_41024001-tds.pdf', tag='MPKit', madar_image_url='https://m.media-amazon.com/images/I/51hgdPB7atL._AC_UF1000,1000_QL80_.jpg'),
    dict(component_name='ESP32-WROOM-32', subsystem='CDHS', example_role='Onboard computer', scaled_description='Main controller used to process sensor data, control subsystems, and manage mission logic.', length_mm=55.0, width_mm=28.0, height_mm=13.0, scaled_mass_g=25, voltage_v=3.3, current_ma=250, data_size='50 KB/s', assumed_cost_usd=8, temperature_range='-40 to +85°C', key_specs='Wi-Fi, Bluetooth, GPIO, UART, I2C, SPI, ADC, PWM.', component_code='CDH-ESP32WROOM32', datasheet_url='http://academy.cba.mit.edu/classes/networking_communications/ESP32/esp32-wroom-32_datasheet_en.pdf', tag='MPKit', madar_image_url='https://m.media-amazon.com/images/I/71sGKxbFhbL._AC_UF1000,1000_QL80_.jpg'),
    dict(component_name='I2C FRAM Module', subsystem='CDHS', example_role='Store critical mission data', scaled_description='Non-volatile FRAM memory used for fast and reliable data storage', length_mm=20.0, width_mm=17.0, height_mm=3.0, scaled_mass_g=2, voltage_v=3.3, current_ma=0.2, data_size='32 KB storage', assumed_cost_usd=8, temperature_range='-40 to +85 °C', key_specs='256 Kbit / 32 KB; I2C up to 1 MHz; 95-year retention; address 0x50-0x57', component_code='CDHS-FRAM-001', datasheet_url='https://drive.google.com/file/d/1SF5M3b74rKCqflJrM_wsKqXldD2yTCN9/view?usp=drive_link', tag='SatKit', madar_image_url='/static/uploads/134f5bb2-60ec-4c66-b8c1-86733bf27090.png'),
    dict(component_name='INA219 Current Sensor', subsystem='CDHS', example_role='Monitor power consumption', scaled_description='Digital current and power sensor used to measure bus voltage and current', length_mm=25.0, width_mm=22.0, height_mm=3.0, scaled_mass_g=3, voltage_v=3.3, current_ma=1, data_size='8 bytes', assumed_cost_usd=3, temperature_range='-40 to +125 °C', key_specs='I2C/SMBus; measures shunt voltage and bus voltage; up to 26 V bus sensing', component_code='CDHS-INA219-001', datasheet_url='https://drive.google.com/file/d/1iwKyJaMbjR1KXH2O3vhY4kIaJ7bk28M9/view?usp=drive_link', tag='SatKit', madar_image_url='/static/uploads/df4364de-24af-4259-a119-cf7b42a2b471.png'),
    dict(component_name='MicroSD Card Module', subsystem='CDHS', example_role='Store logs and payload data', scaled_description='Removable storage module used for logging sensor readings and image data', length_mm=42.0, width_mm=24.0, height_mm=5.0, scaled_mass_g=5, voltage_v=3.3, current_ma=200, data_size='32 GB assumed', assumed_cost_usd=2, temperature_range='-40 to +125 °C', key_specs='SPI interface; FAT16/FAT32 support; removable storage', component_code='CDHS-MICROSD-001', datasheet_url='https://drive.google.com/file/d/1KzjzQVLI8geQ01IMMTv8Ach1nAqdICag/view?usp=drive_link', tag='SatKit', madar_image_url='/static/uploads/47013ea7-cf5a-4478-b0b4-2c6e26e5ac7d.png'),
    dict(component_name='TMP102 Temperature Sensor', subsystem='CDHS', example_role='Measure internal temperature', scaled_description='Digital temperature sensor used to monitor satellite internal temperature', length_mm=18.0, width_mm=17.0, height_mm=3.0, scaled_mass_g=2, voltage_v=3.3, current_ma=0.001, data_size='4 bytes', assumed_cost_usd=4, temperature_range='-40 to +125 °C', key_specs='I2C; 0.0625°C resolution; ±0.5°C accuracy; address options via ADD0', component_code='CDHS-TMP102-001', datasheet_url='https://drive.google.com/file/d/1j-N7EGnAD3col5GJbGYuK8xZYS8MKan1/view?usp=drive_link', tag='SatKit', madar_image_url='/static/uploads/bdd40a9b-7676-4c8c-9625-d2c74f5af7ef.png'),
    dict(component_name='HC-12 Module', subsystem='COMMS', example_role='Send telemetry to ground station', scaled_description='Wireless RF UART module used for satellite-to-ground communication', length_mm=27.4, width_mm=13.2, height_mm=4.0, scaled_mass_g=4, voltage_v=3.3, current_ma=100, data_size='32 bytes/packet', assumed_cost_usd=4, temperature_range='-40 to +85 °C', key_specs='433.4-473 MHz; 100 channels; 20 dBm max power; about 500 m range', component_code='COMMS-HC12-001', datasheet_url='https://drive.google.com/file/d/1s6A9SfbsWjgyM-2E-YriFalzgjBl7Gm-/view?usp=drive_link', tag='SatKit', madar_image_url='/static/uploads/667df105-507f-4386-a7b1-acc380c4d4b4.png'),
    dict(component_name='IR Remote', subsystem='COMMS', example_role='Receive command/data', scaled_description='Short-range optical reception module', length_mm=30.0, width_mm=30.0, height_mm=15.0, scaled_mass_g=15, voltage_v=5, current_ma=2, data_size='0.001', assumed_cost_usd=5, temperature_range='-40 to +85°C', key_specs='Optical signal reception', component_code='COMM-SAT-002', datasheet_url='https://drive.google.com/file/d/1x3mjsUJFqb3rH3TgLiTF1Mkqdv-qqoHC/view?usp=drive_link', tag='TinkerCAD', madar_image_url='https://robu.in/wp-content/uploads/2017/07/219.jpg'),
    dict(component_name='IR Sensor', subsystem='COMMS', example_role='Send command/data', scaled_description='Short-range optical transmission module', length_mm=30.0, width_mm=30.0, height_mm=15.0, scaled_mass_g=15, voltage_v=5, current_ma=20, data_size='0.001', assumed_cost_usd=5, temperature_range='-40 to +85°C', key_specs='Optical signal reception', component_code='COMM-SAT-001', datasheet_url='https://drive.google.com/file/d/1lh15f2sUxT8gvXslct8SEZ7KVJ2BZ9Us/view?usp=drive_link', tag='TinkerCAD', madar_image_url='https://static.wixstatic.com/media/f3eafe_552e1d4517a5419fbd458c389de0279e~mv2.jpg/v1/fill/w_790,h_561,al_c,q_85,enc_avif,quality_auto/f3eafe_552e1d4517a5419fbd458c389de0279e~mv2.jpg'),
    dict(component_name='3.3V Regulator [LD1117V33]', subsystem='EPS', example_role='Voltage conversion', scaled_description='Regulates incoming power to stable spacecraft voltage', length_mm=50.0, width_mm=40.0, height_mm=20.0, scaled_mass_g=40, voltage_v=3.3, current_ma=10, data_size='N/A', assumed_cost_usd=10, temperature_range='-40 to +120°C', key_specs='Stable regulated output', component_code='EPS-SAT-0012', datasheet_url='https://drive.google.com/file/d/1QhU94I_yiZP7APC7whJ8DRkvHJCjWE3o/view?usp=drive_link', tag='TinkerCAD', madar_image_url='https://estore.st.com/media/catalog/product/l/d/ld1117v33.jpeg?quality=80&bg-color=255,255,255&fit=bounds&height=265&width=265&canvas=265:265'),
    dict(component_name='9V Battery', subsystem='EPS', example_role='Energy storage', scaled_description='Small battery pack packaged for spacecraft use', length_mm=80.0, width_mm=50.0, height_mm=30.0, scaled_mass_g=180, voltage_v=9, current_ma=None, data_size=None, assumed_cost_usd=25, temperature_range='0 to +50°C', key_specs='Basic stored power unit', component_code='EPS-SAT-003', datasheet_url='https://drive.google.com/file/d/1eDDciqhOJghL4fHLmTPfI2nELZbGfnEe/view?usp=drive_link', tag='TinkerCAD', madar_image_url='https://thevalleyofcode.com/images/electronics-first-circuit/Screen_Shot_2020-12-05_at_12.16.57.png'),
    dict(component_name='AA Battery Pack (4xAA)', subsystem='EPS', example_role='Primary battery unit', scaled_description='Larger battery pack for longer missions', length_mm=100.0, width_mm=80.0, height_mm=35.0, scaled_mass_g=350, voltage_v=9, current_ma=None, data_size=None, assumed_cost_usd=35, temperature_range='0 to +80°C', key_specs='Higher energy storage', component_code='EPS-SAT-005', datasheet_url='https://drive.google.com/file/d/1I6exKvBqydipYpEc9kgTA_8jtKFjj9_j/view?usp=drive_link', tag='TinkerCAD', madar_image_url='https://www.newtoncbraga.com.br/images/stories/artigo2023/kit001_04_0002.png'),
    dict(component_name='Coin Cell (3V battery)', subsystem='EPS', example_role='Energy storage', scaled_description='Small battery pack packaged for simple spacecraft uses (mainly for peripherals)', length_mm=40.0, width_mm=30.0, height_mm=20.0, scaled_mass_g=100, voltage_v=3, current_ma=None, data_size=None, assumed_cost_usd=15, temperature_range='0 to +40°C', key_specs='Simple Uses', component_code='EPS-SAT-004', datasheet_url='https://drive.google.com/file/d/1wh3zqFlVw4O4JIg3WLQw45Egt6xnojIJ/view?usp=drive_link', tag='TinkerCAD', madar_image_url='https://media.springernature.com/lw685/springer-static/image/chp%3A10.1007%2F978-1-4842-9582-3_2/MediaObjects/531157_1_En_2_Fig3_HTML.jpg'),
    dict(component_name='LM2596', subsystem='EPS', example_role='Step-down voltage regulation', scaled_description='Converts higher input voltage into a stable lower voltage for satellite subsystems.', length_mm=43.0, width_mm=21.0, height_mm=14.0, scaled_mass_g=12, voltage_v=5, current_ma=3000, data_size='0 KB/s', assumed_cost_usd=2, temperature_range='-40 to +85°C', key_specs='Adjustable DC-DC buck converter.', component_code='EPS-LM2596', datasheet_url='https://www.onsemi.com/download/data-sheet/pdf/lm2596-d.pdf', tag='MPKit', madar_image_url='https://m.media-amazon.com/images/I/71HfxNInzjL._AC_UF1000,1000_QL80_.jpg'),
    dict(component_name='LM2596 Buck Converter', subsystem='EPS', example_role='Regulate bus voltage', scaled_description='Step-down voltage regulator used to convert higher input voltage to stable lower voltage', length_mm=43.0, width_mm=21.0, height_mm=14.0, scaled_mass_g=15, voltage_v=3.3, current_ma=3000, data_size='0 bytes', assumed_cost_usd=2, temperature_range='-40 to +125 °C', key_specs='Input up to 40 V; adjustable output 1.23-30 V; up to 3 A output; 150 kHz switching', component_code='EPS-LM2596-001', datasheet_url='https://drive.google.com/file/d/1U977LbpZfSwEjKdMi0qUn3OiNOgna_C4/view?usp=drive_link', tag='SatKit', madar_image_url='/static/uploads/574503ba-f3e3-4d3d-bcc6-a4cd80a1c21f.png'),
    dict(component_name='LM7805 Voltage Regulator', subsystem='EPS', example_role='Voltage conversion', scaled_description='Regulates incoming power to stable spacecraft voltage', length_mm=50.0, width_mm=40.0, height_mm=20.0, scaled_mass_g=40, voltage_v=5, current_ma=40, data_size=None, assumed_cost_usd=12, temperature_range='-40 to +120°C', key_specs='Stable regulated output', component_code='EPS-SAT-001', datasheet_url='https://drive.google.com/file/d/103UlLm6SDx6jjFWK1RYC63O8JzsZ8_zv/view?usp=drive_link', tag='TinkerCAD', madar_image_url='https://www.electronicsforu.com/wp-contents/uploads/2016/10/Lm7805-pinout-diagram-300x238.png'),
    dict(component_name='Li-ion 18650 Battery', subsystem='EPS', example_role='Energy storage', scaled_description='Stores electrical energy to power the satellite kit when external power is unavailable.', length_mm=65.0, width_mm=18.0, height_mm=18.0, scaled_mass_g=45, voltage_v=3.7, current_ma=2600, data_size='0 KB/s', assumed_cost_usd=5, temperature_range='-20 to +60°C', key_specs='Rechargeable 3.7 V lithium-ion cell, typical 2200–3000 mAh capacity.', component_code='EPS-18650', datasheet_url=None, tag='MPKit', madar_image_url='https://images-na.ssl-images-amazon.com/images/I/31l6ruXIquS.jpg'),
    dict(component_name='MT3608', subsystem='EPS', example_role='Step-up voltage regulation', scaled_description='Boosts battery voltage to a higher voltage required by some subsystems.', length_mm=37.0, width_mm=17.0, height_mm=7.0, scaled_mass_g=4, voltage_v=5, current_ma=1200, data_size='0 KB/s', assumed_cost_usd=2, temperature_range='-40 to +85°C', key_specs='DC-DC step-up boost converter.', component_code='EPS-MT3608', datasheet_url='https://www.olimex.com/Products/Breadboarding/BB-PWR-3608/resources/MT3608.pdf', tag='MPKit', madar_image_url='https://www.az-delivery.de/cdn/shop/products/mt3608-dc-dc-netzteil-adapter-step-up-modul-932676.jpg?v=1679399025'),
    dict(component_name='Solar Cell', subsystem='EPS', example_role='Power Generation', scaled_description='Converts solar power to electricity that would power the satellite and be used to charge the batteries', length_mm=90.0, width_mm=45.0, height_mm=10.0, scaled_mass_g=50, voltage_v=0, current_ma=0, data_size='N/A', assumed_cost_usd=15, temperature_range='-40 to +85°C', key_specs='Power Generation', component_code='EPS-SAT-006', datasheet_url='https://drive.google.com/file/d/1ys2zuNGkHz1FxuBnrfR2_QRVk-KT10G0/view?usp=drive_link', tag='TinkerCAD', madar_image_url='https://custom-images.strikinglycdn.com/res/hrscywv4p/image/upload/c_limit,fl_lossy,h_1440,w_720,f_auto,q_60/1134255/733934_378196.gif'),
    dict(component_name='TP4056', subsystem='EPS', example_role='Battery charging', scaled_description='Charges the Li-ion battery safely from a USB or external power source.', length_mm=25.0, width_mm=19.0, height_mm=4.0, scaled_mass_g=3, voltage_v=5, current_ma=1000, data_size='0 KB/s', assumed_cost_usd=1, temperature_range='-20 to +85°C', key_specs='Single-cell Li-ion charging module with charge protection depending on version.', component_code='EPS-TP4056', datasheet_url='https://img.eecart.com/dev/file/part/spec/TP4056-XUNDE.pdf', tag='MPKit', madar_image_url='https://cdn3.botland.store/80089/li-ion-charger-tp4056-1s-37v-microusb-with-protection.jpg'),
    dict(component_name='ESP32-CAM Module', subsystem='Payload', example_role='Capture mission images', scaled_description='ESP32-based camera module used to capture images and send them to the main controller', length_mm=27.0, width_mm=40.5, height_mm=5.0, scaled_mass_g=10, voltage_v=5, current_ma=2000, data_size='100 KB/image', assumed_cost_usd=8, temperature_range='-40 to +85 °C', key_specs='WiFi; Bluetooth 4.2; BLE; onboard camera; 80-240 MHz CPU', component_code='PAY-ESP32CAM-001', datasheet_url='https://drive.google.com/file/d/1IMyO_eqDMBRy8yduiiTmUo8pkoTsg2y0/view?usp=drive_link', tag='SatKit', madar_image_url='/static/uploads/ffc12e8b-b4b9-488e-826d-e74c4d2ae872.png'),
    dict(component_name='Gas Sensor', subsystem='Payload', example_role='Air Quality Sensing', scaled_description='The Gas Sensor Module detects the presence of gases such as smoke, air pollutants, or harmful gases. It provides an analog signal that changes depending on gas concentration.', length_mm=50.0, width_mm=40.0, height_mm=25.0, scaled_mass_g=60, voltage_v=5, current_ma=150, data_size='0.002', assumed_cost_usd=18, temperature_range='-40 to +85°C', key_specs='Air Quality Sensing', component_code='PY-SAT-002', datasheet_url='https://drive.google.com/file/d/1hFo_F6l6wltHWvtVwRBhYdU7se_qSmxh/view?usp=drive_link', tag='TinkerCAD', madar_image_url='https://user-images.githubusercontent.com/63101268/99223875-558d3180-280b-11eb-9bc2-973f1b9ec867.png'),
    dict(component_name='HC-SR04 Ultrasonic Sensor', subsystem='Payload', example_role='Distance / ranging', scaled_description='Packaged ranging subsystem', length_mm=60.0, width_mm=50.0, height_mm=25.0, scaled_mass_g=80, voltage_v=5, current_ma=20, data_size='0.002', assumed_cost_usd=18, temperature_range='-40 to +85°C', key_specs='Range measurement capability', component_code='PY-SAT-004', datasheet_url='https://drive.google.com/file/d/1700Zc1D2n0m4kRmH7UQAYosBy0WQejDM/view?usp=drive_link', tag='TinkerCAD', madar_image_url='https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTatiF0KBfuGuDYKCrYTDo_GH85CmzoPcFkhg&s'),
    dict(component_name='PIR Motion Sensor', subsystem='Payload', example_role='Object/activity sensing', scaled_description='Packaged motion detection payload', length_mm=50.0, width_mm=50.0, height_mm=25.0, scaled_mass_g=60, voltage_v=5, current_ma=3, data_size='0.001', assumed_cost_usd=16, temperature_range='-40 to +85°C', key_specs='Event-based motion detection', component_code='PY-SAT-003', datasheet_url='https://drive.google.com/file/d/1QYdmuHpT2N9qu5wPdxbz0ddsJ4Dkg-vm/view?usp=drive_link', tag='TinkerCAD', madar_image_url='https://indomaker.com/wp-content/uploads/2021/11/sensor-PIR.jpg'),
    dict(component_name='TMP36 Temperature Sensor', subsystem='Payload', example_role='Temperature monitoring', scaled_description='Packaged thermal sensing module', length_mm=35.0, width_mm=35.0, height_mm=15.0, scaled_mass_g=25, voltage_v=5, current_ma=1, data_size='0.002', assumed_cost_usd=10, temperature_range='-40 to +85°C', key_specs='Temperature sensing, low power', component_code='PAY-S1-01', datasheet_url='https://drive.google.com/file/d/1PjSPNE86KZxrTMst7L3t6o3woBBOMXCW/view?usp=drive_link', tag='TinkerCAD', madar_image_url='https://www.elecfreaks.com/learn-en/_images/case0703.png'),
]



async def seed(
    db: AsyncSession, *, dry_run: bool, update: bool = False, images_dir: Path | None = None,
) -> None:
    created = {"mission": 0, "variants": 0, "components": 0}
    skipped = {"mission": 0, "variants": 0, "components": 0}
    updated = {"mission": 0, "variants": 0, "components": 0}
    images_attached = 0

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
            # Design v2 (7D-2) added `max_depth_of_discharge_pct` and
            # `required_downlink_margin_fraction` to every variant. Without
            # --update an existing database keeps the code defaults for
            # both, which works but isn't the per-difficulty tuning.
            if update:
                existing.label = v["label"]
                existing.points = v["points"]
                existing.config = v["config"]
                updated["variants"] += 1
            else:
                skipped["variants"] += 1
            continue
        db.add(MissionVariant(id=uuid.uuid4(), mission_id=mission.id, **v))
        created["variants"] += 1
    await db.flush()

    for c in COMPONENTS:
        c = dict(c)
        madar_image_url = c.pop("madar_image_url", None)
        existing = (await db.execute(
            select(DesignComponentLibrary).where(DesignComponentLibrary.component_code == c["component_code"])
        )).scalars().first()
        if existing is not None:
            skipped["components"] += 1
            row = existing
        else:
            row = DesignComponentLibrary(id=uuid.uuid4(), **c)
            db.add(row)
            created["components"] += 1
            await db.flush()  # need row.id before uploading its image

        # Storage writes aren't part of the DB transaction below and won't
        # roll back with it, so --dry-run must not perform them either.
        if not dry_run and not row.image_bucket and await _attach_image(row, madar_image_url, images_dir):
            images_attached += 1
    await db.flush()

    for label in sorted(set(created) | set(updated) | set(skipped)):
        print(f"{label:14} created {created.get(label, 0):3}   "
              f"updated {updated.get(label, 0):3}   unchanged {skipped.get(label, 0):3}")
    print(f"{'images':14} attached {images_attached:3} / {len(COMPONENTS)} components")

    if dry_run:
        print("\n--dry-run: rolling back, nothing written.")
    else:
        await db.commit()
        print(f"\nCommitted. Mission: {MISSION_SLUG}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true", help="Rewrite existing variant configs too")
    parser.add_argument("--dry-run", action="store_true", help="Report what would change, write nothing")
    parser.add_argument(
        "--images-dir", type=Path, default=None,
        help="Madar's frontend/uploads/ folder, for components whose madar_image_url is a "
             "/static/uploads/<uuid> path. External (http) image URLs are fetched regardless. "
             "On the VPS this is /var/www/missionportal/frontend/uploads.",
    )
    args = parser.parse_args()

    engine = create_async_engine(settings.DATABASE_URL)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as db:
        await seed(db, dry_run=args.dry_run, update=args.update, images_dir=args.images_dir)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

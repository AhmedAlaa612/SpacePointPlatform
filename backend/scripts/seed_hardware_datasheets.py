"""Generate and seed realistic satellite module hardware datasheets (PDFs)
into storage_local and database for the SpacePoint Instructor Readiness Pipeline.

Run this script ONCE on your environment (local or VPS):
    python scripts/seed_hardware_datasheets.py
"""

import asyncio
import io
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Add backend directory to sys.path so 'app' can be resolved
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select, text

from app.db.session import AsyncSessionLocal, engine
from app.models.sessions.pre_session_quiz import PreSessionQuizDatasheet
from app.services import storage_local


def build_datasheet_pdf(
    title: str,
    doc_type: str,
    subsystem: str,
    doc_code: str,
    summary: str,
    specs: list[list[str]],
    pinout: list[list[str]],
    register_notes: list[str],
    guidelines: list[str],
) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=40,
        rightMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    styles = getSampleStyleSheet()

    header_style = ParagraphStyle(
        "DocHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        textColor=colors.HexColor("#6366f1"),
        spaceAfter=4,
    )
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=6,
    )
    badge_style = ParagraphStyle(
        "DocBadge",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=colors.HexColor("#475569"),
        spaceAfter=12,
    )
    section_title = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#1e293b"),
        spaceBefore=10,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "BodyDark",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#334155"),
        spaceAfter=6,
    )
    table_text = ParagraphStyle(
        "TableText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#1e293b"),
    )
    table_header = ParagraphStyle(
        "TableHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.white,
    )

    elements = []

    # Page 1: Header & Specifications
    elements.append(Paragraph("SPACEPOINT AEROSPACE FLIGHT HARDWARE SPECIFICATION", header_style))
    elements.append(Paragraph(title, title_style))
    elements.append(
        Paragraph(
            f"<b>DOCUMENT:</b> {doc_code} &nbsp;&bull;&nbsp; <b>SUBSYSTEM:</b> {subsystem} &nbsp;&bull;&nbsp; <b>TYPE:</b> {doc_type.upper().replace('_', ' ')}",
            badge_style,
        )
    )
    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#6366f1"), spaceAfter=10))

    elements.append(Paragraph("1. General Overview & Architecture", section_title))
    elements.append(Paragraph(summary, body_style))
    elements.append(Spacer(1, 8))

    elements.append(Paragraph("2. Absolute Electrical & Operating Characteristics", section_title))
    spec_data = [[Paragraph(f"<b>{col}</b>", table_header) for col in specs[0]]]
    for row in specs[1:]:
        spec_data.append([Paragraph(cell, table_text) for cell in row])

    spec_table = Table(spec_data, colWidths=[120, 100, 100, 210])
    spec_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#334155")),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#94a3b8")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    elements.append(spec_table)
    elements.append(Spacer(1, 12))

    elements.append(Paragraph("3. Connector Pinout & Interface Mapping", section_title))
    pin_data = [[Paragraph(f"<b>{col}</b>", table_header) for col in pinout[0]]]
    for row in pinout[1:]:
        pin_data.append([Paragraph(cell, table_text) for cell in row])

    pin_table = Table(pin_data, colWidths=[50, 80, 70, 330])
    pin_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#475569")),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#94a3b8")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    elements.append(pin_table)

    # Page 2: Addressing & Protocol Details
    elements.append(PageBreak())
    elements.append(Paragraph("4. Bus Protocol, Addressing & Register Logic", section_title))
    elements.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#94a3b8"), spaceAfter=8))
    for note in register_notes:
        elements.append(Paragraph(f"&bull;&nbsp;&nbsp;{note}", body_style))
    elements.append(Spacer(1, 10))

    elements.append(Paragraph("5. Flight Integration & Safety Instructions", section_title))
    elements.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#94a3b8"), spaceAfter=8))
    for g in guidelines:
        elements.append(Paragraph(f"&bull;&nbsp;&nbsp;{g}", body_style))

    doc.build(elements)
    return buffer.getvalue()


DATASHEET_DEFINITIONS = [
    {
        "filename": "esp32_datasheet.pdf",
        "doc_id": "ds-esp32",
        "title": "ESP32 Microcontroller Module Data Sheet",
        "doc_type": "datasheet",
        "subsystem_tag": "CDHS",
        "doc_code": "SP-CDHS-DOC-01",
        "summary": "Dual-core 32-bit Xtensa LX6 microprocessor module operating up to 240 MHz. Acts as the primary On-Board Computer (OBC) and telemetry routing engine for the SpacePoint CubeSat architecture. Manages inter-subsystem I2C bus arbitration, SPI flash storage, and packetized ground-station telemetry downlink.",
        "specs": [
            ["Parameter", "Min", "Max", "Conditions / Notes"],
            ["Operating Voltage (VDD)", "3.0 V", "3.6 V", "Nominal 3.3V flight bus supply"],
            ["Operating Current (Active)", "80 mA", "240 mA", "Dual core active with radio transceiver"],
            ["Deep Sleep Current", "5 µA", "10 µA", "RTC timer and ULP coprocessor running"],
            ["Operating Temp Range", "-40 °C", "+105 °C", "Space environmental test qualified"],
            ["Clock Frequency", "80 MHz", "240 MHz", "Integrated 40 MHz crystal oscillator"],
        ],
        "pinout": [
            ["Pin #", "Name", "Type", "Function / Subsystem Interconnect"],
            ["1", "3V3", "Power", "Regulated 3.3V DC rail input from EPS subsystem"],
            ["2", "GND", "Power", "Common satellite chassis ground reference"],
            ["21", "GPIO21", "I/O", "Primary I2C Bus Serial Data line (SDA) - 3.3V logic"],
            ["22", "GPIO22", "I/O", "Primary I2C Bus Serial Clock line (SCL) - 400 kHz max"],
            ["1", "TX0", "Output", "Telemetry debug UART transmit to umbilical diagnostic port"],
            ["3", "RX0", "Input", "Telemetry debug UART receive from umbilical diagnostic port"],
        ],
        "register_notes": [
            "Primary I2C Master bus interface resides on GPIO21 (SDA) and GPIO22 (SCL).",
            "Bus arbitration operates up to 400 kHz Fast Mode. Pull-up resistance must be between 2.2kΩ and 4.7kΩ to 3.3V.",
            "Hardware strapping pin GPIO0 must be pulled HIGH during boot to enter normal SPI Flash execution mode.",
            "UART0 provides 115200 baud 8-N-1 packet streaming for pre-flight readiness console output.",
        ],
        "guidelines": [
            "Ensure low-ESR ceramic decoupling capacitors (10µF + 100nF) are placed immediately adjacent to the VDD pin.",
            "Avoid routing high-frequency switching lines directly underneath the RF trace keep-out zone.",
            "All telemetry logging buffers must flush to non-volatile SPI flash before entering low-power hibernation.",
        ],
    },
    {
        "filename": "tmp102_datasheet.pdf",
        "doc_id": "ds-tmp102",
        "title": "TMP102 Temperature Sensor Data Sheet",
        "doc_type": "datasheet",
        "subsystem_tag": "CDHS",
        "doc_code": "SP-CDHS-DOC-02",
        "summary": "Low-power 12-bit digital temperature sensor ideal for satellite thermal monitoring across battery bays, solar panel hinge assemblies, and OBC processing cores. Communicates over a two-wire two-direction I2C interface.",
        "specs": [
            ["Parameter", "Min", "Max", "Conditions / Notes"],
            ["Supply Voltage", "1.4 V", "3.6 V", "Operates directly from 3.3V logic rail"],
            ["Quiescent Current", "10 µA", "15 µA", "During active temperature conversion"],
            ["Shutdown Current", "0.5 µA", "1 µA", "Ultra-low power standby mode"],
            ["Temperature Accuracy", "-0.5 °C", "+0.5 °C", "Over -25°C to +85°C flight range"],
            ["Resolution", "12 bits", "13 bits", "0.0625°C resolution per LSB"],
        ],
        "pinout": [
            ["Pin #", "Name", "Type", "Function / Subsystem Interconnect"],
            ["1", "SCL", "Input", "I2C Serial Clock input from CDHS master"],
            ["2", "GND", "Power", "Chassis ground return"],
            ["3", "ALERT", "Output", "Active-low open-drain thermal alert over-temp interrupt"],
            ["4", "ADD0", "Input", "Address selection strap pin (GND, V+, SDA, SCL)"],
            ["5", "V+", "Power", "Positive power supply rail (1.4V to 3.6V)"],
            ["6", "SDA", "I/O", "I2C Serial Data bidirectional line"],
        ],
        "register_notes": [
            "Address selection via ADD0: Connected to GND -> 0x48 (0b1001000).",
            "Address selection via ADD0: Connected to V+ -> 0x49 (0b1001001).",
            "Address selection via ADD0: Connected to SDA -> 0x4A (0b1001010).",
            "Address selection via ADD0: Connected to SCL -> 0x4B (0b1001011).",
            "Temperature Register (Pointer 0x00): Read-only 16-bit word containing 12-bit digital thermal reading.",
        ],
        "guidelines": [
            "Mount in direct thermal conductive contact with battery cells or aluminum chassis mounting boss.",
            "Use a 0.1µF decoupling capacitor between V+ and GND placed within 3mm of the sensor body.",
        ],
    },
    {
        "filename": "mpu6050_datasheet.pdf",
        "doc_id": "ds-mpu6050",
        "title": "MPU-6050 6-Axis Motion Tracking IMU Data Sheet",
        "doc_type": "datasheet",
        "subsystem_tag": "ADCS/APC",
        "doc_code": "SP-ADCS-DOC-01",
        "summary": "Integrated 6-axis MotionTracking device combining a 3-axis gyroscope and a 3-axis accelerometer on a single silicon die. Supplies body rate measurements for detumbling and attitude determination during satellite separation.",
        "specs": [
            ["Parameter", "Min", "Max", "Conditions / Notes"],
            ["VDD Supply Voltage", "2.375 V", "3.46 V", "Operates from 3.3V spacecraft bus"],
            ["Operating Current", "3.5 mA", "4.0 mA", "Full 6-axis sensing active"],
            ["Gyro Full-Scale Range", "±250", "±2000 °/s", "User-programmable via GYRO_CONFIG register"],
            ["Accel Full-Scale Range", "±2g", "±16g", "User-programmable via ACCEL_CONFIG register"],
            ["Digital Output Rate", "4 Hz", "8000 Hz", "Configurable sample rate divider"],
        ],
        "pinout": [
            ["Pin #", "Name", "Type", "Function / Subsystem Interconnect"],
            ["1", "CLKIN", "Input", "Optional external reference clock synchronization"],
            ["8", "VLOGIC", "Power", "Digital I/O supply voltage (1.71V to VDD)"],
            ["9", "AD0", "Input", "I2C slave address LSB select pin (GND=0x68, VLOGIC=0x69)"],
            ["12", "INT", "Output", "Programmable interrupt to OBC (motion/data ready)"],
            ["13", "VDD", "Power", "Main power supply voltage rail"],
            ["18", "GND", "Power", "Power supply ground reference"],
            ["23", "SCL", "Input", "I2C serial clock input line"],
            ["24", "SDA", "I/O", "I2C serial data line"],
        ],
        "register_notes": [
            "I2C 7-bit Slave Address: When AD0 is tied to GND, address is 0x68 (104 dec). When tied to 3.3V, address is 0x69 (105 dec).",
            "WHO_AM_I Register (0x75): Returns constant 0x68 for device identification on startup.",
            "PWR_MGMT_1 Register (0x6B): Bit 6 (SLEEP) must be cleared to 0 immediately upon startup to wake device.",
        ],
        "guidelines": [
            "Align sensor orthogonal axes precisely with CubeSat primary geometric axes X (Roll), Y (Pitch), Z (Yaw).",
            "Keep distance from ferromagnetic structural screws to preserve magnetic decoupling when paired with magnetometer.",
        ],
    },
    {
        "filename": "hmc5883l_datasheet.pdf",
        "doc_id": "ds-hmc5883l",
        "title": "HMC5883L 3-Axis Magnetometer Data Sheet",
        "doc_type": "datasheet",
        "subsystem_tag": "ADCS/APC",
        "doc_code": "SP-ADCS-DOC-02",
        "summary": "Surface-mount high-resolution 3-axis magneto-resistive sensor. Measures Earth's magnetic field vector in Low Earth Orbit (LEO) for B-dot detumbling algorithm execution and magnetic torque rod activation control.",
        "specs": [
            ["Parameter", "Min", "Max", "Conditions / Notes"],
            ["Supply Voltage (VDD)", "2.16 V", "3.6 V", "Nominal 3.3V flight bus supply"],
            ["Current Consumption", "100 µA", "120 µA", "During 15 Hz measurement cycle"],
            ["Field Range", "-8.0 G", "+8.0 Gauss", "Saturates near magnetic dipole saturation"],
            ["Resolution", "0.73 mG", "5 mGauss", "12-bit ADC conversion"],
            ["Output Rate", "0.75 Hz", "75 Hz", "Configurable in Configuration Register A"],
        ],
        "pinout": [
            ["Pin #", "Name", "Type", "Function / Subsystem Interconnect"],
            ["1", "SCL", "Input", "I2C Serial Clock (up to 400 kHz)"],
            ["2", "VDD", "Power", "Positive power supply input rail"],
            ["4", "S1", "Power", "Sensor bridge capacitor connection"],
            ["9", "GND", "Power", "Supply ground"],
            ["11", "VDDIO", "Power", "Digital I/O supply voltage (1.71V to VDD)"],
            ["15", "DRDY", "Output", "Data Ready pulse interrupt output pin"],
            ["16", "SDA", "I/O", "I2C Serial Data bidirectional line"],
        ],
        "register_notes": [
            "I2C 7-bit Slave Address is fixed in hardware: 0x1E (0b0011110) for write, 0x3D for read byte.",
            "Identification Registers (0x0A, 0x0B, 0x0C) return ASCII values 'H', '4', '3'.",
            "Mode Register (0x02): Set bits [1:0] to 00 for Continuous-Measurement Mode.",
        ],
        "guidelines": [
            "Must be positioned as far away as possible from high-current solar panel lines and magnetic torque coils.",
            "Perform in-situ 3-axis hard-iron and soft-iron calibration once integrated inside the chassis frame.",
        ],
    },
    {
        "filename": "ina219_datasheet.pdf",
        "doc_id": "ds-ina219",
        "title": "INA219 High-Side DC Current and Power Sensor Data Sheet",
        "doc_type": "datasheet",
        "subsystem_tag": "EPS",
        "doc_code": "SP-EPS-DOC-01",
        "summary": "Bi-directional high-side current shunt and bus voltage monitor with I2C/SMBus interface. Senses both shunt voltage drop across a precision sense resistor (0.1Ω) and bus supply voltage to compute battery state-of-charge.",
        "specs": [
            ["Parameter", "Min", "Max", "Conditions / Notes"],
            ["Bus Voltage Range", "0 V", "+26 V", "Monitors battery rail up to 26V DC"],
            ["Supply Voltage (Vs)", "3.0 V", "5.5 V", "Powered from 3.3V or 5.0V regulated rail"],
            ["Quiescent Current", "0.7 mA", "1.0 mA", "Standard active sampling mode"],
            ["Max Shunt Voltage", "±40 mV", "±320 mV", "Programmable PGA gain (1, 2, 4, 8)"],
            ["ADC Resolution", "9 bits", "12 bits", "Up to 128 samples averaged per conversion"],
        ],
        "pinout": [
            ["Pin #", "Name", "Type", "Function / Subsystem Interconnect"],
            ["1", "A1", "Input", "Address pin 1 (GND, VS, SDA, SCL)"],
            ["2", "A0", "Input", "Address pin 0 (GND, VS, SDA, SCL)"],
            ["3", "SDA", "I/O", "I2C Serial Data bidirectional line"],
            ["4", "SCL", "Input", "I2C Serial Clock line"],
            ["5", "VS", "Power", "Sensor logic power supply (+3.3V)"],
            ["6", "GND", "Power", "Ground return reference"],
            ["7", "IN-", "Input", "Negative shunt voltage sense connection to load"],
            ["8", "IN+", "Input", "Positive shunt voltage sense connection to battery"],
        ],
        "register_notes": [
            "16 selectable I2C slave addresses using pins A0 and A1.",
            "A1=GND, A0=GND -> Slave address 0x40 (0b1000000).",
            "A1=GND, A0=VS  -> Slave address 0x41 (0b1000001).",
            "A1=GND, A0=SDA -> Slave address 0x42 (0b1000010).",
            "A1=GND, A0=SCL -> Slave address 0x43 (0b1000011).",
            "Configuration Register (0x00): Configures PGA range, bus voltage range, and ADC averaging.",
        ],
        "guidelines": [
            "Kelvin connection routing is mandatory for IN+ and IN- traces to prevent trace resistance from falsifying current readings.",
            "Sense resistor rating must tolerate peak charging in-rush current up to 3.0A without exceeding 100°C.",
        ],
    },
    {
        "filename": "tp4056_guide.pdf",
        "doc_id": "ds-tp4056",
        "title": "TP4056 Lithium Battery Charging Module Guide",
        "doc_type": "user_guide",
        "subsystem_tag": "EPS",
        "doc_code": "SP-EPS-DOC-02",
        "summary": "Complete constant-current/constant-voltage (CC/CV) linear charger module for single-cell or dual-cell parallel lithium-ion flight batteries. Features internal thermal feedback to restrict charging current during solar peak temperatures.",
        "specs": [
            ["Parameter", "Min", "Max", "Conditions / Notes"],
            ["Input Supply Voltage", "4.5 V", "6.5 V", "Supplied by solar regulator boost converter"],
            ["Float Voltage", "4.158 V", "4.242 V", "Precision 4.2V ±1% termination threshold"],
            ["Charge Current", "100 mA", "1000 mA", "Configured via external R_PROG resistor"],
            ["C/10 Termination", "0.08 C", "0.12 C", "Automatic charge cycle termination"],
            ["Soft-Start Time", "10 µs", "20 µs", "Prevents in-rush current on bus switch-on"],
        ],
        "pinout": [
            ["Pin #", "Name", "Type", "Function / Subsystem Interconnect"],
            ["1", "TEMP", "Input", "Battery temperature NTC thermistor sensor input"],
            ["2", "PROG", "Analog", "Charge current setting and charge monitor pin"],
            ["3", "GND", "Power", "Chassis and battery ground return"],
            ["4", "VCC", "Power", "Input power from solar regulator (5.0V nominal)"],
            ["5", "BAT", "Output", "Positive terminal connection to Li-Ion cell (+4.2V)"],
            ["6", "STDBY", "Output", "Open-drain battery charge complete indicator pin"],
            ["7", "CHRG", "Output", "Open-drain charging in progress indicator pin"],
            ["8", "CE", "Input", "Chip enable active high input pin"],
        ],
        "register_notes": [
            "Current configuration formula: I_CHRG = (V_PROG / R_PROG) * 1200, where V_PROG = 1.0V.",
            "For 500mA flight charge rate: R_PROG = 2.4 kΩ.",
            "CHRG pin goes low (active) while cell is charging; pulls high when battery voltage reaches 4.2V.",
        ],
        "guidelines": [
            "Ensure the TEMP thermistor is bonded directly onto the flight battery pouch with space-grade thermally conductive epoxy.",
            "Thermal relief pad beneath the TP4056 package must be soldered to internal copper ground plane for heatsinking.",
        ],
    },
    {
        "filename": "solar_regulator_guide.pdf",
        "doc_id": "ds-solar",
        "title": "Solar Panel Regulator & Boost Converter Module Guide",
        "doc_type": "user_guide",
        "subsystem_tag": "EPS",
        "doc_code": "SP-EPS-DOC-03",
        "summary": "Multi-channel solar array peak power tracking and conditioning module. Accepts variable DC voltage from body-mounted photovoltaic panels and converts to stabilized 5.0V and 3.3V primary power rails for distribution across all spacecraft subsystems.",
        "specs": [
            ["Parameter", "Min", "Max", "Conditions / Notes"],
            ["Array Input Voltage", "2.0 V", "18.0 V", "Accommodates eclipse exit cold array spike"],
            ["Regulated Rail Output", "4.95 V", "5.05 V", "High-efficiency synchronous buck-boost"],
            ["Conversion Efficiency", "92 %", "96 %", "At 1.5A load across 6V-12V input range"],
            ["Overvoltage Clamp", "5.3 V", "5.5 V", "Crowbar protection against solar surge"],
            ["Switching Frequency", "1.2 MHz", "1.5 MHz", "Synchronous PWM switching"],
        ],
        "pinout": [
            ["Pin #", "Name", "Type", "Function / Subsystem Interconnect"],
            ["1", "PV_IN+", "Power", "Photovoltaic panel string positive terminal"],
            ["2", "PV_IN-", "Power", "Photovoltaic panel string return terminal"],
            ["3", "GND", "Power", "Main chassis ground reference"],
            ["4", "VOUT_5V", "Power", "Stabilized 5.0V bus line out to charging module"],
            ["5", "EN_REG", "Input", "Regulator enable control line from OBC (CDHS)"],
            ["6", "PWR_GOOD", "Output", "Active-high power good flag to OBC interrupt line"],
        ],
        "register_notes": [
            "Autonomous analog MPPT control loop operates with no software dependency for guaranteed black-start capability.",
            "PWR_GOOD output remains low until 5.0V rail is within ±3% of target operating threshold.",
        ],
        "guidelines": [
            "Isolate high-current switching inductor nodes from sensitive RF transceiver traces.",
            "Each solar string must include a low forward-voltage Schottky blocking diode (e.g. 0.25V drop) to prevent reverse current leakage during eclipse.",
        ],
    },
    {
        "filename": "cdhs_connector_pinout_guide.pdf",
        "doc_id": "ds-cdhs-bus",
        "title": "CDHS Main Bus Connector Pinout Guide",
        "doc_type": "user_guide",
        "subsystem_tag": "CDHS",
        "doc_code": "SP-CDHS-DOC-03",
        "summary": "Specification guide for the standardized SpacePoint 10-pin stackable header interface (Connectors J1 through J6) bridging CDHS to EPS, ADCS, and payload daughterboards.",
        "specs": [
            ["Parameter", "Min", "Max", "Conditions / Notes"],
            ["Rated Pin Current", "2.0 A", "3.0 A", "Continuous per connector pin contact"],
            ["Contact Resistance", "10 mΩ", "20 mΩ", "Gold-plated phosphor bronze pins"],
            ["Dielectric Withstanding", "500 V", "750 V", "Sea level and vacuum qualified"],
            ["Mating Durability", "50 cycles", "100 cycles", "Without contact degradation"],
            ["Header Pitch", "2.54 mm", "2.54 mm", "Standard dual-row unshrouded header"],
        ],
        "pinout": [
            ["Pin #", "Name", "Type", "Function / Subsystem Interconnect"],
            ["Pin 1", "3V3_BUS", "Power", "Regulated 3.3V main system power rail"],
            ["Pin 2", "5V0_BUS", "Power", "Regulated 5.0V secondary system power rail"],
            ["Pin 3", "GND", "Power", "Primary system power ground return"],
            ["Pin 4", "GND", "Power", "Redundant system ground return"],
            ["Pin 5", "I2C_SDA", "I/O", "Inter-subsystem I2C bus serial data (Pull-up 4.7kΩ)"],
            ["Pin 6", "I2C_SCL", "Clock", "Inter-subsystem I2C bus serial clock (400 kHz)"],
            ["Pin 7", "UART_TX", "Output", "OBC Telemetry data transmit to radio transmitter"],
            ["Pin 8", "UART_RX", "Input", "OBC Telecommand data receive from radio receiver"],
            ["Pin 9", "ALERT_INT", "Input", "Active-low global subsystem fault/alert interrupt"],
            ["Pin 10", "RESET_N", "Input", "Active-low hardware subsystem master reset line"],
        ],
        "register_notes": [
            "Connector J6 on hardware revision Rev-B contains a documented layout anomaly: Pin 3 and Pin 4 must be cross-jumpered for redundant ground bonding.",
            "Always inspect connector jumper header tables prior to powering the flight stack.",
        ],
        "guidelines": [
            "Use polarized keyed shrouds on umbilical flight cables to prevent 180-degree reverse insertion.",
            "Verify with digital multimeter that 5V0_BUS is never shorted to 3V3_BUS prior to applying battery power.",
        ],
    },
    {
        "filename": "i2c_uart_bus_wiring.pdf",
        "doc_id": "ds-i2c-bus",
        "title": "I2C & UART Bus Wiring Reference Guide",
        "doc_type": "user_guide",
        "subsystem_tag": "CDHS",
        "doc_code": "SP-CDHS-DOC-04",
        "summary": "Engineering reference manual for digital serial communication topology within the SpacePoint CubeSat structure. Covers pull-up calculation, signal integrity, capacitance budgets, and level-shifting rules.",
        "specs": [
            ["Parameter", "Min", "Max", "Conditions / Notes"],
            ["I2C Standard Mode", "10 kHz", "100 kHz", "For legacy payload and low-speed sensors"],
            ["I2C Fast Mode", "100 kHz", "400 kHz", "Standard flight bus operating frequency"],
            ["Max Bus Capacitance", "200 pF", "400 pF", "Total trace + pin capacitance on SDA/SCL"],
            ["UART Baud Rates", "9600", "115200", "Standard 8-N-1 asynchronous framing"],
            ["Logic High Threshold", "0.7 * VDD", "VDD + 0.3V", "Minimum 2.31V for 3.3V logic"],
        ],
        "pinout": [
            ["Line", "Signal", "Direction", "Recommended Pull-Up / Termination"],
            ["SDA", "Serial Data", "Bidirectional", "4.7 kΩ pull-up to 3.3V on CDHS mainboard"],
            ["SCL", "Serial Clock", "Master -> Slave", "4.7 kΩ pull-up to 3.3V on CDHS mainboard"],
            ["TXD", "Serial Transmit", "Transmitter -> Receiver", "No pull-up; 33Ω series damping resistor"],
            ["RXD", "Serial Receive", "Receiver <- Transmitter", "No pull-up; 33Ω series damping resistor"],
        ],
        "register_notes": [
            "Only ONE set of pull-up resistors should be present on the entire I2C bus (installed on the CDHS master board).",
            "Daughterboards (sensors, payload) MUST have their local I2C pull-ups disabled or unpopulated to avoid lowering total bus impedance below 1.5kΩ.",
        ],
        "guidelines": [
            "Route SDA and SCL as differential pairs with matched lengths and keep clear of PWM lines.",
            "Ground planes must run unbroken beneath all digital serial lines for return current containment.",
        ],
    },
    {
        "filename": "payload_integration_guide.pdf",
        "doc_id": "ds-payload",
        "title": "Payload Subsystem Integration Guide",
        "doc_type": "user_guide",
        "subsystem_tag": "ADCS/APC",
        "doc_code": "SP-PAYLOAD-DOC-01",
        "summary": "Electrical and mechanical integration ICD (Interface Control Document) for secondary scientific and camera payloads operating in the SpacePoint 1U/3U CubeSat platform.",
        "specs": [
            ["Parameter", "Min", "Max", "Conditions / Notes"],
            ["Mass Budget", "150 g", "350 g", "Allocated payload bay mass"],
            ["Envelope Dimensions", "85 x 85 mm", "80 mm depth", "Standardized payload volume"],
            ["Peak Power Allotment", "1.5 W", "3.0 W", "Permitted for max 5 minutes per orbit"],
            ["Standby Power", "10 mW", "50 mW", "During eclipse and non-imaging passes"],
            ["Interface Protocol", "SPI / I2C", "UART", "Commands over I2C, raw data over SPI/UART"],
        ],
        "pinout": [
            ["Pin #", "Signal", "Type", "Function / Subsystem Interconnect"],
            ["1", "PAYLOAD_5V", "Power", "Switched 5.0V power rail controlled by OBC MOSFET switch"],
            ["2", "GND", "Power", "Chassis ground return"],
            ["3", "SPI_MOSI", "Output", "High-speed sensor payload command data"],
            ["4", "SPI_MISO", "Input", "High-speed sensor image data return"],
            ["5", "SPI_SCK", "Output", "High-speed SPI clock line (up to 10 MHz)"],
            ["6", "PAYLOAD_CS", "Output", "Active-low chip select from CDHS"],
            ["7", "PAYLOAD_INT", "Input", "Interrupt line signaling data capture complete"],
        ],
        "register_notes": [
            "Payload power must be toggled strictly via CDHS telecommand to protect the EPS battery budget.",
            "Always poll the PAYLOAD_INT pin before initiating SPI DMA transfers.",
        ],
        "guidelines": [
            "Thermal heat strap must couple the payload image sensor directly to the -Y chassis radiation panel.",
            "Verify that payload EMI emissions do not degrade UHF/VHF uplink antenna receiver sensitivity.",
        ],
    },
    {
        "filename": "microsd_user_guide.pdf",
        "doc_id": "ds-microsd",
        "title": "MicroSD Card Interface User Guide",
        "doc_type": "user_guide",
        "subsystem_tag": "CDHS",
        "doc_code": "SP-CDHS-DOC-05",
        "summary": "High-capacity non-volatile telemetry payload storage module communicating via 4-wire SPI bus. Stores continuous flight log files, gyro rates, solar currents, and system health status for orbital dump.",
        "specs": [
            ["Parameter", "Min", "Max", "Conditions / Notes"],
            ["Operating Voltage", "2.7 V", "3.6 V", "Level shifted from 3.3V bus"],
            ["Read Current", "15 mA", "25 mA", "During continuous block read"],
            ["Write Current", "20 mA", "40 mA", "During continuous block write"],
            ["Max SPI Frequency", "10 MHz", "25 MHz", "Clock speed supported in SPI mode"],
            ["Operating Temp", "-40 °C", "+85 °C", "Industrial space-grade flash storage"],
        ],
        "pinout": [
            ["Pin #", "Signal", "Type", "Function / Subsystem Interconnect"],
            ["1", "CS", "Input", "SPI Chip Select active low from CDHS"],
            ["2", "DI", "Input", "SPI Data In (MOSI) from OBC"],
            ["3", "VSS1", "Power", "Ground return reference"],
            ["4", "VDD", "Power", "Positive power supply rail (3.3V)"],
            ["5", "SCLK", "Input", "SPI Clock from OBC"],
            ["6", "VSS2", "Power", "Ground return reference"],
            ["7", "DO", "Output", "SPI Data Out (MISO) to OBC"],
        ],
        "register_notes": [
            "Card initializes in SPI mode by sending 74+ clock cycles with CS high, followed by CMD0 with CS low.",
            "Block size is locked to 512 bytes for reliable flash sector alignment.",
        ],
        "guidelines": [
            "Ensure low-pass filtering on VDD line with 10µF tantalum and 0.1µF ceramic capacitors.",
            "Maintain trace lengths under 50mm to minimize reflections at 20MHz SPI clock frequencies.",
        ],
    },
    {
        "filename": "bmp280_datasheet.pdf",
        "doc_id": "ds-bmp280",
        "title": "BMP280 Barometric Pressure & Temp Sensor Data Sheet",
        "doc_type": "datasheet",
        "subsystem_tag": "CDHS",
        "doc_code": "SP-CDHS-DOC-06",
        "summary": "Absolute barometric pressure and temperature sensor designed for clean-room testing, launch vehicle fairing depressurization tracking, and pressurized payload bay monitoring.",
        "specs": [
            ["Parameter", "Min", "Max", "Conditions / Notes"],
            ["Supply Voltage (VDD)", "1.71 V", "3.6 V", "Powered from 3.3V bus"],
            ["Current (1Hz Sampling)", "2.7 µA", "3.2 µA", "Ultra-low power monitoring"],
            ["Pressure Range", "300 hPa", "1100 hPa", "Full tropospheric to vacuum qualification"],
            ["Temperature Range", "-40 °C", "+85 °C", "Operational flight temperature"],
            ["RMS Noise", "0.2 Pa", "0.5 Pa", "Equivalent to 1.7 cm altitude resolution"],
        ],
        "pinout": [
            ["Pin #", "Name", "Type", "Function / Subsystem Interconnect"],
            ["1", "GND", "Power", "Ground return"],
            ["2", "CSB", "Input", "Chip select (tie to VDD for I2C interface)"],
            ["3", "SDI", "I/O", "I2C Serial Data (SDA) / SPI MOSI"],
            ["4", "SCK", "Input", "I2C Serial Clock (SCL) / SPI SCK"],
            ["5", "SDO", "I/O", "I2C Address LSB select (GND=0x76, VDD=0x77) / SPI MISO"],
            ["6", "VDDIO", "Power", "Digital interface supply rail"],
            ["7", "GND", "Power", "Ground return"],
            ["8", "VDD", "Power", "Main analog supply rail"],
        ],
        "register_notes": [
            "I2C 7-bit Slave Address: 0x76 when SDO pin is grounded, 0x77 when SDO is tied to VDD.",
            "ID Register (0xD0): Returns 0x58 indicating genuine BMP280 silicon revision.",
        ],
        "guidelines": [
            "Keep vent hole clear of potting compound, conformal coating, or thermal tape.",
            "Mount away from air conditioning blast ducts to avoid false barometric pressure transients.",
        ],
    },
    {
        "filename": "reaction_wheel_datasheet.pdf",
        "doc_id": "ds-reaction-wheel",
        "title": "Micro-Reaction Wheel Actuator Module Data Sheet",
        "doc_type": "datasheet",
        "subsystem_tag": "ADCS/APC",
        "doc_code": "SP-ADCS-DOC-03",
        "summary": "Brushless DC momentum/reaction wheel assembly for 3-axis CubeSat attitude pointing. Features internal Hall effect sensors, closed-loop speed controller, and telemetry reporting over I2C/UART.",
        "specs": [
            ["Parameter", "Min", "Max", "Conditions / Notes"],
            ["Operating Voltage", "4.75 V", "5.25 V", "High-power 5.0V bus line"],
            ["Max Momentum Storage", "1.5 mNms", "3.0 mNms", "At 6000 RPM nominal speed"],
            ["Peak Torque", "0.2 mNm", "0.5 mNm", "During acceleration slews"],
            ["Max Speed", "1000 RPM", "8000 RPM", "Bidirectional CW/CCW rotation"],
            ["Peak Current", "150 mA", "350 mA", "During rapid torque ramp"],
        ],
        "pinout": [
            ["Pin #", "Signal", "Type", "Function / Subsystem Interconnect"],
            ["1", "5V_MOTOR", "Power", "Dedicated 5.0V motor drive line"],
            ["2", "GND", "Power", "Chassis ground return"],
            ["3", "I2C_SDA", "I/O", "Speed command and telemetry data"],
            ["4", "I2C_SCL", "Clock", "I2C Clock line (up to 400 kHz)"],
            ["5", "BRAKE", "Input", "Active-high dynamic emergency brake line"],
            ["6", "SPEED_PULSE", "Output", "Hall effect frequency pulse out"],
        ],
        "register_notes": [
            "I2C Slave Address: 0x28 (0b00101000) for Wheel X, 0x29 for Wheel Y, 0x2A for Wheel Z.",
            "Target Velocity Register (0x01): Signed 16-bit word controlling RPM magnitude and direction.",
        ],
        "guidelines": [
            "Mount securely to satellite primary structural frame using thread locker to prevent vibration loosening during launch.",
            "Ensure dynamic balancing calibration has been performed to prevent micro-vibrations from blurring payload imagery.",
        ],
    },
    {
        "filename": "eps_charging_guide.pdf",
        "doc_id": "ds-eps-charging",
        "title": "EPS Battery Charging & Power Distribution Guide",
        "doc_type": "user_guide",
        "subsystem_tag": "EPS",
        "doc_code": "SP-EPS-DOC-04",
        "summary": "System integration user guide detailing the electrical power conditioning architecture, battery charging algorithm, over-current latching protection, and power rail switching logic for the SpacePoint satellite platform.",
        "specs": [
            ["Parameter", "Min", "Max", "Conditions / Notes"],
            ["Battery Chemistry", "Li-Ion", "NMC 18650", "2S1P configuration nominal 7.4V"],
            ["Battery Capacity", "2600 mAh", "3500 mAh", "Total stored onboard energy 26 Wh"],
            ["Main Bus 3.3V Output", "3.28 V", "3.32 V", "Low-noise buck regulator, 3.0A max"],
            ["Main Bus 5.0V Output", "4.95 V", "5.05 V", "High-efficiency boost regulator, 2.5A max"],
            ["Cut-off Threshold", "6.0 V", "6.2 V", "Undervoltage lockout protection"],
        ],
        "pinout": [
            ["Rail", "Voltage", "Max Current", "Subsystems Powered"],
            ["3V3_BUS", "3.3 V", "3.0 A", "CDHS OBC, ADCS sensors, RTC, Telemetry"],
            ["5V0_BUS", "5.0 V", "2.5 A", "Radio PA, Reaction Wheels, Scientific Payload"],
            ["VBAT_RAW", "6.0 - 8.4 V", "5.0 A", "Direct battery rail to high-current heaters"],
            ["CHG_IN", "5.0 - 15.0 V", "2.0 A", "Solar panel array input line"],
        ],
        "register_notes": [
            "Battery state of charge (SoC) lookup table stored in non-volatile EPS microcontroller registers.",
            "Emergency shedding profile: when VBAT drops below 6.8V, 5V0_BUS is automatically disconnected to preserve CDHS.",
        ],
        "guidelines": [
            "Never connect flight battery pack until ground safety removal pin (RBF pin) has been verified open.",
            "Perform load transient testing using electronic load before closing flight enclosure.",
        ],
    },
]


async def seed_datasheets() -> None:
    print("=" * 70)
    print(" SpacePoint Satellite Hardware Datasheet Generator & Seeder")
    print("=" * 70)

    # 1. Run DDL checks
    print("\n[1/3] Ensuring database schema and tables exist...")
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: PreSessionQuizDatasheet.__table__.create(sync_conn, checkfirst=True)
        )
        await conn.execute(
            text("ALTER TABLE pre_session_quiz_presets ADD COLUMN IF NOT EXISTS phases JSONB DEFAULT '[]'::jsonb;")
        )
    print("      Table 'pre_session_quiz_datasheets' and preset schema verified.")

    # 2. Build PDFs and save to storage_local
    print("\n[2/3] Generating and encrypting PDF datasheets to local storage...")
    now = datetime.now(timezone.utc)
    pdf_count = 0

    for ds in DATASHEET_DEFINITIONS:
        filename = ds["filename"]
        pdf_bytes = build_datasheet_pdf(
            title=ds["title"],
            doc_type=ds["doc_type"],
            subsystem=ds["subsystem_tag"],
            doc_code=ds["doc_code"],
            summary=ds["summary"],
            specs=ds["specs"],
            pinout=ds["pinout"],
            register_notes=ds["register_notes"],
            guidelines=ds["guidelines"],
        )
        await storage_local.upload_to_path("datasheets", filename, pdf_bytes, "application/pdf")
        pdf_count += 1
        print(f"      + Saved PDF: datasheets/{filename} ({len(pdf_bytes):,} bytes)")

    # 3. Insert or update rows in pre_session_quiz_datasheets
    print("\n[3/3] Synchronizing database datasheet library...")
    row_count = 0
    async with AsyncSessionLocal() as db:
        for ds in DATASHEET_DEFINITIONS:
            filename = ds["filename"]
            url = f"/files/datasheets/{filename}"

            existing = (
                await db.execute(
                    select(PreSessionQuizDatasheet).where(PreSessionQuizDatasheet.url == url)
                )
            ).scalars().first()

            if existing:
                existing.title = ds["title"]
                existing.doc_type = ds["doc_type"]
                existing.subsystem_tag = ds["subsystem_tag"]
                existing.description = ds["summary"]
                existing.page_count = 2
                existing.is_active = True
                existing.updated_at = now
            else:
                new_row = PreSessionQuizDatasheet(
                    id=uuid.uuid5(uuid.NAMESPACE_DNS, f"spacepoint.datasheet.{filename}"),
                    title=ds["title"],
                    url=url,
                    doc_type=ds["doc_type"],
                    subsystem_tag=ds["subsystem_tag"],
                    description=ds["summary"],
                    page_count=2,
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
                db.add(new_row)
            row_count += 1

        await db.commit()
    print(f"      + Synchronized {row_count} datasheet library records in database.")

    await engine.dispose()
    print("\n" + "=" * 70)
    print(f" SUCCESS: Seeded {pdf_count} encrypted PDFs and {row_count} database rows!")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(seed_datasheets())

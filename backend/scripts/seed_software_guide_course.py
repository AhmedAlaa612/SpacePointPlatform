"""Seed script for the SpacePoint Flight Software & Subsystems LMS Course.

Populates the 4 modules with complete composite lessons (Rich Markdown theory,
architecture diagrams, address tables, and interactive code practice & hardware labs).
"""

import argparse
import asyncio
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.enums import UserRole
from app.models.lms.course import Course, CourseModule, ModuleItem
from app.models.user import User

COURSE_TITLE = "SpacePoint Software Guide: Flight Software & Subsystems"


async def seed(db: AsyncSession, dry_run: bool = False) -> None:
    print(f"[*] Seeding '{COURSE_TITLE}'...")

    # 1. Find an admin user to author the course
    admin_res = await db.execute(select(User).where(User.roles.contains([UserRole.admin])).limit(1))
    admin_user = admin_res.scalar_one_or_none()
    if not admin_user:
        user_res = await db.execute(select(User).limit(1))
        admin_user = user_res.scalar_one_or_none()
        if not admin_user:
            print("[-] Error: No users found in database to author course.")
            return

    # 2. Check if course already exists
    res = await db.execute(select(Course).where(Course.title == COURSE_TITLE))
    course = res.scalar_one_or_none()

    if not course:
        course = Course(
            id=uuid.uuid4(),
            title=COURSE_TITLE,
            description=(
                "Master the ESP32 microcontroller, satellite communication protocols (UART, I2C, CAN, SPI), "
                "and flight software for Command & Data Handling (CDHS) and Attitude Determination & Control (ADCS)."
            ),
            kind="course",
            is_published=True,
            created_by=admin_user.id,
            level="intermediate",
            track="Avionics & Flight Software",
            access_mode="open",
            outcomes=[
                "Configure the ESP32 and Arduino development environment for aerospace",
                "Wire and verify serial, I2C, CAN, and SPI avionics bus topologies",
                "Read telemetry from TMP102 temperature and INA219 power sensors",
                "Write persistent telemetry logs to FRAM non-volatile memory",
                "Control reaction wheel DC motors with high-precision PWM",
                "Integrate the MPU6050 6-axis gyroscope for spacecraft attitude determination",
            ],
        )
        db.add(course)
        await db.flush()
        print(f"    [+] Created course: {course.id}")
    else:
        print(f"    [=] Found existing course: {course.id}")
        course.is_published = True
        course.access_mode = "open"

    # Define curriculum structure with complete rich Markdown explanations and interactive components
    curriculum = [
        # ── MODULE 1: EMBEDDED C++ & ESP32 FUNDAMENTALS ──────────────────────────
        {
            "title": "1. Embedded C++ & ESP32 Fundamentals",
            "items": [
                {
                    "title": "Downloading the Arduino IDE",
                    "kind": "text",
                    "content": {
                        "body": (
                            "## Setting Up Your Development Environment\n\n"
                            "The Arduino IDE is the desktop software we use to write, compile, and upload code to our ESP32 microcontrollers.\n\n"
                            "### Download for your Operating System:\n"
                            "- [Download for Windows (Installer)](https://www.arduino.cc/en/software)\n"
                            "- [Download for macOS](https://www.arduino.cc/en/software)\n"
                            "- [Download for Linux](https://www.arduino.cc/en/software)\n\n"
                            "### Installation Steps:\n"
                            "1. Download the installer for your operating system from the links above.\n"
                            "2. Run the installer and accept the default USB driver installation prompts.\n"
                            "3. Launch the Arduino IDE once installation finishes."
                        ),
                    },
                },
                {
                    "title": "Adding ESP32 Board Support",
                    "kind": "text",
                    "content": {
                        "body": (
                            "## Adding ESP32 Board Support to Arduino IDE\n\n"
                            "By default, the Arduino IDE only recognizes standard Arduino microcontrollers (like the Uno). To program the ESP32, you need to install the official Espressif board definitions.\n\n"
                            "### Step 1: Add Board Manager URL\n"
                            "1. In Arduino IDE, open **File > Preferences** (or **Arduino IDE > Settings** on macOS).\n"
                            "2. Locate the **Additional Boards Manager URLs** field and paste this URL:\n\n"
                            "```text\n"
                            "https://espressif.github.io/arduino-esp32/package_esp32_index.json\n"
                            "```\n\n"
                            "3. Click **OK** to save your preferences.\n\n"
                            "### Step 2: Install ESP32 Package\n"
                            "1. Go to **Tools > Board > Boards Manager**.\n"
                            "2. Type `esp32` in the search bar.\n"
                            "3. Find **esp32 by Espressif Systems** and click **Install**.\n\n"
                            "Once installed, select your board model under **Tools > Board > esp32**."
                        ),
                    },
                },
                {
                    "title": "Core C++ Data Types & Embedded Memory",
                    "kind": "text",
                    "content": {
                        "body": (
                            "## Core C++ Data Types in Embedded Programming\n\n"
                            "In embedded programming, choosing the right data type matters for memory and performance. Microcontrollers have limited RAM compared to desktop computers.\n\n"
                            "| Type | Purpose | Size on ESP32 | Example Value |\n"
                            "| :--- | :--- | :--- | :--- |\n"
                            "| `int` | Whole numbers and counters | 32-bit (4 bytes) | `int count = 10;` |\n"
                            "| `float` | Decimal numbers and measurements | 32-bit (4 bytes) | `float voltage = 3.3;` |\n"
                            "| `bool` | True or false flags | 8-bit (1 byte) | `bool isActive = true;` |\n"
                            "| `char` | Single text characters | 8-bit (1 byte) | `char grade = 'A';` |\n\n"
                            "> **Note:** On 8-bit microcontrollers (like Arduino Uno), `int` is 16 bits. On the 32-bit ESP32, standard `int` is 32 bits."
                        ),
                    },
                },
                {
                    "title": "C++ Practice: Variable Declarations",
                    "kind": "practice",
                    "content": {
                        "markdown": (
                            "## Declaring and Initializing Variables\n\n"
                            "Variables store data in memory during program execution. In embedded code, clear, descriptive names make programs much easier to read and debug.\n\n"
                            "```cpp\n"
                            "// ❌ Unclear naming\n"
                            "int x = 1000;\n\n"
                            "// ✅ Clear naming\n"
                            "int readIntervalMs = 1000;\n"
                            "float sensorVoltage = 3.3;\n"
                            "bool isSystemReady = true;\n"
                            "```\n\n"
                            "- Always initialize your variables when declaring them (`int count = 0;`).\n"
                            "- Use `const` for values that never change during runtime (like pin numbers).\n\n"
                            "> **Practice Challenge:** Declare the three variables below with their proper data types (`int`, `float`, `bool`) and assigned values."
                        ),
                        "instructions": "Declare variables with the correct types (int, float, bool) and initialize them.",
                        "template": (
                            "void setup() {\n"
                            "  Serial.begin(115200);\n\n"
                            "  // 1. Declare an integer named 'count' with value 10\n"
                            "  {{INT_VAR}} count = {{INT_VAL}};\n\n"
                            "  // 2. Declare a float named 'voltage' with value 3.3\n"
                            "  {{FLOAT_VAR}} voltage = {{FLOAT_VAL}};\n\n"
                            "  // 3. Declare a boolean named 'isActive' with value true\n"
                            "  {{BOOL_VAR}} isActive = {{BOOL_VAL}};\n\n"
                            "  Serial.println(\"Variables initialized!\");\n"
                            "}\n"
                        ),
                        "max_attempts": 3,
                        "blanks": [
                            {"token": "{{INT_VAR}}", "label": "Type", "validator_pattern": "^int$", "correct_answer": "int", "hint": "Whole numbers use 'int'."},
                            {"token": "{{INT_VAL}}", "label": "Value", "validator_pattern": "^10$", "correct_answer": "10", "hint": "The count is 10."},
                            {"token": "{{FLOAT_VAR}}", "label": "Type", "validator_pattern": "^float$", "correct_answer": "float", "hint": "Decimals use 'float'."},
                            {"token": "{{FLOAT_VAL}}", "label": "Value", "validator_pattern": "^3\\.3$", "correct_answer": "3.3", "hint": "The voltage is 3.3."},
                            {"token": "{{BOOL_VAR}}", "label": "Type", "validator_pattern": "^bool$", "correct_answer": "bool", "hint": "Flags use 'bool'."},
                            {"token": "{{BOOL_VAL}}", "label": "Value", "validator_pattern": "^(true|1)$", "correct_answer": "true", "hint": "Active is 'true'."},
                        ],
                    },
                },
                {
                    "title": "C++ Practice: For Loop Iteration",
                    "kind": "practice",
                    "content": {
                        "markdown": (
                            "## Loops: Repeating Code\n\n"
                            "Loops allow you to run a block of code multiple times without rewriting it. The two most common loops in C++ are **`for`** and **`while`**:\n\n"
                            "- **`for` loop:** Used when you know in advance how many times you want to iterate (e.g., reading 10 sensor samples).\n"
                            "- **`while` loop:** Used when repeating until a condition changes (e.g., waiting for a hardware sensor connection).\n\n"
                            "```cpp\n"
                            "// Loop from i = 0 up to 4 (5 iterations total)\n"
                            "for (int i = 0; i < 5; i++) {\n"
                            "  Serial.println(i);\n"
                            "}\n"
                            "```\n\n"
                            "> **Practice Challenge:** Complete the for loop header below to count from `0` to `9` (10 iterations total)."
                        ),
                        "instructions": "Complete the loop header to iterate from 0 to 9 (10 iterations).",
                        "template": (
                            "void setup() {\n"
                            "  Serial.begin(115200);\n\n"
                            "  // Loop from i = 0 to i < 10\n"
                            "  for (int i = 0; i < {{LIMIT}}; {{INCREMENT}}) {\n"
                            "    Serial.println(i);\n"
                            "  }\n"
                            "}\n"
                        ),
                        "max_attempts": 3,
                        "blanks": [
                            {"token": "{{LIMIT}}", "label": "Limit", "validator_pattern": "^10$", "correct_answer": "10", "hint": "The loop runs while i < 10."},
                            {"token": "{{INCREMENT}}", "label": "Step", "validator_pattern": "^(i\\+\\+|\\+\\+i|i\\s*\\+=\\s*1)$", "correct_answer": "i++", "hint": "Increment with i++."},
                        ],
                    },
                },
                {
                    "title": "C++ Practice: Thermal Warning Logic (If-Else)",
                    "kind": "practice",
                    "content": {
                        "markdown": (
                            "## Decision Making with If-Else\n\n"
                            "`if` and `else` statements allow your program to make decisions and react dynamically based on sensor inputs.\n\n"
                            "```cpp\n"
                            "if (temperature > 30.0) {\n"
                            "  turnOnCooling();\n"
                            "} else {\n"
                            "  standby();\n"
                            "}\n"
                            "```\n\n"
                            "> **Common Mistake:** Using `=` (assignment) instead of `==` (comparison) or `>` / `<`. Single `=` sets a value, double `==` tests for equality.\n\n"
                            "> **Practice Challenge:** Complete the logic below to check if `temp` is greater than `30.0` degrees."
                        ),
                        "instructions": "Set the comparison operator and matching else branch.",
                        "template": (
                            "void checkTemp(float temp) {\n"
                            "  // Check if temp is greater than 30\n"
                            "  if (temp {{OPERATOR}} 30.0) {\n"
                            "    Serial.println(\"Too Hot!\");\n"
                            "  } {{ELSE_BRANCH}} {\n"
                            "    Serial.println(\"Normal\");\n"
                            "  }\n"
                            "}\n"
                        ),
                        "max_attempts": 3,
                        "blanks": [
                            {"token": "{{OPERATOR}}", "label": "Op", "validator_pattern": "^>$", "correct_answer": ">", "hint": "Use greater-than (>)."},
                            {"token": "{{ELSE_BRANCH}}", "label": "Branch", "validator_pattern": "^else$", "correct_answer": "else", "hint": "The fallback block is 'else'."},
                        ],
                    },
                },
                {
                    "title": "C++ Practice: Writing a Function",
                    "kind": "practice",
                    "content": {
                        "markdown": (
                            "## Writing Functions in C++\n\n"
                            "Functions group code into modular, reusable blocks. This keeps your program organized and avoids repeating the same code in multiple places.\n\n"
                            "```cpp\n"
                            "// Function definition taking one argument\n"
                            "void blinkLed(int delayTime) {\n"
                            "  digitalWrite(LED_BUILTIN, HIGH);\n"
                            "  delay(delayTime);\n"
                            "  digitalWrite(LED_BUILTIN, LOW);\n"
                            "  delay(delayTime);\n"
                            "}\n"
                            "```\n\n"
                            "> **Practice Challenge:** Define the function named `blinkLED` that takes an integer parameter named `delayTime`."
                        ),
                        "instructions": "Complete the function declaration with name and argument.",
                        "template": (
                            "// Define the function\n"
                            "void {{FUNC_NAME}}(int {{ARG_NAME}}) {\n"
                            "  digitalWrite(LED_BUILTIN, HIGH);\n"
                            "  delay({{ARG_NAME}});\n"
                            "  digitalWrite(LED_BUILTIN, LOW);\n"
                            "  delay({{ARG_NAME}});\n"
                            "}\n\n"
                            "void loop() {\n"
                            "  blinkLED(1000);\n"
                            "}\n"
                        ),
                        "max_attempts": 3,
                        "blanks": [
                            {"token": "{{FUNC_NAME}}", "label": "FuncName", "validator_pattern": "^blinkLED$", "correct_answer": "blinkLED", "hint": "The function name is blinkLED."},
                            {"token": "{{ARG_NAME}}", "label": "ArgName", "validator_pattern": "^delayTime$", "correct_answer": "delayTime", "hint": "The argument name is delayTime."},
                        ],
                    },
                },
            ],
        },

        # ── MODULE 2: COMMUNICATION PROTOCOLS & INTERACTIVE LABS ─────────────────
        {
            "title": "2. Communication Protocols & Interactive Labs",
            "items": [
                {
                    "title": "CAN Bus: Priority & Arbitration Lab",
                    "kind": "lab",
                    "content": {
                        "markdown": (
                            "## Controller Area Network (CAN)\n\n"
                            "The **Controller Area Network (CAN)** is an ultra-reliable, multi-master broadcast standard widely used in spacecraft avionics and automotive powertrains.\n\n"
                            "![CAN Bus Architecture](https://blog.seeedstudio.com/wp-content/uploads/2019/11/image-158.png)\n\n"
                            "### Key Principles of CAN in Space:\n"
                            "- **Differential Signaling:** Uses two complementary lines: **CAN_H** (High) and **CAN_L** (Low). The receiver measures the voltage differential (\\(V_{diff} = CAN_H - CAN_L\\)), making the bus virtually immune to severe electromagnetic noise.\n"
                            "- **120Ω Termination:** Both physical ends of the differential bus must be terminated with a **120Ω resistor** to eliminate high-frequency signal reflections.\n"
                            "- **Bitwise Arbitration:** When multiple subsystems attempt to transmit simultaneously, collision is resolved non-destructively: **dominant zero (0) bits overwrite recessive one (1) bits**. Therefore, packets with **lower numerical message IDs win priority**.\n\n"
                            "> **Interactive Lab:** Run the arbitration simulator below to observe how high-priority emergency packets override payload data."
                        ),
                        "instructions": "Explore CAN bus priority arbitration where lower numerical message IDs win the bus.",
                        "lab_type": "can",
                        "title": "CAN Bus Arbitration Simulator",
                        "config": {"bus_speed": "500 kbps"},
                    },
                },
                {
                    "title": "UART: Cross-Over Wiring Challenge",
                    "kind": "lab",
                    "content": {
                        "markdown": (
                            "## Universal Asynchronous Receiver-Transmitter (UART)\n\n"
                            "UART is a point-to-point, full-duplex serial protocol. Because it is **asynchronous**, there is no shared clock wire; both transmitter and receiver must agree on a synchronized **Baud Rate** (typically 115200 bps in SpacePoint avionics).\n\n"
                            "![UART Timing Diagram](https://vanhunteradams.com/Protocols/UART/uart_hardware.png)\n\n"
                            "### The Crossover Wiring Rule:\n"
                            "A common engineering error in satellite integration is wiring TX to TX. Remember:\n"
                            "- **MCU TX (Transmit)** must wire to **Peripheral RX (Receive)** (the speaker talks to the listener).\n"
                            "- **MCU RX (Receive)** must wire to **Peripheral TX (Transmit)** (the listener hears the speaker).\n"
                            "- **GND (Ground)** must always be connected to provide a shared 0V reference.\n\n"
                            "> **Interactive Lab:** Connect the ESP32 pins to the GPS Module below following the crossover rule to establish communications."
                        ),
                        "instructions": "Wire MCU TX to GPS RX, MCU RX to GPS TX, and GND to GND.",
                        "lab_type": "uart",
                        "title": "UART Cross-Over Wiring Lab",
                        "config": {
                            "left_name": "ESP32 MCU",
                            "left_pins": ["TX", "RX", "GND"],
                            "right_name": "GPS Module",
                            "right_pins": ["TX", "RX", "GND"],
                        },
                    },
                },
                {
                    "title": "I²C: Multi-Drop Avionics Bus Builder Lab",
                    "kind": "lab",
                    "content": {
                        "markdown": (
                            "## Inter-Integrated Circuit (I²C)\n\n"
                            "I²C is a synchronous, multi-drop serial bus invented by Philips. It allows one master (the ESP32) to query dozens of telemetry sensors using only **two physical wires**:\n\n"
                            "![I2C Data Transfer](https://www.analog.com/en/_/media/analog/en/landing-pages/technical-articles/i2c-primer-what-is-i2c-part-1-/36684.png?la=en&w=900)\n\n"
                            "- **SDA (Serial Data):** Bidirectional data carrier line.\n"
                            "- **SCL (Serial Clock):** Synchronous clock pulses driven by the Master.\n\n"
                            "### Hardware Bus Architecture:\n"
                            "1. **Open-Drain with Pull-ups:** Devices only pull lines LOW to 0V. External pull-up resistors (typically 4.7kΩ to 3.3V) pull the bus HIGH when idle.\n"
                            "2. **Unique 7-Bit Addresses:** Each peripheral device on the bus must hold a unique 7-bit hex address (e.g., `0x49` for TMP102, `0x50` for FRAM).\n\n"
                            "> **Interactive Lab:** Assemble the avionics bus below by adding the ESP32 Master controller and at least two unique telemetry sensors."
                        ),
                        "instructions": "Construct an I2C bus with 1 Master and at least 2 sensors.",
                        "lab_type": "i2c",
                        "title": "I²C Multi-Drop Bus Builder",
                        "config": {
                            "allowed_devices": [
                                "TMP102 Temp (0x49)",
                                "INA219 Power (0x40)",
                                "FRAM Storage (0x50)",
                                "OLED Display (0x3C)",
                                "MPU6050 IMU (0x68)",
                            ],
                            "max_devices": 5,
                        },
                    },
                },
                {
                    "title": "SPI: Synchronous Active-Low Chip Select Lab",
                    "kind": "lab",
                    "content": {
                        "markdown": (
                            "## Serial Peripheral Interface (SPI)\n\n"
                            "SPI is a high-speed, synchronous, full-duplex communication protocol capable of speeds up to 40+ MHz. It is ideal for high-bandwidth satellite payloads like mass storage flash and camera sensors.\n\n"
                            "![SPI Timing Diagram](https://upload.wikimedia.org/wikipedia/commons/thumb/6/6b/SPI_timing_diagram2.svg/800px-SPI_timing_diagram2.svg.png)\n\n"
                            "### 4-Wire Interface Architecture:\n"
                            "- **SCLK:** Serial Clock generated by the Master.\n"
                            "- **MOSI:** Master Out Slave In (data from ESP32 to device).\n"
                            "- **MISO:** Master In Slave Out (telemetry from device to ESP32).\n"
                            "- **SS / CS (Slave Select):** Dedicated active-low lines for each peripheral.\n\n"
                            "> **Active-Low Principle:** The Master pulls a device's SS line **LOW (0V)** to initiate communication. When SS is HIGH (3.3V), the peripheral disconnects its MISO pin into a high-impedance (floating) state to let other devices use the bus.\n\n"
                            "> **Interactive Lab:** Select a peripheral below to pull its Chip Select line LOW and observe the full-duplex clock synchronization."
                        ),
                        "instructions": "Toggle the active-low slave select line to clock data from a peripheral.",
                        "lab_type": "spi",
                        "title": "SPI Active-Low Chip Select Lab",
                        "config": {"slave_count": 3},
                    },
                },
            ],
        },

        # ── MODULE 3: COMMAND & DATA HANDLING (CDHS) SENSORS ─────────────────────
        {
            "title": "3. Command & Data Handling (CDHS) Sensors",
            "items": [
                {
                    "title": "TMP102 Digital Temperature Sensor Integration",
                    "kind": "practice",
                    "content": {
                        "markdown": (
                            "## TMP102 Digital Temperature Sensor\n\n"
                            "The **TMP102** is a high-accuracy, low-power digital temperature sensor communicating over I²C. On the SpacePoint CDHS board:\n\n"
                            "- **ESP32 Pins:** SDA = GPIO 21, SCL = GPIO 22\n"
                            "- **Temperature Register:** `0x00`\n"
                            "- **Base Address Configuration:** The address pin `ADD0` can be wired to four points:\n\n"
                            "| ADD0 Pin Connection | Binary Address | Hex Address | Used On Board |\n"
                            "| :--- | :--- | :--- | :--- |\n"
                            "| Tied to **GND** | `1001000` | `0x48` | Alternate |\n"
                            "| Tied to **V+** | `1001001` | **`0x49`** | **SpacePoint CDHS Board** |\n"
                            "| Tied to **SDA** | `1001010` | `0x4A` | Secondary Payload |\n"
                            "| Tied to **SCL** | `1001011` | `0x4B` | Battery Pack |\n\n"
                            "> **Flight Software Challenge:** Verify the SpacePoint address (`0x49`) in the dropdown, then write the code to begin transmission to the sensor and point to temperature register `0x00`."
                        ),
                        "instructions": "Select address 0x49 and complete the Wire transmission calls.",
                        "template": (
                            "#include <Wire.h>\n\n"
                            "void readTemperature() {\n"
                            "  // 1. Begin transmission to TMP102 sensor at 0x49\n"
                            "  Wire.beginTransmission({{I2C_ADDR}});\n\n"
                            "  // 2. Point to the temperature register (0x00)\n"
                            "  Wire.write({{REG_ADDR}});\n\n"
                            "  // 3. End transmission and request 2 bytes of data\n"
                            "  Wire.endTransmission();\n"
                            "  Wire.requestFrom({{I2C_ADDR}}, 2);\n"
                            "}\n"
                        ),
                        "max_attempts": 3,
                        "hardware_selector": {
                            "enabled": True,
                            "default_address": "0x49",
                            "addresses": ["0x48", "0x49", "0x4A", "0x4B"],
                        },
                        "blanks": [
                            {"token": "{{I2C_ADDR}}", "label": "Address", "validator_pattern": "^0x49$", "correct_answer": "0x49", "hint": "The SpacePoint TMP102 address is 0x49."},
                            {"token": "{{REG_ADDR}}", "label": "Register", "validator_pattern": "^(0x00|0)$", "correct_answer": "0x00", "hint": "Temperature register is 0x00."},
                        ],
                    },
                },
                {
                    "title": "FRAM Non-Volatile Telemetry Storage",
                    "kind": "practice",
                    "content": {
                        "markdown": (
                            "## Ferroelectric RAM (FRAM)\n\n"
                            "**FRAM** is non-volatile random-access memory that retains data without battery power. In space systems, FRAM is far superior to Flash or EEPROM:\n\n"
                            "- **Write Endurance:** \\(10^{14}\\) write cycles (virtually infinite compared to Flash's 10,000 cycles).\n"
                            "- **No Write Delays:** Data writes at full bus speed with zero page-buffer latency.\n"
                            "- **Radiation Immunity:** Highly resistant to gamma radiation and cosmic single-event upsets (SEU).\n\n"
                            "### SpacePoint CDHS Wiring:\n"
                            "| Pin Strapping (A0 / A1 / A2) | Binary Address | Hex Address | Assignment |\n"
                            "| :--- | :--- | :--- | :--- |\n"
                            "| **GND / GND / GND** | `1010000` | **`0x50`** | **SpacePoint CDHS Log** |\n"
                            "| V+ / GND / GND | `1010001` | `0x51` | Backup Log |\n"
                            "| GND / V+ / GND | `1010010` | `0x52` | Payload Cache |\n\n"
                            "> **Flight Software Challenge:** Open communication with the FRAM chip at `0x50` and write to memory address register `0x0000`."
                        ),
                        "instructions": "Transmit to FRAM at address 0x50 and target memory offset 0x00.",
                        "template": (
                            "#include <Wire.h>\n\n"
                            "void logFlightTelemetry(uint8_t statusByte) {\n"
                            "  // Begin transmission to FRAM chip at 0x50\n"
                            "  Wire.beginTransmission({{FRAM_ADDR}});\n\n"
                            "  // Target memory address 0x0000 (MSB, LSB)\n"
                            "  Wire.write({{ADDR_MSB}});\n"
                            "  Wire.write({{ADDR_LSB}});\n\n"
                            "  // Write the telemetry payload byte\n"
                            "  Wire.write(statusByte);\n"
                            "  Wire.endTransmission();\n"
                            "}\n"
                        ),
                        "max_attempts": 3,
                        "hardware_selector": {
                            "enabled": True,
                            "default_address": "0x50",
                            "addresses": ["0x50", "0x51", "0x52", "0x53"],
                        },
                        "blanks": [
                            {"token": "{{FRAM_ADDR}}", "label": "Address", "validator_pattern": "^0x50$", "correct_answer": "0x50", "hint": "Base FRAM address is 0x50."},
                            {"token": "{{ADDR_MSB}}", "label": "MSB", "validator_pattern": "^(0x00|0)$", "correct_answer": "0x00", "hint": "Memory address MSB is 0x00."},
                            {"token": "{{ADDR_LSB}}", "label": "LSB", "validator_pattern": "^(0x00|0)$", "correct_answer": "0x00", "hint": "Memory address LSB is 0x00."},
                        ],
                    },
                },
                {
                    "title": "INA219 Power & Current Telemetry",
                    "kind": "practice",
                    "content": {
                        "markdown": (
                            "## INA219 Voltage & Current Monitor\n\n"
                            "The **INA219** measures power consumption across the CubeSat Electrical Power System (EPS). By measuring voltage across a precision 0.1Ω shunt resistor, it calculates:\n\n"
                            "- **Bus Voltage:** The voltage supplying the onboard computer (3.3V nominal).\n"
                            "- **Shunt Voltage:** Small voltage drop across the shunt resistor.\n"
                            "- **Current (mA):** Total current drawn by satellite avionics.\n\n"
                            "### I²C Address Configuration:\n"
                            "| Pin Connection (A0 / A1) | Binary Address | Hex Address | Assignment |\n"
                            "| :--- | :--- | :--- | :--- |\n"
                            "| **GND / GND** | `1000000` | **`0x40`** | **SpacePoint EPS Monitor** |\n"
                            "| GND / V+ | `1000001` | `0x41` | Solar Panel 1 |\n"
                            "| GND / SDA | `1000100` | `0x44` | Solar Panel 2 |\n\n"
                            "> **Flight Software Challenge:** Initialize the INA219 sensor object with address `0x40` and call the driver to read the current in milliamps."
                        ),
                        "instructions": "Complete the sensor initialization and telemetry readout.",
                        "template": (
                            "#include <Adafruit_INA219.h>\n\n"
                            "// Instantiate monitor at address 0x40\n"
                            "Adafruit_INA219 ina219({{INA_ADDR}});\n\n"
                            "void readPowerTelemetry() {\n"
                            "  float current_mA = ina219.{{READ_FUNC}}();\n"
                            "  Serial.print(\"Current Draw: \");\n"
                            "  Serial.print(current_mA);\n"
                            "  Serial.println(\" mA\");\n"
                            "}\n"
                        ),
                        "max_attempts": 3,
                        "hardware_selector": {
                            "enabled": True,
                            "default_address": "0x40",
                            "addresses": ["0x40", "0x41", "0x44", "0x45"],
                        },
                        "blanks": [
                            {"token": "{{INA_ADDR}}", "label": "Address", "validator_pattern": "^0x40$", "correct_answer": "0x40", "hint": "Base INA219 address is 0x40."},
                            {"token": "{{READ_FUNC}}", "label": "Method", "validator_pattern": "^getCurrent_mA$", "correct_answer": "getCurrent_mA", "hint": "Use method getCurrent_mA."},
                        ],
                    },
                },
            ],
        },

        # ── MODULE 4: ATTITUDE DETERMINATION & CONTROL (ADCS) ────────────────────
        {
            "title": "4. Attitude Determination & Control (ADCS)",
            "items": [
                {
                    "title": "Reaction Wheel Motor Control (PWM)",
                    "kind": "practice",
                    "content": {
                        "markdown": (
                            "## Attitude Control with Reaction Wheels\n\n"
                            "Satellites change orientation in zero gravity by exchanging angular momentum with spinning flywheels called **Reaction Wheels**.\n\n"
                            "- To rotate the satellite clockwise, the motor accelerates the reaction wheel counter-clockwise (Newton's 3rd Law).\n"
                            "- Motor speed is governed by **Pulse Width Modulation (PWM)** via the ESP32's onboard **LEDC hardware timer**.\n\n"
                            "```cpp\n"
                            "// LEDC PWM Configuration\n"
                            "ledcAttachChannel(PWM_PIN, 5000, 8, PWM_CHANNEL);\n"
                            "ledcWrite(PWM_PIN, dutyCycle);\n"
                            "```\n\n"
                            "> **Challenge:** Configure PWM channel `0` at `5000` Hz with `8`-bit resolution (0-255 duty cycle) and spin the wheel at half power (`128`)."
                        ),
                        "instructions": "Set up 5000 Hz, 8-bit resolution PWM and assign half-power duty cycle (128).",
                        "template": (
                            "const int MOTOR_PIN = 18;\n"
                            "const int PWM_CHAN = 0;\n\n"
                            "void initReactionWheel() {\n"
                            "  // Configure 5000 Hz, 8-bit resolution (values 0-255)\n"
                            "  ledcAttachChannel(MOTOR_PIN, {{FREQ}}, {{RES_BITS}}, PWM_CHAN);\n"
                            "}\n\n"
                            "void setWheelSpeedHalfPower() {\n"
                            "  // 50% duty cycle on 8-bit counter is 128\n"
                            "  ledcWrite(MOTOR_PIN, {{DUTY_VAL}});\n"
                            "}\n"
                        ),
                        "max_attempts": 3,
                        "blanks": [
                            {"token": "{{FREQ}}", "label": "Freq Hz", "validator_pattern": "^5000$", "correct_answer": "5000", "hint": "PWM frequency is 5000 Hz."},
                            {"token": "{{RES_BITS}}", "label": "Bits", "validator_pattern": "^8$", "correct_answer": "8", "hint": "8-bit resolution (0-255)."},
                            {"token": "{{DUTY_VAL}}", "label": "Duty", "validator_pattern": "^128$", "correct_answer": "128", "hint": "Half power of 256 is 128."},
                        ],
                    },
                },
                {
                    "title": "MPU6050 6-Axis Gyroscope Telemetry",
                    "kind": "practice",
                    "content": {
                        "markdown": (
                            "## Inertial Measurement Units (IMU)\n\n"
                            "The **MPU6050** contains a 3-axis MEMS accelerometer and 3-axis gyroscope. In orbit:\n\n"
                            "- **Gyroscope (°/s):** Detects spacecraft angular tumbling rate during orbital deployment.\n"
                            "- **B-Dot Detumble Algorithm:** Flight software uses gyro rates to pulse magnetic torquer coils and arrest spin.\n"
                            "- **I²C Address:** `0x68` (or `0x69` if AD0 pin is pulled HIGH).\n\n"
                            "> **Flight Software Challenge:** Initiate I²C communication with the MPU6050 at `0x68` and request telemetry from accelerometer register `0x3B`."
                        ),
                        "instructions": "Address MPU6050 at 0x68 and query the accelerometer registers starting at 0x3B.",
                        "template": (
                            "#include <Wire.h>\n\n"
                            "void readGyroTelemetry() {\n"
                            "  // Begin communication with MPU6050 at 0x68\n"
                            "  Wire.beginTransmission({{IMU_ADDR}});\n\n"
                            "  // Point to register 0x3B (ACCEL_XOUT_H)\n"
                            "  Wire.write({{REG_START}});\n"
                            "  Wire.endTransmission(false);\n\n"
                            "  // Request 6 consecutive bytes (X, Y, Z raw registers)\n"
                            "  Wire.requestFrom({{IMU_ADDR}}, 6);\n"
                            "}\n"
                        ),
                        "max_attempts": 3,
                        "hardware_selector": {
                            "enabled": True,
                            "default_address": "0x68",
                            "addresses": ["0x68", "0x69"],
                        },
                        "blanks": [
                            {"token": "{{IMU_ADDR}}", "label": "Address", "validator_pattern": "^0x68$", "correct_answer": "0x68", "hint": "MPU6050 default I2C address is 0x68."},
                            {"token": "{{REG_START}}", "label": "Register", "validator_pattern": "^(0x3B|0x3b)$", "correct_answer": "0x3B", "hint": "Start register is 0x3B."},
                        ],
                    },
                },
            ],
        },
    ]

    for mod_idx, mod_def in enumerate(curriculum):
        # Find or create module
        mod_res = await db.execute(
            select(CourseModule).where(
                CourseModule.course_id == course.id,
                CourseModule.position == mod_idx,
            )
        )
        module = mod_res.scalar_one_or_none()

        if not module:
            module = CourseModule(
                id=uuid.uuid4(),
                course_id=course.id,
                title=mod_def["title"],
                position=mod_idx,
            )
            db.add(module)
            await db.flush()
            print(f"    [+] Created module: {module.title}")
        else:
            module.title = mod_def["title"]
            print(f"    [=] Updated module: {module.title}")

        # Delete old items in this module to re-seed cleanly
        await db.execute(delete(ModuleItem).where(ModuleItem.module_id == module.id))
        await db.flush()

        for item_idx, item_def in enumerate(mod_def["items"]):
            item = ModuleItem(
                id=uuid.uuid4(),
                module_id=module.id,
                position=item_idx,
                kind=item_def["kind"],
                title=item_def["title"],
                is_required=True,
                content=item_def["content"],
            )
            db.add(item)
            print(f"        [+] Added item ({item.kind}): {item.title}")

    if dry_run:
        print("\n[!] Dry run enabled: Rolling back all changes.")
        await db.rollback()
    else:
        await db.commit()
        print("\n[+] Success! Course and all composite lessons seeded successfully.")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Simulate without committing")
    args = parser.parse_args()

    engine = create_async_engine(settings.DATABASE_URL)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as db:
        await seed(db, dry_run=args.dry_run)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

# SpacePoint SatKit — Ground Station Hardware, Pinout & Connection Guide

This guide covers:
1. **Board Jumper Pins & I2C Addresses** across the SatKit stack (**CDHS Board V5**, **APC Board V5**, and **EPS Board V5**).
2. **Which Arduino `.ino` File to Load** onto the ESP32.
3. **How to Connect** to the Portal Ground Station using any of the **3 Supported Connection Methods** (USB Web Serial, SatKit Wi-Fi Hotspot, or Cloud HTTP / Simulator).

---

## 1. SatKit Hardware Pinout, Jumpers & I2C Addresses

All I2C sensors on the SatKit share the ESP32 I2C bus:
- **`SDA` = `GPIO 21`**
- **`SCL` = `GPIO 22`**
- **Hardware Watchdog (`MAX6369 WDI`) = `GPIO 4`** *(must be toggled every ~100 ms in `loop()`, otherwise the CDHS board resets itself every ~1.6 seconds)*

### Required Jumpers by Board & Socket

| Board & Socket | Module / Sensor | I2C Address | Required Jumper Caps / Pin Wiring |
| :--- | :--- | :--- | :--- |
| **CDHS Board V5** (`J122`, `J123`) | **ESP32 & 3.3V Sensor Rail Power** | — | Install jumper caps on **`J122` (`3V3_ESP32`)** and **`J123` (`5V_ESP32`)** (or turn the **EPS battery switch ON**). Without `J122`, the ESP32 boots over USB, but the 3.3V I2C sensors receive no power (`0 devices found`). |
| **CDHS Board V5** (`J5`) | **`INA219` Current & Voltage Sensor** | **`0x40`** | Close the 4 jumpers next to `J5`: **`J51` (`SCL`)**, **`J52` (`SDA`)**, **`J53` (`VIN+`)**, **`J54` (`VIN-`)**. Uses the **`R010` (`0.010 Ω`)** shunt resistor. |
| **CDHS Board V5** (`J3`) | **`MB85RC256V` 32 KB Non-Volatile FRAM** | **`0x50`** | Close the row of jumpers **`J31`–`J38`** next to `J3` (ties `A0`, `A1`, `A2`, `WP` to `GND` and connects `SDA`/`SCL`/`3V3`). |
| **CDHS Board V5** (`J4`) | **`TMP102` Temperature Sensor** | **`0x48`** or **`0x49`** | Close jumpers **`J41`–`J46`** next to `J4`. (`ADD0 → GND` gives **`0x48`**; `ADD0 → 3V3` gives **`0x49`**. The firmware auto-detects both). |
| **APC Board V5** (`J3` 10-pin) | **`MPU6050` 6-Axis IMU (Roll / Pitch / Yaw)** | **`0x68`** or **`0x69`** | Plug the `MPU6050` into the 10-pin header **`J3` on the APC Board**. Next to it is header **`J37` (`AD0` address pin)**:<br>• Connect **`J37` to `3V3`** → address **`0x69`**<br>• Connect **`J37` to `GND`** → address **`0x68`**<br>*(The firmware automatically detects both `0x68` and `0x69`).* |
| **EPS Board V5** | **18650 Battery Charger & 5V Boost (`J200`)** | — | **Red LED** = Charging via Micro-USB • **Blue LED** = Fully Charged • **White Slide Switch** = Turns battery output to the stack ON/OFF. |

---

## 2. Which Firmware File (`.ino`) to Load in Arduino IDE

The Portal Ground Station is backwards- and forwards-compatible with **all 3 SatKit sketches**—you do **not** have to rewrite student sketches for the dashboard to work:

| Sketch File | Where It Is | What It Supports |
| :--- | :--- | :--- |
| **1. `AlFalaj_SatKit_GroundStation.ino`** *(Recommended Universal SatKit Sketch)* | [ops/ground-station/firmware/cdhs_board.ino](file:///c:/Users/ahmed/Downloads/spaceportal/spacepoint-stripe-test/ops/ground-station/firmware/cdhs_board.ino) or downloadable inside the Portal Ground Station (**"1. SatKit Firmware (.ino)"**) | **USB Web Serial + SatKit Wi-Fi AP (`192.168.4.1`) + Embedded Offline SpacePoint Portal HTML Dashboard (`http://192.168.4.1/`)** simultaneously, zero external libraries required, auto-detects `0x40`, `0x50`, `0x48`/`0x49`, `0x68`/`0x69`, kicks watchdog on `GPIO 4`, and writes records to FRAM. |
| **2. `ground_station_usb_receiver.ino`** *(2nd Spare ESP32 Wireless Ground Station Dongle)* | [ops/ground-station/firmware/ground_station_usb_receiver.ino](file:///c:/Users/ahmed/Downloads/spaceportal/spacepoint-stripe-test/ops/ground-station/firmware/ground_station_usb_receiver.ino) or downloadable inside the Portal (**"2. Spare ESP32 USB Receiver (.ino)"**) | Flash onto a **2nd spare ESP32** plugged into laptop USB. It joins the SatKit's `ALFALAJ-SAT1` Wi-Fi wirelessly, polls `/api/telemetry` at 1 Hz, injects real wireless `RSSI (dBm)`, forwards downlink commands (`TAKE_PICTURE`, `SPIN_CW`, `STOP`, etc.), and streams JSON over USB to the Portal while the laptop stays on normal internet! |
| **3. `AlFalaj_CDHS.ino`** *(Wi-Fi Mission Console)* | Inside `AlFalaj_CDHS_WiFiHost.zip` (with `dashboard_gz.h` & `sim_frame.h`, `#define SIMULATE 0`) | Hosts Wi-Fi AP **`ALFALAJ-SAT1`** (password: `falaj2026`) and serves `/api/telemetry` and `/api/cmd` at `http://192.168.4.1`. Works out-of-the-box with both Method B (2nd ESP32 Receiver) and Method C (SatKit Wi-Fi Direct). |
| **4. `AlFalaj_Sensors.ino`** | Standalone sensor test sketch | Streams telemetry over **USB Serial (115200 baud)** (`T ... C \| ... V ... mA \| roll ... pitch ...` text format) plus Wi-Fi `/data`. |

### Flashing Steps in Arduino IDE
1. Open Arduino IDE and load your chosen `.ino` file.
2. Go to **Tools → Board** and select **`ESP32 Dev Module`**.
3. Go to **Tools → Port** and select your SatKit COM port (e.g. **`COM5` / `USB-SERIAL CH340`**).
4. Click **Upload (→)** and wait for `Hard resetting via RTS pin...`.
5. **Important:** If you are connecting via USB in the browser, **close the Arduino IDE Serial Monitor** after uploading so Chrome/Edge can access the COM port.

---

## 3. Connecting to the Portal Ground Station (4 Methods)

Open the Ground Station mission page in **Google Chrome** or **Microsoft Edge** (`/learn/missions/ground-station/<attemptId>`):

### Method A: Direct USB Cable via Web Serial (`Detect USB Port`)
1. Keep your laptop connected to your regular classroom/home Wi-Fi so the portal has live internet access.
2. Plug the SatKit ESP32 into your laptop via USB (and make sure Arduino Serial Monitor is closed).
3. On the Ground Station toolbar, click **`Detect USB Port`** and choose **`USB-SERIAL CH340 (COMx)`**.
4. The status badge turns **`Live`**, the 6 telemetry trend charts and **3D Attitude Cube** update every second, and every frame is persisted to the cloud database.

### Method B: 2-ESP32 Wireless Ground Station Bridge *(Untethered SatKit + Full Laptop Internet!)*
1. Leave the **SatKit (ESP32 #1)** running untethered on its EPS battery (with `AlFalaj_CDHS.ino` or `cdhs_board.ino` broadcasting **`ALFALAJ-SAT1`**, password `falaj2026`).
2. Flash [ground_station_usb_receiver.ino](file:///c:/Users/ahmed/Downloads/spaceportal/spacepoint-stripe-test/ops/ground-station/firmware/ground_station_usb_receiver.ino) onto a **2nd spare ESP32** and keep that spare ESP32 plugged into your laptop's USB port.
3. Keep your laptop connected to your normal classroom/home Wi-Fi (so the Portal has full internet and never breaks on page refresh).
4. In the Portal Ground Station, click **`Detect USB Port`** and select the **2nd spare ESP32's COM port**:
   - The spare ESP32 connects wirelessly to `ALFALAJ-SAT1`, polls `http://192.168.4.1/api/telemetry` every second, injects the real wireless **`Signal RSSI (dBm)`**, and pipes the JSON over USB into the Portal.
   - Any command clicked in the Portal Command Console (`TAKE_PICTURE`, `SPIN_CW`, `SPIN_CCW`, `STOP`, `FAKE`, `GET_STATUS`) is sent over USB to the spare ESP32 and forwarded wirelessly to `http://192.168.4.1/api/cmd` on the SatKit.

### Method C: SatKit Wi-Fi Hotspot (`SatKit Wi-Fi (192.168.4.1)`) & Embedded Offline HTML Console
1. Switch your laptop's Wi-Fi network to **`ALFALAJ-SAT1`** (password: **`falaj2026`**).
2. **Option C1 — Portal Offline Mode:** If you opened the Portal Ground Station page before switching Wi-Fi, click **`SatKit Wi-Fi (192.168.4.1)`** on the toolbar. All 6 live charts, the 3D Attitude Cube, and the Command Console update live (`Live (Local SatKit)`), while frames queue in `localStorage` (`N queued offline`) and auto-sync to the cloud when you return to normal internet.
3. **Option C2 — Embedded Offline HTML Console (Survives Refreshes Without Internet):** If you are loaded with `AlFalaj_SatKit_GroundStation.ino` ([cdhs_board.ino](file:///c:/Users/ahmed/Downloads/spaceportal/spacepoint-stripe-test/ops/ground-station/firmware/cdhs_board.ino)) or `AlFalaj_CDHS.ino`, simply open **`http://192.168.4.1/`** in any browser to view the self-contained HTML dashboard hosted directly by the ESP32.

### Method D: Cloud HTTP Ingest / Built-in Simulator (`Sim`)
- **Simulator:** Click **`Sim`** on the toolbar to stream synthetic orbital telemetry (`temp`, `voltage`, `current`, `power`, `pitch`, `roll`, `yaw`, `lat`, `lon`, `alt`) immediately without hardware.
- **Direct HTTP POST:** Any ESP32 or script on Wi-Fi can `POST` either flat JSON or nested `AlFalaj_CDHS` JSON directly to:
  ```http
  POST /api/ground-station/devices/{device_id}/telemetry
  Content-Type: application/json
  ```

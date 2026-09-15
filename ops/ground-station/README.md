# Ground Station

Live CubeSat telemetry/command tool, ported from the legacy Madar
platform's `LoRa-Dashboard-V3`. Backend routes live in
`backend/app/routers/ground_station/`; the frontend page is
`frontend/src/pages/ground-station/GroundStationPage.tsx`.

## What's in this directory

- `firmware/` — three different rigs, not one:
  - `cdhs_board.ino` — the **real direct-USB rig** (Web Serial connects to
    this one): ESP32 + TMP102 (temp, I2C 0x49) + INA219 (current/voltage,
    I2C 0x40) + MPU6050 (orientation, I2C 0x68), matching the SpacePoint
    curriculum (`spacepoint-software-guide`'s CDHS/ADCS modules) — students
    wire these parts up and write this code themselves as coursework; this
    file is the working reference version. Prints bare JSON, no agent
    needed.
  - `webserial_test.ino` — no sensors at all, just prints synthetic
    telemetry in the same JSON shape. Use this to prove the USB → browser →
    console pipeline works before debugging real sensor wiring.
  - `ground_station.ino` / `satellite_board.ino` / `adcs.ino` — the legacy
    LoRa-relay path (a separate Heltec LoRa satellite board talking over
    RF to a separate LoRa+WiFi+MQTT gateway board). Carried over as-is for
    reference; these do **not** work with Web Serial — they need the
    on-site agent's MQTT path below.
- `agent/` — the on-site bridge (`agent.py`), adapted from the legacy
  `local_bridge.py`. **Runs on the physical machine next to the hardware —
  it is NOT part of `docker-compose.dev.yml` and does NOT run on the VPS.**
  The cloud API has no serial port; this script is what actually talks to
  the rig and forwards data up over plain authenticated HTTPS (or MQTT, for
  the LoRa gateway path).

## Setup

1. Flash the firmware in `firmware/` onto the ground station radio and
   satellite/ADCS boards, same as before.
2. Ask staff (an `operations`/`admin` account) to register a device:
   `POST /ground-station/admin/devices {"label": "Lab Rig 1"}` — this
   returns a device id and a secret, shown once.
3. Copy `agent/.env.example` to `agent/.env`, fill in the API base URL and
   the device id/secret from step 2, and the serial port the rig is on.
4. `pip install -r agent/requirements.txt`
5. `python agent/agent.py` (real hardware) or `python agent/agent.py --simulate`
   (no hardware attached — synthetic telemetry, same shape as the legacy
   app's built-in simulator, so the dashboard works identically for a demo).

## Why this isn't in docker-compose

Production for this platform is a VPS running the `api`/`worker` containers
(see `docs/HANDOFF_VPS_DEPLOYMENT.md`) — there's no physical serial port
there to read. The agent is meant to run wherever the actual hardware is
(a lab machine, a Raspberry Pi next to the rig), pointed at the deployed
API over the network.

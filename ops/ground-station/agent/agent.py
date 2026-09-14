#!/usr/bin/env python3
"""Ground Station on-site bridge — adapted from the legacy Madar platform's
`local_bridge.py`. Runs on the physical machine next to the hardware (NOT
in docker-compose.dev.yml, NOT on the VPS — there is no serial port there).

Same job as the legacy bridge: read the rig's serial output, forward it to
the cloud API, and write queued commands back down to the rig. The only
thing that changed is the transport — plain authenticated HTTPS against this
platform's own `/ground-station/devices/{id}/*` endpoints instead of a
Socket.IO client against a Render-hosted Flask app.

Usage:
    python agent.py                  # real hardware via serial
    python agent.py --simulate       # no hardware — synthetic telemetry,
                                      # same shape the legacy sim_worker sent

Configure via ground-station-agent.env (see .env.example in this directory).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import threading
import time
from datetime import datetime, timezone

import requests

try:
    import serial  # pyserial
except ImportError:  # not needed in --simulate mode
    serial = None

try:
    import paho.mqtt.client as mqtt  # optional — only needed if MQTT_BROKER is set
except ImportError:
    mqtt = None


def _env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)


API_BASE_URL = _env("GROUND_STATION_API_BASE_URL", "http://localhost:8000")
DEVICE_ID = _env("GROUND_STATION_DEVICE_ID")
DEVICE_SECRET = _env("GROUND_STATION_DEVICE_SECRET")
SERIAL_PORT = _env("GROUND_STATION_SERIAL_PORT", "/dev/ttyUSB0")
SERIAL_BAUD = int(_env("GROUND_STATION_SERIAL_BAUD", "115200"))
COMMAND_POLL_SECONDS = float(_env("GROUND_STATION_COMMAND_POLL_SECONDS", "1.0"))

# MQTT — optional secondary telemetry source / command fallback, same
# broker/topic scheme as the legacy app (backend/serial_reader.py):
# `{prefix}/telemetry/#` inbound, `{prefix}/command/{device}` outbound.
MQTT_BROKER = _env("GROUND_STATION_MQTT_BROKER")
MQTT_PORT = int(_env("GROUND_STATION_MQTT_PORT", "1883"))
MQTT_TOPIC_PREFIX = _env("GROUND_STATION_MQTT_TOPIC_PREFIX", "sat_dash")

_HEADERS = {"X-Device-Secret": DEVICE_SECRET or ""}


def _require_config() -> None:
    missing = [n for n, v in [
        ("GROUND_STATION_DEVICE_ID", DEVICE_ID), ("GROUND_STATION_DEVICE_SECRET", DEVICE_SECRET),
    ] if not v]
    if missing:
        raise SystemExit(
            f"Missing required env var(s): {', '.join(missing)}. "
            "Register a device via POST /ground-station/admin/devices and set these."
        )


def send_telemetry(data: dict) -> None:
    url = f"{API_BASE_URL}/ground-station/devices/{DEVICE_ID}/telemetry"
    try:
        resp = requests.post(url, json={"data": data}, headers=_HEADERS, timeout=5)
        if resp.status_code >= 400:
            print(f"[!] Telemetry rejected ({resp.status_code}): {resp.text[:200]}")
    except requests.RequestException as exc:
        print(f"[!] Telemetry POST failed: {exc}")


def ack_command(command_id: str, ok: bool, detail: str = "") -> None:
    url = f"{API_BASE_URL}/ground-station/devices/{DEVICE_ID}/commands/{command_id}/ack"
    try:
        requests.post(url, json={"ok": ok, "detail": detail}, headers=_HEADERS, timeout=5)
    except requests.RequestException as exc:
        print(f"[!] Command ack failed: {exc}")


def poll_commands_loop(write_to_hardware) -> None:
    url = f"{API_BASE_URL}/ground-station/devices/{DEVICE_ID}/commands/pending"
    while True:
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=5)
            if resp.ok:
                for cmd in resp.json().get("commands", []):
                    line = cmd["name"] if not cmd.get("arg") else f"{cmd['name']} {cmd['arg']}"
                    print(f"[CLOUD -> HW] {line}")
                    ok = write_to_hardware(line)
                    ack_command(cmd["id"], ok)
        except requests.RequestException as exc:
            print(f"[!] Command poll failed: {exc}")
        time.sleep(COMMAND_POLL_SECONDS)


# ------------------------------------------------------------------- mqtt --

_mqtt_client = None  # module-level so write_to_hardware's MQTT fallback can reach it


def start_mqtt() -> None:
    """Background MQTT telemetry listener + command-publish path — runs
    alongside serial/simulate, same dual-source design as the legacy app's
    simultaneous serial+WiFi bridge threads."""
    global _mqtt_client
    if not MQTT_BROKER:
        return
    if mqtt is None:
        print("[!] GROUND_STATION_MQTT_BROKER is set but paho-mqtt is not installed — "
              "pip install -r requirements.txt")
        return

    def on_connect(client, userdata, flags, rc, properties=None):
        if rc == 0:
            print(f"[MQTT] Connected to {MQTT_BROKER}:{MQTT_PORT}")
            client.subscribe(f"{MQTT_TOPIC_PREFIX}/telemetry/#")
        else:
            print(f"[!] MQTT connect failed, rc={rc}")

    def on_message(client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode("utf-8", errors="ignore"))
        except json.JSONDecodeError:
            data = {"raw_line": msg.payload.decode("utf-8", errors="ignore")}
        send_telemetry(data)

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.connect_async(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
        _mqtt_client = client
        print(f"[MQTT] Connecting to {MQTT_BROKER}:{MQTT_PORT}...")
    except Exception as exc:
        print(f"[!] MQTT setup error: {exc}")


def mqtt_publish_command(line: str) -> bool:
    if _mqtt_client is None:
        return False
    try:
        _mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/command/{DEVICE_ID}", line, qos=1)
        print(f"[CLOUD -> MQTT TX] {line}")
        return True
    except Exception as exc:
        print(f"[!] MQTT publish failed: {exc}")
        return False


# ---------------------------------------------------------------- hardware --

def _open_serial():
    if serial is None:
        raise SystemExit("pyserial is not installed — pip install -r requirements.txt")
    try:
        conn = serial.Serial(SERIAL_PORT, SERIAL_BAUD, timeout=1)
        print(f"[SERIAL] Connected to {SERIAL_PORT} @ {SERIAL_BAUD}")
        return conn
    except Exception as exc:
        raise SystemExit(f"[!] Could not open serial port {SERIAL_PORT}: {exc}")


def run_hardware(conn) -> None:
    def write_to_hardware(line: str) -> bool:
        try:
            conn.write(f"{line}\n".encode("utf-8"))
            return True
        except Exception as exc:
            print(f"[!] Serial write failed: {exc}")
            # Priority 2 fallback, same order as the legacy app: MQTT relay
            # when the direct serial link can't take the command.
            return mqtt_publish_command(line)

    threading.Thread(target=poll_commands_loop, args=(write_to_hardware,), daemon=True).start()

    print(f"[SERIAL] Monitoring {SERIAL_PORT}...")
    while True:
        try:
            raw = conn.readline().decode("utf-8", errors="ignore").strip()
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = {"raw_line": raw}
            send_telemetry(data)
        except Exception as exc:
            print(f"[!] Serial read error: {exc}")
            time.sleep(2)


# ---------------------------------------------------------------- simulate --

def run_simulation() -> None:
    """Same telemetry shape as the legacy app's built-in sim_worker
    (serial_reader.py), so the rest of the pipeline (frontend charts,
    attitude view) needs zero changes to work without hardware attached."""

    def write_to_hardware(line: str) -> bool:
        print(f"[SIM] (no real hardware) would send: {line}")
        return True

    threading.Thread(target=poll_commands_loop, args=(write_to_hardware,), daemon=True).start()

    print("[SIM] Simulated telemetry started (Ctrl+C to stop)")
    t = 0
    while True:
        temp = round(25 + 5 * math.sin(t * 0.1) + random.uniform(-0.5, 0.5), 2)
        voltage = round(3.7 + 0.5 * math.sin(t * 0.01), 2)
        current = round(0.5 + random.uniform(0, 0.1), 2)
        power = round(voltage * current * 1000, 2)
        send_telemetry({
            "temp": temp, "voltage": voltage, "current": current, "power": power,
            "rssi": int(-90 + random.uniform(-10, 20)), "snr": round(8 + random.uniform(-2, 4), 1),
            "uptime": t, "baud_rate": 7, "freq": 868.1,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        })
        t += 1
        time.sleep(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulate", action="store_true", help="Run without real hardware attached")
    args = parser.parse_args()

    _require_config()
    print("=" * 60)
    print(" Ground Station bridge")
    print(f" API: {API_BASE_URL}  Device: {DEVICE_ID}")
    print("=" * 60)

    start_mqtt()

    if args.simulate:
        run_simulation()
    else:
        run_hardware(_open_serial())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting Ground Station bridge...")

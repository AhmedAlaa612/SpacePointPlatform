/* SpacePoint Ground Station — Wireless USB Receiver Dongle (2nd ESP32)
 *
 * HOW THIS WORKS (2-ESP32 Setup):
 *   - ESP32 #1 (SatKit CubeSat): Runs on its battery completely untethered,
 *     hosting the "ALFALAJ-SAT1" Wi-Fi hotspot (AlFalaj_CDHS.ino, AlFalaj_Sensors.ino,
 *     or cdhs_board.ino). ZERO changes needed on the SatKit!
 *   - ESP32 #2 (This Spare ESP32): Plugged into your laptop's USB port.
 *     It joins "ALFALAJ-SAT1" over Wi-Fi, polls http://192.168.4.1/api/telemetry
 *     (or /data) once per second, injects the real wireless signal strength
 *     (WiFi.RSSI() in dBm), and prints the JSON line over USB Serial (115200 baud)
 *     straight into the SpacePoint Portal Ground Station ("Detect USB Port").
 *   - Bidirectional Commands: When you click PING, GET_STATUS, FAKE, TAKE_PICTURE,
 *     SPIN_CW, SPIN_CCW, or STOP in the Portal Command Console, the Portal writes
 *     "CMD <NAME>" over USB to this receiver ESP32, which forwards it over Wi-Fi
 *     to http://192.168.4.1/api/cmd on the SatKit!
 *
 * WHY THIS IS IDEAL:
 *   - The SatKit CubeSat is 100% wireless (students can tilt/spin it in their hands).
 *   - Your laptop stays connected to your normal home/classroom Wi-Fi with full internet,
 *     so refreshing the SpacePoint Portal never drops the page!
 *   - The "Signal RSSI (dBm)" chart in the Portal shows the real wireless link strength
 *     between the SatKit and this Ground Station receiver ESP32.
 *
 * Board: ESP32 Dev Module (115200 baud)
 * Libraries needed: NONE (uses built-in ESP32 WiFi & HTTPClient)
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include "soc/rtc_cntl_reg.h"

const char* SAT_SSID = "ALFALAJ-SAT1";
const char* SAT_PASS = "falaj2026";
const char* SAT_HOST = "http://192.168.4.1";

unsigned long lastPoll = 0;
unsigned long lastReconnect = 0;
String cmdBuffer;

void ensureSatWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  unsigned long now = millis();
  if (now - lastReconnect < 3000) return;
  lastReconnect = now;
  WiFi.disconnect();
  WiFi.begin(SAT_SSID, SAT_PASS);
}

void forwardCommandToSatKit(String cmd) {
  cmd.trim();
  int space = cmd.indexOf(' ');
  String name = (space < 0) ? cmd : cmd.substring(0, space);
  name.toUpperCase();

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[GND-RX] SatKit Wi-Fi not connected yet");
    return;
  }

  String path = "/api/telemetry";
  if (name == "TAKE_PICTURE") path = "/api/cmd?capture=1";
  else if (name == "SPIN_CW") path = "/api/cmd?wz=180";
  else if (name == "SPIN_CCW") path = "/api/cmd?wz=-180";
  else if (name == "STOP") path = "/api/cmd?adcs=OFF";
  else if (name == "FAKE") path = "/api/cmd?mode=SIM";
  else if (name == "GET_STATUS" || name == "PING") {
    lastPoll = 0; // trigger immediate telemetry fetch
    return;
  }

  HTTPClient http;
  http.setTimeout(1200);
  if (http.begin(String(SAT_HOST) + path)) {
    int code = http.GET();
    Serial.printf("[GND-RX] Forwarded %s -> HTTP %d\n", name.c_str(), code);
    http.end();
  }
}

void pollCommandsFromUsb() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      cmdBuffer.trim();
      if (cmdBuffer.startsWith("CMD ")) {
        forwardCommandToSatKit(cmdBuffer.substring(4));
      }
      cmdBuffer = "";
    } else if (c != '\r') {
      cmdBuffer += c;
    }
  }
}

void pollSatKitTelemetry() {
  if (WiFi.status() != WL_CONNECTED) return;

  int rssi = WiFi.RSSI();
  const char* paths[] = { "/api/telemetry", "/data" };

  for (int i = 0; i < 2; i++) {
    HTTPClient http;
    http.setTimeout(800);
    if (!http.begin(String(SAT_HOST) + paths[i])) continue;
    int code = http.GET();
    if (code == 200) {
      String body = http.getString();
      http.end();
      body.trim();
      if (body.startsWith("{") && body.endsWith("}")) {
        // Replace `"rssi":0` (from AlFalaj_CDHS.ino AP mode) or append real receiver RSSI
        int rssiIdx = body.indexOf("\"rssi\":0");
        if (rssiIdx >= 0) {
          body = body.substring(0, rssiIdx) + "\"rssi\":" + String(rssi) + body.substring(rssiIdx + 8);
        } else if (body.indexOf("\"rssi\":") < 0) {
          body = body.substring(0, body.length() - 1) + ",\"rssi\":" + String(rssi) + "}";
        }
        // Print one single-line JSON frame over USB Serial to the Portal
        body.replace("\r", "");
        body.replace("\n", "");
        Serial.println(body);
        return;
      }
    } else {
      http.end();
    }
  }
}

void setup() {
  Serial.begin(115200);
  WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(SAT_SSID, SAT_PASS);
  Serial.println("[GND-RX] Ground Station USB Receiver starting — looking for ALFALAJ-SAT1...");
}

void loop() {
  pollCommandsFromUsb();
  ensureSatWifi();

  unsigned long now = millis();
  if (now - lastPoll >= 1000) {
    lastPoll = now;
    pollSatKitTelemetry();
  }
}

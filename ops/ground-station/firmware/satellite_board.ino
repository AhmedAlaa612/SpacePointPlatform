// ============================================================
//  SATELLITE BOARD — Heltec WiFi LoRa 32 (v2 / v3)
//  Sends telemetry JSON via LoRa RF every 2 seconds.
//  No WiFi needed on this board.
//
//  ★ CONFIGURE THE SECTION BELOW BEFORE FLASHING ★
// ============================================================

// ---------- USER CONFIG ----------
#define BAND          868E6   // 868E6 = EU | 915E6 = US/AU
#define DEVICE_ID     "Sat_1"
#define DEST_ID       "Station_01"
#define TX_INTERVAL   2000    // ms between packets

// LoRa radio parameters — MUST match ground station
#define LORA_SF       7       // Spreading Factor (7–12)
#define LORA_BW       125E3   // Bandwidth Hz
#define LORA_CR       5       // Coding Rate denominator (5 = 4/5)
#define LORA_SYNC     0x12    // Private network sync word
// ---------------------------------

// Board detection: define HELTEC_V3 in board settings if using v3
#ifdef HELTEC_V3
  #include "HeltecLib.h"      // v3 uses new library
#else
  #include "heltec.h"         // v2 classic library
#endif

#include <ArduinoJson.h>

// ---------- STATE ----------
unsigned long uptime_sec = 0;
unsigned long last_tx    = 0;
int pkt_count            = 0;

// ----- Simulated Sensor Readings -----
// Replace these functions with real sensor reads if you have
// an INA219 (power) or DS18B20 / SHT31 (temperature) wired up.
float readTemp()    { return 24.5f + (random(-15, 15) * 0.1f); }
float readVoltage() { return 3.70f + (random(-5,  5)  * 0.01f); }
float readCurrent() { return 0.50f + (random(0,  10)  * 0.01f); }

void setup() {
  Serial.begin(115200);

#ifdef HELTEC_V3
  heltec_setup();
#else
  Heltec.begin(
    true  /* OLED   */,
    true  /* LoRa   */,
    true  /* Serial */,
    true  /* PABOOST*/,
    BAND
  );
#endif

  // Fine-tune radio params
  LoRa.setSpreadingFactor(LORA_SF);
  LoRa.setSignalBandwidth(LORA_BW);
  LoRa.setCodingRate4(LORA_CR);
  LoRa.setSyncWord(LORA_SYNC);

  Serial.println("[SAT] Satellite board ready. Transmitting on " + String(BAND / 1E6) + " MHz");

#ifndef HELTEC_V3
  Heltec.display->clear();
  Heltec.display->setFont(ArialMT_Plain_10);
  Heltec.display->drawString(0, 0, "SAT Board Ready");
  Heltec.display->drawString(0, 12, String(BAND / 1E6) + " MHz");
  Heltec.display->display();
#endif
}

void loop() {
  unsigned long now = millis();

  if (now - last_tx >= TX_INTERVAL) {
    last_tx   = now;
    uptime_sec += (TX_INTERVAL / 1000);
    pkt_count++;

    float volt = readVoltage();
    float curr = readCurrent();
    float temp = readTemp();
    float pwr  = volt * curr * 1000.0f;  // mW

    // Build JSON payload
    StaticJsonDocument<256> doc;
    doc["src"]       = DEVICE_ID;
    doc["dst"]       = DEST_ID;
    doc["type"]      = "telemetry";
    doc["timestamp"] = 0;  // backend will stamp with real Unix time

    JsonObject data = doc.createNestedObject("data");
    data["temp"]      = round(temp    * 100) / 100.0;
    data["voltage"]   = round(volt    * 1000) / 1000.0;
    data["current"]   = round(curr    * 1000) / 1000.0;
    data["power"]     = round(pwr     * 10)   / 10.0;
    data["uptime"]    = uptime_sec;
    data["baud_rate"] = 7;
    data["freq"]      = BAND / 1E6;

    String payload;
    serializeJson(doc, payload);

    // Transmit
    LoRa.beginPacket();
    LoRa.print(payload);
    int ret = LoRa.endPacket();

    if (ret) {
      Serial.println("[SAT] TX #" + String(pkt_count) + " OK | " + payload);
    } else {
      Serial.println("[SAT] TX FAILED");
    }

#ifndef HELTEC_V3
    // Update OLED
    Heltec.display->clear();
    Heltec.display->drawString(0, 0,  "TX #" + String(pkt_count));
    Heltec.display->drawString(0, 12, "T:" + String(temp, 1) + "C  V:" + String(volt, 2) + "V");
    Heltec.display->drawString(0, 24, "P:" + String(pwr, 0) + "mW");
    Heltec.display->display();
#endif
  }
}

// ============================================================
//  GROUND STATION BOARD — Heltec WiFi LoRa 32 (v2 / v3)
//  Receives LoRa packets from Satellite, publishes to MQTT.
//  Also forwards downlink commands from MQTT via LoRa.
//
//  ★ CONFIGURE THE SECTION BELOW BEFORE FLASHING ★
// ============================================================

// ---------- USER CONFIG ----------
#define WIFI_SSID     "YOUR_WIFI_SSID"      // <-- change this
#define WIFI_PASS     "YOUR_WIFI_PASSWORD"   // <-- change this
#define MQTT_HOST     "192.168.1.100"        // <-- your PC's LAN IP (run ipconfig)
#define MQTT_PORT     1883
#define CLIENT_ID     "LoRa_GND_Station"

// MQTT Topics (must match backend MQTT_TOPIC_PREFIX = "sat")
#define TOPIC_TELEM   "sat/telemetry/Sat_1"
#define TOPIC_CMD_SUB "sat/command/Sat_1"    // commands to forward via LoRa

// LoRa radio params — MUST match satellite board exactly
#define BAND      868E6    // 868E6 = EU | 915E6 = US/AU
#define LORA_SF   7
#define LORA_BW   125E3
#define LORA_CR   5
#define LORA_SYNC 0x12
// ---------------------------------

#ifdef HELTEC_V3
  #include "HeltecLib.h"
#else
  #include "heltec.h"
#endif

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

WiFiClient   wifiClient;
PubSubClient mqtt(wifiClient);

unsigned long last_reconnect = 0;
int           rx_count       = 0;

// ---------- WiFi ----------
void connectWiFi() {
  Serial.print("[WiFi] Connecting to ");
  Serial.println(WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 15000) {
    delay(500);
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WiFi] Connected! IP: " + WiFi.localIP().toString());
  } else {
    Serial.println("\n[WiFi] FAILED — check SSID/password");
  }
}

// ---------- MQTT Callbacks ----------
void onMqttMessage(char* topic, byte* payload, unsigned int length) {
  // Received a downlink command from the dashboard → forward via LoRa
  String msg = "";
  for (unsigned int i = 0; i < length; i++) msg += (char)payload[i];

  Serial.println("[MQTT] CMD received → forwarding via LoRa: " + msg);

  LoRa.beginPacket();
  LoRa.print(msg);
  LoRa.endPacket();

#ifndef HELTEC_V3
  Heltec.display->clear();
  Heltec.display->drawString(0, 48, "CMD TX: " + msg.substring(0, 20));
  Heltec.display->display();
#endif
}

bool reconnectMQTT() {
  if (WiFi.status() != WL_CONNECTED) connectWiFi();
  if (WiFi.status() != WL_CONNECTED) return false;

  Serial.print("[MQTT] Connecting to " + String(MQTT_HOST) + "...");
  if (mqtt.connect(CLIENT_ID)) {
    Serial.println(" OK");
    mqtt.subscribe(TOPIC_CMD_SUB);
    Serial.println("[MQTT] Subscribed to " + String(TOPIC_CMD_SUB));
    return true;
  }
  Serial.println(" FAILED, rc=" + String(mqtt.state()));
  return false;
}

// ---------- Setup ----------
void setup() {
  Serial.begin(115200);

#ifdef HELTEC_V3
  heltec_setup();
#else
  Heltec.begin(true, true, true, true, BAND);
#endif

  LoRa.setSpreadingFactor(LORA_SF);
  LoRa.setSignalBandwidth(LORA_BW);
  LoRa.setCodingRate4(LORA_CR);
  LoRa.setSyncWord(LORA_SYNC);

  connectWiFi();

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMqttMessage);
  mqtt.setBufferSize(512);  // allow larger JSON payloads

  reconnectMQTT();

  Serial.println("[GND] Ground station ready. Listening on " + String(BAND / 1E6) + " MHz");

#ifndef HELTEC_V3
  Heltec.display->clear();
  Heltec.display->setFont(ArialMT_Plain_10);
  Heltec.display->drawString(0, 0,  "GND Station Ready");
  Heltec.display->drawString(0, 12, String(BAND / 1E6) + " MHz");
  Heltec.display->drawString(0, 24, WiFi.localIP().toString());
  Heltec.display->display();
#endif
}

// ---------- Loop ----------
void loop() {
  // Keep MQTT alive
  if (!mqtt.connected()) {
    unsigned long now = millis();
    if (now - last_reconnect > 5000) {
      last_reconnect = now;
      reconnectMQTT();
    }
  } else {
    mqtt.loop();
  }

  // Check for incoming LoRa packet
  int pktSize = LoRa.parsePacket();
  if (pktSize > 0) {
    String received = "";
    while (LoRa.available()) {
      received += (char)LoRa.read();
    }
    int rssi = LoRa.packetRssi();
    float snr = LoRa.packetSnr();

    Serial.println("[LoRa] RX (" + String(pktSize) + "B) RSSI:" + String(rssi) + " SNR:" + String(snr, 1));
    Serial.println("       " + received);

    // Parse and inject actual RSSI/SNR from the receiver
    StaticJsonDocument<512> doc;
    DeserializationError err = deserializeJson(doc, received);

    String mqttPayload;
    if (!err) {
      // Update RSSI and SNR with the ground-station-measured values
      if (doc.containsKey("data")) {
        doc["data"]["rssi"] = rssi;
        doc["data"]["snr"]  = snr;
      }
      serializeJson(doc, mqttPayload);
    } else {
      // Not valid JSON — forward raw anyway
      mqttPayload = received;
    }

    // Publish to MQTT
    if (mqtt.connected()) {
      bool ok = mqtt.publish(TOPIC_TELEM, mqttPayload.c_str(), false);
      rx_count++;
      Serial.println("[MQTT] Published to " + String(TOPIC_TELEM) + (ok ? " OK" : " FAIL"));
    } else {
      Serial.println("[MQTT] Not connected — packet dropped");
    }

#ifndef HELTEC_V3
    Heltec.display->clear();
    Heltec.display->drawString(0, 0,  "RX #" + String(rx_count));
    Heltec.display->drawString(0, 12, "RSSI:" + String(rssi) + " SNR:" + String(snr, 1));
    Heltec.display->drawString(0, 24, "MQTT: " + String(mqtt.connected() ? "OK" : "OFF"));
    Heltec.display->drawString(0, 36, received.substring(0, 22));
    Heltec.display->display();
#endif
  }
}

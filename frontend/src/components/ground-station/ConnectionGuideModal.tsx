/** Collapsible SatKit Hardware & Connection Guide inside the Ground Station
 * console — covers board jumper pins (CDHS V5, APC V5, EPS V5), I2C addresses,
 * downloadable Arduino sketch (`AlFalaj_SatKit_GroundStation.ino`), and all
 * 3 connection methods (USB Web Serial, SatKit Wi-Fi Direct, and HTTP POST). */
import { useState } from "react";
import { ChevronDown, ChevronUp, Cpu, Download, HelpCircle, Usb, Wifi, Copy, Check } from "lucide-react";

const SATKIT_ARDUINO_SKETCH = `// SpacePoint SatKit — Universal Ground Station Firmware (USB Serial + Wi-Fi Portal HTML)
// Board: ESP32 Dev Module (115200 baud)
// Works with:
//   1. USB Web Serial ("Detect USB Port" in SpacePoint Portal Ground Station)
//   2. Standalone SpacePoint Portal HTML Dashboard hosted at http://192.168.4.1/ (on Wi-Fi "ALFALAJ-SAT1", pass "falaj2026")
//   3. SatKit Wi-Fi Direct Polling ("SatKit Wi-Fi (192.168.4.1)" in Portal Ground Station)
//
// Supported Sensors (auto-detected on I2C SDA=21, SCL=22):
//   - INA219 Current/Voltage @ 0x40 (CDHS Board J5: jumpers J51-J54 closed)
//   - MB85RC256V 32KB FRAM   @ 0x50 (CDHS Board J3: jumpers J31-J38 closed)
//   - TMP102 Temperature     @ 0x48 or 0x49 (CDHS Board J4: jumpers J41-J46 closed)
//   - MPU6050 6-Axis IMU     @ 0x68 (APC J37 -> GND) or 0x69 (APC J37 -> 3V3)

#include <WiFi.h>
#include <WebServer.h>
#include <Wire.h>
#include "soc/rtc_cntl_reg.h"

#define SDA_PIN    21
#define SCL_PIN    22
#define WDT_PIN    4     // MAX6369 watchdog pin (must toggle every 100ms)
#define SHUNT_OHMS 0.010 // R010 shunt resistor on INA219

#define INA_ADDR   0x40
#define FRAM_ADDR  0x50
uint8_t tmpAddr  = 0x48; // Auto-detects 0x48 or 0x49
uint8_t mpuAddr  = 0x68; // Auto-detects 0x68 (J37->GND) or 0x69 (J37->3V3)

WebServer server(80);

bool inaOk = false, framOk = false, tmpOk = false, mpuOk = false;
bool fakeMode = false;
float tempC = NAN, busV = NAN, mA = NAN, powerMw = NAN;
float roll = 0, pitch = 0, yaw = 0;
uint32_t framRecords = 0;
unsigned long lastSample = 0, lastWdt = 0, lastTime = 0;
String cmdBuffer;

const char PORTAL_HTML[] PROGMEM = R"rawliteral(
<!DOCTYPE html><html><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>SpacePoint Ground Station — SatKit Console</title>
<style>
:root{--bg:#0d0714;--card:rgba(101,63,132,0.14);--border:rgba(101,63,132,0.38);--text:#f3f0f7;--muted:rgba(215,210,203,0.72)}
*{box-sizing:border-box;margin:0;padding:0;font-family:system-ui,sans-serif}
body{background:radial-gradient(circle at top,#1c0f2e 0%,var(--bg) 70%);color:var(--text);min-height:100vh;padding:20px}
.wrap{max-width:1100px;margin:0 auto;display:flex;flex-direction:column;gap:14px}
.top,.card{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:16px}
.top{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:10px}
.badges{display:flex;flex-wrap:wrap;gap:6px}.badge{font-size:11px;padding:4px 10px;border-radius:99px;background:rgba(255,255,255,0.06)}
.ok{color:#34d399;background:rgba(52,211,153,0.12)}.off{color:#9ca3af}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px}
.head{display:flex;justify-content:space-between;align-items:baseline}.lbl{font-size:11px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted)}
.val{font-size:24px;font-weight:700}.unit{font-size:12px;color:var(--muted);margin-left:3px}
canvas{width:100%;height:80px;margin-top:10px;display:block}
button{background:rgba(168,85,247,0.22);color:#fff;border:1px solid rgba(168,85,247,0.5);border-radius:10px;padding:7px 12px;font-size:12px;cursor:pointer}
</style></head><body><div class="wrap">
<div class="top"><div><div style="font-size:17px;font-weight:700">SpacePoint Ground Station — SatKit Local Console</div>
<div style="font-size:12px;color:var(--muted)">Offline Wi-Fi AP (192.168.4.1) &bull; USB Serial 115200 JSON Active</div></div>
<div class="badges"><span id="b-ina" class="badge off">INA219</span><span id="b-fram" class="badge off">FRAM</span><span id="b-tmp" class="badge off">TMP102</span><span id="b-mpu" class="badge off">MPU6050</span>
<button onclick="fetch('/api/cmd?mode=SIM')">Sim Toggle</button></div></div>
<div class="grid">
<div class="card"><div class="head"><span class="lbl">Temperature</span><div><span id="v-temp" class="val">--</span><span class="unit">°C</span></div></div><canvas id="c-temp"></canvas></div>
<div class="card"><div class="head"><span class="lbl">Voltage</span><div><span id="v-voltage" class="val">--</span><span class="unit">V</span></div></div><canvas id="c-voltage"></canvas></div>
<div class="card"><div class="head"><span class="lbl">Current</span><div><span id="v-current" class="val">--</span><span class="unit">A</span></div></div><canvas id="c-current"></canvas></div>
<div class="card"><div class="head"><span class="lbl">Power</span><div><span id="v-power" class="val">--</span><span class="unit">mW</span></div></div><canvas id="c-power"></canvas></div>
<div class="card"><div class="head"><span class="lbl">Roll</span><div><span id="v-roll" class="val">--</span><span class="unit">°</span></div></div><canvas id="c-roll"></canvas></div>
<div class="card"><div class="head"><span class="lbl">Pitch</span><div><span id="v-pitch" class="val">--</span><span class="unit">°</span></div></div><canvas id="c-pitch"></canvas></div>
</div>
<div class="card" style="display:flex;justify-content:space-between;font-size:12px;color:var(--muted)">
<span>FRAM Records Saved: <strong id="v-fram" style="color:#34d399">0</strong></span>
<span>Uptime: <strong id="v-up" style="color:#fff">0</strong>s</span></div></div>
<script>
const hist={temp:[],voltage:[],current:[],power:[],roll:[],pitch:[]},col={temp:'#ff6b6b',voltage:'#00c6ff',current:'#f9d423',power:'#a855f7',roll:'#00ff7f',pitch:'#39ff14'};
function draw(k){const c=document.getElementById('c-'+k),ctx=c.getContext('2d'),w=c.width=c.clientWidth,h=c.height=c.clientHeight;ctx.clearRect(0,0,w,h);
const a=hist[k].filter(v=>v!==null&&!isNaN(v));if(a.length<2)return;let mn=Math.min(...a),mx=Math.max(...a);if(mx===mn){mx++;mn--;}
ctx.strokeStyle=col[k];ctx.lineWidth=2;ctx.beginPath();a.forEach((v,i)=>{const x=(i/(a.length-1))*w,y=h-6-((v-mn)/(mx-mn))*(h-12);i?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.stroke();}
function sb(id,ok,t){const e=document.getElementById(id);e.className='badge '+(ok?'ok':'off');e.textContent=(ok?'● ':'○ ')+t;}
async function poll(){try{const r=await fetch('/api/telemetry'),d=await r.json();
sb('b-ina',d.ina_ok,'INA219 0x40');sb('b-fram',d.fram_ok,'FRAM 0x50');sb('b-tmp',d.tmp_ok,'TMP102');sb('b-mpu',d.mpu_ok,'MPU6050');
['temp','voltage','current','power','roll','pitch'].forEach(k=>{const v=d[k];document.getElementById('v-'+k).textContent=v!=null?Number(v).toFixed(k==='current'?3:2):'--';
hist[k].push(v);if(hist[k].length>60)hist[k].shift();draw(k);});
document.getElementById('v-fram').textContent=d.fram_records||0;document.getElementById('v-up').textContent=d.uptime||0;}catch(e){}}
setInterval(poll,1000);poll();
</script></body></html>
)rawliteral";

bool i2cFound(uint8_t addr) {
  Wire.beginTransmission(addr);
  return Wire.endTransmission() == 0;
}

void writeReg(uint8_t addr, uint8_t reg, uint8_t val) {
  Wire.beginTransmission(addr);
  Wire.write(reg);
  Wire.write(val);
  Wire.endTransmission();
}

int16_t read16(uint8_t addr, uint8_t reg) {
  Wire.beginTransmission(addr);
  Wire.write(reg);
  Wire.endTransmission(false);
  Wire.requestFrom(addr, (uint8_t)2);
  if (Wire.available() < 2) return 0;
  return (Wire.read() << 8) | Wire.read();
}

void writeFramRecord(uint32_t seq, float t, float v, float c, float r, float p) {
  if (!framOk) return;
  uint16_t addr = (seq % 1000) * 24;
  struct { uint32_t s; float t, v, c, r, p; } rec = { seq, t, v, c, r, p };
  Wire.beginTransmission(FRAM_ADDR);
  Wire.write((uint8_t)(addr >> 8));
  Wire.write((uint8_t)(addr & 0xFF));
  Wire.write((const uint8_t*)&rec, sizeof(rec));
  Wire.endTransmission();
}

void scanSensors() {
  inaOk  = i2cFound(INA_ADDR);
  framOk = i2cFound(FRAM_ADDR);

  if (i2cFound(0x48)) { tmpAddr = 0x48; tmpOk = true; }
  else if (i2cFound(0x49)) { tmpAddr = 0x49; tmpOk = true; }
  else tmpOk = false;

  if (i2cFound(0x68)) { mpuAddr = 0x68; if (!mpuOk) writeReg(mpuAddr, 0x6B, 0x00); mpuOk = true; }
  else if (i2cFound(0x69)) { mpuAddr = 0x69; if (!mpuOk) writeReg(mpuAddr, 0x6B, 0x00); mpuOk = true; }
  else mpuOk = false;
}

void readSensors(float dt) {
  if (fakeMode) {
    float t = millis() / 1000.0f;
    tempC = 24.5f + 2.0f * sin(t * 0.2f);
    busV = 4.18f + 0.05f * sin(t * 0.1f);
    mA = 165.0f + 15.0f * sin(t * 0.3f);
    powerMw = busV * mA;
    roll = 12.0f * sin(t * 0.4f);
    pitch = 8.0f * cos(t * 0.3f);
    yaw = fmod(t * 6.0f, 360.0f);
    return;
  }

  if (tmpOk) {
    tempC = (read16(tmpAddr, 0x00) >> 4) * 0.0625f;
  } else tempC = NAN;

  if (inaOk) {
    float shuntMv = read16(INA_ADDR, 0x01) * 0.01f;
    busV = (read16(INA_ADDR, 0x02) >> 3) * 0.004f;
    mA = fabs(shuntMv / SHUNT_OHMS);
    powerMw = busV * mA;
  } else {
    busV = mA = powerMw = NAN;
  }

  if (mpuOk) {
    Wire.beginTransmission(mpuAddr);
    Wire.write(0x3B);
    Wire.endTransmission(false);
    Wire.requestFrom(mpuAddr, (uint8_t)14);
    if (Wire.available() >= 14) {
      int16_t v[7];
      for (int i = 0; i < 7; i++) v[i] = (Wire.read() << 8) | Wire.read();
      float ax = v[0] / 16384.0f, ay = v[1] / 16384.0f, az = v[2] / 16384.0f;
      float gz = v[6] / 131.0f;
      roll = atan2(ay, az) * 57.2958f;
      pitch = atan2(-ax, sqrt(ay * ay + az * az)) * 57.2958f;
      yaw += gz * dt;
      if (yaw > 180) yaw -= 360;
      if (yaw < -180) yaw += 360;
    }
  }
}

String buildTelemetryJson() {
  String j = "{";
  j += "\\"temp\\":";    j += isnan(tempC)   ? "null" : String(tempC, 2);
  j += ",\\"voltage\\":"; j += isnan(busV)    ? "null" : String(busV, 3);
  j += ",\\"current\\":"; j += isnan(mA)      ? "null" : String(mA / 1000.0f, 4);
  j += ",\\"power\\":";   j += isnan(powerMw) ? "null" : String(powerMw, 2);
  j += ",\\"roll\\":";    j += (!mpuOk && !fakeMode) ? "null" : String(roll, 2);
  j += ",\\"pitch\\":";   j += (!mpuOk && !fakeMode) ? "null" : String(pitch, 2);
  j += ",\\"yaw\\":";     j += (!mpuOk && !fakeMode) ? "null" : String(yaw, 2);
  j += ",\\"uptime\\":";  j += String(millis() / 1000);
  j += ",\\"fram_records\\":"; j += String(framRecords);
  j += ",\\"ina_ok\\":";  j += (inaOk || fakeMode) ? "true" : "false";
  j += ",\\"fram_ok\\":"; j += (framOk || fakeMode) ? "true" : "false";
  j += ",\\"tmp_ok\\":";  j += (tmpOk || fakeMode) ? "true" : "false";
  j += ",\\"mpu_ok\\":";  j += (mpuOk || fakeMode) ? "true" : "false";
  j += "}";
  return j;
}

void handleRoot() {
  server.send_P(200, "text/html", PORTAL_HTML);
}

void handleWifiTelemetry() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.send(200, "application/json", buildTelemetryJson());
}

void handleWifiCmd() {
  if (server.hasArg("mode") && server.arg("mode") == "SIM") fakeMode = !fakeMode;
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.send(200, "application/json", "{\\"ok\\":true}");
}

void setup() {
  Serial.begin(115200);
  WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);
  pinMode(WDT_PIN, OUTPUT);
  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(50000);

  WiFi.mode(WIFI_AP);
  WiFi.softAP("ALFALAJ-SAT1", "falaj2026", 1);
  WiFi.softAPConfig(IPAddress(192, 168, 4, 1), IPAddress(192, 168, 4, 1), IPAddress(255, 255, 255, 0));

  server.on("/", handleRoot);
  server.on("/api/telemetry", handleWifiTelemetry);
  server.on("/data", handleWifiTelemetry);
  server.on("/api/cmd", handleWifiCmd);
  server.begin();
  lastTime = millis();
}

void loop() {
  server.handleClient();

  // Kick hardware watchdog every 100ms so CDHS board doesn't reset
  if (millis() - lastWdt >= 100) {
    lastWdt = millis();
    digitalWrite(WDT_PIN, !digitalRead(WDT_PIN));
  }

  // Listen for USB Web Serial commands ("CMD PING", "CMD FAKE", "CMD GET_STATUS")
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\\n') {
      cmdBuffer.trim();
      if (cmdBuffer.startsWith("CMD ")) {
        String cmd = cmdBuffer.substring(4);
        cmd.trim(); cmd.toUpperCase();
        if (cmd == "FAKE") fakeMode = !fakeMode;
        else if (cmd == "GET_STATUS") lastSample = 0;
      }
      cmdBuffer = "";
    } else if (c != '\\r') cmdBuffer += c;
  }

  if (millis() - lastSample >= 1000) {
    float dt = (millis() - lastTime) / 1000.0f;
    lastTime = millis();
    lastSample = lastTime;

    scanSensors();
    readSensors(dt);
    if (framOk) writeFramRecord(framRecords++, isnan(tempC) ? 0 : tempC, isnan(busV) ? 0 : busV, isnan(mA) ? 0 : mA, roll, pitch);

    // Output JSON over USB Serial (parsed by Ground Station Web Serial)
    Serial.println(buildTelemetryJson());
  }
}
`;

const GROUND_STATION_RECEIVER_SKETCH = `// SpacePoint Ground Station — Wireless USB Receiver Dongle (2nd Spare ESP32)
// Board: ESP32 Dev Module (115200 baud)
//
// Flash this onto a SPARE ESP32 plugged into your laptop's USB port:
//   - SatKit (ESP32 #1) runs on battery hosting "ALFALAJ-SAT1" (pass: "falaj2026").
//   - This Receiver (ESP32 #2) connects to "ALFALAJ-SAT1" over Wi-Fi, fetches
//     http://192.168.4.1/api/telemetry every second, injects the live wireless
//     RSSI (dBm), and streams JSON over USB Serial into the Portal ("Detect USB Port").
//   - Your laptop stays on normal Wi-Fi/internet while the SatKit is 100% wireless!

#include <WiFi.h>
#include <HTTPClient.h>
#include "soc/rtc_cntl_reg.h"

const char* SAT_SSID = "ALFALAJ-SAT1";
const char* SAT_PASS = "falaj2026";
const char* SAT_HOST = "http://192.168.4.1";

unsigned long lastPoll = 0, lastReconnect = 0;
String cmdBuffer;

void ensureSatWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  if (millis() - lastReconnect < 3000) return;
  lastReconnect = millis();
  WiFi.disconnect();
  WiFi.begin(SAT_SSID, SAT_PASS);
}

void forwardCommandToSatKit(String cmd) {
  cmd.trim();
  int space = cmd.indexOf(' ');
  String name = (space < 0) ? cmd : cmd.substring(0, space);
  name.toUpperCase();
  if (WiFi.status() != WL_CONNECTED) return;

  String path = "/api/telemetry";
  if (name == "TAKE_PICTURE") path = "/api/cmd?capture=1";
  else if (name == "SPIN_CW") path = "/api/cmd?wz=180";
  else if (name == "SPIN_CCW") path = "/api/cmd?wz=-180";
  else if (name == "STOP") path = "/api/cmd?adcs=OFF";
  else if (name == "FAKE") path = "/api/cmd?mode=SIM";
  else { lastPoll = 0; return; }

  HTTPClient http;
  http.setTimeout(1200);
  if (http.begin(String(SAT_HOST) + path)) { http.GET(); http.end(); }
}

void pollSatKitTelemetry() {
  if (WiFi.status() != WL_CONNECTED) return;
  int rssi = WiFi.RSSI();
  const char* paths[] = { "/api/telemetry", "/data" };
  for (int i = 0; i < 2; i++) {
    HTTPClient http;
    http.setTimeout(800);
    if (!http.begin(String(SAT_HOST) + paths[i])) continue;
    if (http.GET() == 200) {
      String body = http.getString();
      http.end();
      body.trim();
      if (body.startsWith("{") && body.endsWith("}")) {
        int idx = body.indexOf("\\"rssi\\":0");
        if (idx >= 0) body = body.substring(0, idx) + "\\"rssi\\":" + String(rssi) + body.substring(idx + 8);
        else if (body.indexOf("\\"rssi\\":") < 0) body = body.substring(0, body.length() - 1) + ",\\"rssi\\":" + String(rssi) + "}";
        body.replace("\\r", ""); body.replace("\\n", "");
        Serial.println(body);
        return;
      }
    } else http.end();
  }
}

void setup() {
  Serial.begin(115200);
  WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(SAT_SSID, SAT_PASS);
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\\n') {
      cmdBuffer.trim();
      if (cmdBuffer.startsWith("CMD ")) forwardCommandToSatKit(cmdBuffer.substring(4));
      cmdBuffer = "";
    } else if (c != '\\r') cmdBuffer += c;
  }
  ensureSatWifi();
  if (millis() - lastPoll >= 1000) { lastPoll = millis(); pollSatKitTelemetry(); }
}
`;

export default function ConnectionGuideModal() {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  function downloadFile(content: string, filename: string) {
    const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  function copySketch() {
    void navigator.clipboard.writeText(SATKIT_ARDUINO_SKETCH);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="rounded-xl ring-1 ring-border bg-card overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full px-4 py-2.5 flex items-center justify-between gap-3 text-left text-xs font-medium hover:bg-muted/50 transition-colors"
      >
        <span className="inline-flex items-center gap-2">
          <HelpCircle className="size-4 text-primary" />
          <span>SatKit Hardware, Pins & Connection Guide (How to Connect Your ESP32)</span>
        </span>
        <span className="inline-flex items-center gap-1 text-muted-foreground">
          {open ? "Hide guide" : "Show guide"}
          {open ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
        </span>
      </button>

      {open && (
        <div className="p-4 border-t border-border space-y-5 text-xs">
          {/* Section 1: Firmware to load */}
          <div className="space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="font-semibold text-sm flex items-center gap-2">
                <Cpu className="size-4 text-primary" />
                1. Arduino Firmware to Load onto the SatKit ESP32
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={copySketch}
                  className="inline-flex items-center gap-1.5 rounded-lg ring-1 ring-border px-2.5 py-1 hover:bg-muted"
                >
                  {copied ? <Check className="size-3.5 text-emerald-500" /> : <Copy className="size-3.5" />}
                  {copied ? "Copied!" : "Copy SatKit .ino"}
                </button>
                <button
                  type="button"
                  onClick={() => downloadFile(SATKIT_ARDUINO_SKETCH, "AlFalaj_SatKit_GroundStation.ino")}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-primary text-primary-foreground px-3 py-1 font-medium hover:opacity-90"
                >
                  <Download className="size-3.5" />
                  1. SatKit Firmware (.ino)
                </button>
                <button
                  type="button"
                  onClick={() => downloadFile(GROUND_STATION_RECEIVER_SKETCH, "GroundStation_USB_Receiver.ino")}
                  className="inline-flex items-center gap-1.5 rounded-lg ring-1 ring-primary/50 bg-primary/10 text-primary px-3 py-1 font-medium hover:bg-primary/20"
                  title="Flash onto a 2nd spare ESP32 plugged into laptop USB to receive SatKit Wi-Fi telemetry while keeping laptop on normal internet"
                >
                  <Download className="size-3.5" />
                  2. Spare ESP32 USB Receiver (.ino)
                </button>
              </div>
            </div>
            <p className="text-muted-foreground leading-relaxed">
              This Ground Station automatically supports <strong>all 3 SatKit firmware versions</strong> without changing any code:
              {" "}(1) <code className="bg-muted px-1 py-0.5 rounded">AlFalaj_CDHS.ino</code> (Wi-Fi AP Mission Console with <code className="bg-muted px-1 py-0.5 rounded">#define SIMULATE 0</code>),
              {" "}(2) <code className="bg-muted px-1 py-0.5 rounded">AlFalaj_Sensors.ino</code> (Serial + <code className="bg-muted px-1 py-0.5 rounded">/data</code> endpoint), or
              {" "}(3) the universal <code className="bg-muted px-1 py-0.5 rounded">AlFalaj_SatKit_GroundStation.ino</code> downloadable above (outputs both USB Serial JSON and Wi-Fi <code className="bg-muted px-1 py-0.5 rounded">192.168.4.1/api/telemetry</code> simultaneously).
            </p>
            <div className="rounded-lg bg-muted/40 p-2.5 text-[11px] text-muted-foreground space-y-1">
              <div><strong>Arduino IDE Settings:</strong> Board: <code className="text-foreground">ESP32 Dev Module</code> • Port: <code className="text-foreground">COMx (USB-SERIAL CH340)</code> • Baud Rate: <code className="text-foreground">115200</code></div>
              <div><strong>Important:</strong> Close the Arduino Serial Monitor before clicking <strong>Detect USB Port</strong> in the browser (only one program can hold the COM port open at a time).</div>
            </div>
          </div>

          {/* Section 2: Hardware Pinout & Jumpers */}
          <div className="space-y-2">
            <div className="font-semibold text-sm">2. SatKit Board Pinout, Jumpers & I2C Addresses</div>
            <p className="text-muted-foreground">
              All sensors communicate over the ESP32 I2C bus (<code className="bg-muted px-1 py-0.5 rounded">SDA = GPIO 21</code>, <code className="bg-muted px-1 py-0.5 rounded">SCL = GPIO 22</code>, Watchdog <code className="bg-muted px-1 py-0.5 rounded">WDI = GPIO 4</code>). Verify these jumper caps on your stack:
            </p>
            <div className="overflow-x-auto rounded-lg ring-1 ring-border">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-muted/60 text-[11px] uppercase tracking-wider text-muted-foreground">
                    <th className="p-2.5 border-b border-border">Board & Socket</th>
                    <th className="p-2.5 border-b border-border">Sensor / Module</th>
                    <th className="p-2.5 border-b border-border">I2C Address</th>
                    <th className="p-2.5 border-b border-border">Required Jumpers / Wiring</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border text-[11px]">
                  <tr>
                    <td className="p-2.5 font-medium">CDHS V5 — Power</td>
                    <td className="p-2.5">ESP32 + 3.3V I2C Bus</td>
                    <td className="p-2.5 font-mono">—</td>
                    <td className="p-2.5">
                      <code className="bg-muted px-1 py-0.5 rounded">J122 (3V3_ESP32)</code> & <code className="bg-muted px-1 py-0.5 rounded">J123 (5V_ESP32)</code> jumper caps installed (or EPS battery switch ON) so the 3.3V sensor rail is powered.
                    </td>
                  </tr>
                  <tr>
                    <td className="p-2.5 font-medium">CDHS V5 — <code className="font-mono">J5</code></td>
                    <td className="p-2.5">INA219 Current & Voltage</td>
                    <td className="p-2.5 font-mono text-emerald-400">0x40</td>
                    <td className="p-2.5">
                      Close jumpers <code className="bg-muted px-1 py-0.5 rounded">J51</code> (SCL), <code className="bg-muted px-1 py-0.5 rounded">J52</code> (SDA), <code className="bg-muted px-1 py-0.5 rounded">J53</code> (VIN+), <code className="bg-muted px-1 py-0.5 rounded">J54</code> (VIN-). Uses <code className="font-mono">R010</code> (0.010 Ω) shunt.
                    </td>
                  </tr>
                  <tr>
                    <td className="p-2.5 font-medium">CDHS V5 — <code className="font-mono">J3</code></td>
                    <td className="p-2.5">MB85RC256V 32KB FRAM</td>
                    <td className="p-2.5 font-mono text-emerald-400">0x50</td>
                    <td className="p-2.5">
                      Close jumpers <code className="bg-muted px-1 py-0.5 rounded">J31–J38</code> next to socket <code className="font-mono">J3</code> (grounds WP, A0, A1, A2 and connects SDA/SCL).
                    </td>
                  </tr>
                  <tr>
                    <td className="p-2.5 font-medium">CDHS V5 — <code className="font-mono">J4</code></td>
                    <td className="p-2.5">TMP102 Temperature</td>
                    <td className="p-2.5 font-mono text-emerald-400">0x48 / 0x49</td>
                    <td className="p-2.5">
                      Close jumpers <code className="bg-muted px-1 py-0.5 rounded">J41–J46</code> next to socket <code className="font-mono">J4</code> (<code className="font-mono">ADD0 → GND</code> = <code className="font-mono">0x48</code>; <code className="font-mono">ADD0 → 3V3</code> = <code className="font-mono">0x49</code>; both auto-detected).
                    </td>
                  </tr>
                  <tr>
                    <td className="p-2.5 font-medium">APC V5 — <code className="font-mono">J3</code></td>
                    <td className="p-2.5">MPU6050 6-Axis IMU</td>
                    <td className="p-2.5 font-mono text-emerald-400">0x68 / 0x69</td>
                    <td className="p-2.5">
                      Plug MPU6050 into <code className="font-mono">J3</code> on APC board. Connect header <code className="bg-muted px-1 py-0.5 rounded">J37 (AD0)</code> to <strong>3V3</strong> for <code className="font-mono">0x69</code> or to <strong>GND</strong> for <code className="font-mono">0x68</code> (firmware auto-detects both).
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Section 3: 4 Connection Methods */}
          <div className="space-y-2">
            <div className="font-semibold text-sm">3. Choose Any Connection Method</div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
              <div className="rounded-lg ring-1 ring-border p-3 space-y-1.5 bg-muted/20">
                <div className="font-semibold flex items-center gap-1.5 text-foreground">
                  <Usb className="size-3.5 text-primary" />
                  Method A: Direct USB Cable
                </div>
                <ol className="list-decimal list-inside space-y-1 text-muted-foreground text-[11px]">
                  <li>Keep your laptop connected to your regular Wi-Fi/internet.</li>
                  <li>Plug the SatKit ESP32 into your laptop via USB and close Arduino Serial Monitor.</li>
                  <li>Click <strong>Detect USB Port</strong> above and select <code className="text-foreground">USB-SERIAL CH340 (COMx)</code>.</li>
                  <li>Charts update live and stream straight to the cloud database.</li>
                </ol>
              </div>

              <div className="rounded-lg ring-1 ring-primary/40 p-3 space-y-1.5 bg-primary/5">
                <div className="font-semibold flex items-center gap-1.5 text-foreground">
                  <Wifi className="size-3.5 text-primary" />
                  Method B: 2-ESP32 Wireless Bridge (Best!)
                </div>
                <ol className="list-decimal list-inside space-y-1 text-muted-foreground text-[11px]">
                  <li>Leave the <strong>SatKit (ESP32 #1)</strong> untethered on battery hosting <code className="text-foreground">ALFALAJ-SAT1</code>.</li>
                  <li>Flash <strong>2. Spare ESP32 USB Receiver (.ino)</strong> onto a <strong>2nd ESP32</strong> plugged into your laptop USB.</li>
                  <li>Keep laptop on normal internet Wi-Fi and click <strong>Detect USB Port</strong> (pick the 2nd ESP32).</li>
                  <li>100% wireless CubeSat + full laptop internet + live <code className="text-foreground">Signal RSSI (dBm)</code>!</li>
                </ol>
              </div>

              <div className="rounded-lg ring-1 ring-border p-3 space-y-1.5 bg-muted/20">
                <div className="font-semibold flex items-center gap-1.5 text-foreground">
                  <Wifi className="size-3.5 text-emerald-500" />
                  Method C: SatKit Wi-Fi + Offline HTML
                </div>
                <ol className="list-decimal list-inside space-y-1 text-muted-foreground text-[11px]">
                  <li>Connect laptop Wi-Fi to <code className="text-foreground">ALFALAJ-SAT1</code> (pass: <code className="text-foreground">falaj2026</code>).</li>
                  <li>If this Portal page is already open, click <strong>SatKit Wi-Fi (192.168.4.1)</strong> (queues frames offline & syncs later).</li>
                  <li>Or open <code className="text-foreground">http://192.168.4.1/</code> directly in the browser for the built-in offline SpacePoint HTML Console!</li>
                </ol>
              </div>

              <div className="rounded-lg ring-1 ring-border p-3 space-y-1.5 bg-muted/20">
                <div className="font-semibold flex items-center gap-1.5 text-foreground">
                  <Cpu className="size-3.5 text-amber-500" />
                  Method D: Cloud HTTP / Sim
                </div>
                <ol className="list-decimal list-inside space-y-1 text-muted-foreground text-[11px]">
                  <li>Click <strong>Sim</strong> above to test live synthetic orbits immediately without hardware.</li>
                  <li>Or connect your ESP32 to classroom Wi-Fi and <code className="text-foreground">POST</code> JSON (flat or nested) directly to the device ingest URL at the top of this page.</li>
                </ol>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* SpacePoint SatKit — Universal Ground Station Firmware (USB Serial + Wi-Fi Portal HTML)
 *
 * Board: ESP32 Dev Module (115200 baud)
 * Libraries needed: NONE (uses only built-in ESP32 WiFi, WebServer, Wire)
 *
 * Supports ALL connection modes out of the box:
 *   1. Direct USB Cable -> SpacePoint Portal ("Detect USB Port" via Web Serial)
 *      Streams 1 Hz JSON lines over Serial while laptop stays on normal Wi-Fi/internet.
 *   2. Embedded SpacePoint Portal HTML Dashboard -> Wi-Fi AP "ALFALAJ-SAT1" (pass: "falaj2026")
 *      Open http://192.168.4.1/ in any browser (works completely offline & survives page refresh!).
 *   3. Portal Wi-Fi Polling -> http://192.168.4.1/api/telemetry & /data (CORS enabled).
 *
 * Auto-Detected I2C Sensors (SDA = GPIO 21, SCL = GPIO 22, Watchdog WDI = GPIO 4):
 *   - INA219 Current & Voltage @ 0x40 (CDHS J5: jumpers J51-J54 closed, R010 0.010 ohm shunt)
 *   - MB85RC256V 32KB FRAM     @ 0x50 (CDHS J3: jumpers J31-J38 closed)
 *   - TMP102 Temperature       @ 0x48 or 0x49 (CDHS J4: jumpers J41-J46 closed)
 *   - MPU6050 6-Axis IMU       @ 0x68 (APC J37 -> GND) or 0x69 (APC J37 -> 3V3)
 */

#include <WiFi.h>
#include <WebServer.h>
#include <Wire.h>
#include "soc/rtc_cntl_reg.h"

#define SDA_PIN    21
#define SCL_PIN    22
#define WDT_PIN    4     // MAX6369 hardware watchdog on CDHS V5 (must toggle every 100ms)
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

// Self-contained SpacePoint Portal Ground Station HTML Dashboard served at http://192.168.4.1/
const char PORTAL_HTML[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>SpacePoint Ground Station — SatKit Local Console</title>
<style>
  :root { --bg:#0d0714; --card:rgba(101,63,132,0.12); --border:rgba(101,63,132,0.35); --text:#f3f0f7; --muted:rgba(215,210,203,0.72); --accent:#a855f7; }
  * { box-sizing:border-box; margin:0; padding:0; font-family:system-ui,-apple-system,sans-serif; }
  body { background:radial-gradient(circle at top,#1c0f2e 0%,var(--bg) 70%); color:var(--text); min-height:100vh; padding:20px; }
  .wrap { max-width:1120px; margin:0 auto; display:flex; flex-direction:column; gap:16px; }
  .top { display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:12px; padding:14px 18px; border-radius:16px; background:var(--card); border:1px solid var(--border); }
  .title { font-size:18px; font-weight:700; letter-spacing:0.02em; }
  .sub { font-size:12px; color:var(--muted); margin-top:2px; }
  .badges { display:flex; flex-wrap:wrap; align-items:center; gap:8px; }
  .badge { font-size:11px; padding:4px 10px; border-radius:999px; background:rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.12); }
  .badge.ok { color:#34d399; border-color:rgba(52,211,153,0.35); background:rgba(52,211,153,0.1); }
  .badge.off { color:#9ca3af; }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:14px; }
  .card { background:var(--card); border:1px solid var(--border); border-radius:16px; padding:18px; display:flex; flex-direction:column; gap:12px; box-shadow:0 8px 32px rgba(0,0,0,0.3); }
  .head { display:flex; justify-content:space-between; align-items:flex-start; }
  .lbl { font-size:11px; text-transform:uppercase; letter-spacing:0.12em; color:var(--muted); }
  .val { font-size:26px; font-weight:700; }
  .unit { font-size:12px; color:var(--muted); margin-left:4px; }
  canvas { width:100%; height:84px; display:block; }
  .row { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
  @media(max-width:720px){ .row { grid-template-columns:1fr; } }
  .cube-wrap { display:flex; align-items:center; justify-content:space-around; padding:16px 0; perspective:500px; }
  .cube { width:84px; height:84px; position:relative; transform-style:preserve-3d; transition:transform 0.15s linear; }
  .face { position:absolute; width:84px; height:84px; border:2px solid #a855f7; background:rgba(168,85,247,0.18); display:flex; align-items:center; justify-content:center; font-size:10px; font-weight:700; }
  .f-front  { transform:translateZ(42px); }
  .f-back   { transform:rotateY(180deg) translateZ(42px); }
  .f-right  { transform:rotateY(90deg) translateZ(42px); }
  .f-left   { transform:rotateY(-90deg) translateZ(42px); }
  .f-top    { transform:rotateX(90deg) translateZ(42px); }
  .f-bottom { transform:rotateX(-90deg) translateZ(42px); }
  .btns { display:flex; flex-wrap:wrap; gap:8px; }
  button { background:rgba(168,85,247,0.2); color:#fff; border:1px solid rgba(168,85,247,0.5); border-radius:10px; padding:8px 14px; font-size:12px; font-weight:600; cursor:pointer; }
  button:hover { background:rgba(168,85,247,0.35); }
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div>
      <div class="title">SpacePoint Ground Station — SatKit Console</div>
      <div class="sub">Direct Wi-Fi AP (192.168.4.1) &bull; USB Serial 115200 JSON Active</div>
    </div>
    <div class="badges">
      <span id="b-link" class="badge ok">● Live</span>
      <span id="b-ina" class="badge off">INA219 (0x40)</span>
      <span id="b-fram" class="badge off">FRAM (0x50)</span>
      <span id="b-tmp" class="badge off">TMP102 (0x48)</span>
      <span id="b-mpu" class="badge off">MPU6050 (0x68/69)</span>
    </div>
  </div>

  <div class="grid">
    <div class="card"><div class="head"><span class="lbl">Temperature</span><div><span id="v-temp" class="val">--</span><span class="unit">°C</span></div></div><canvas id="c-temp"></canvas></div>
    <div class="card"><div class="head"><span class="lbl">Voltage</span><div><span id="v-voltage" class="val">--</span><span class="unit">V</span></div></div><canvas id="c-voltage"></canvas></div>
    <div class="card"><div class="head"><span class="lbl">Current</span><div><span id="v-current" class="val">--</span><span class="unit">A</span></div></div><canvas id="c-current"></canvas></div>
    <div class="card"><div class="head"><span class="lbl">Power</span><div><span id="v-power" class="val">--</span><span class="unit">mW</span></div></div><canvas id="c-power"></canvas></div>
    <div class="card"><div class="head"><span class="lbl">Roll</span><div><span id="v-roll" class="val">--</span><span class="unit">°</span></div></div><canvas id="c-roll"></canvas></div>
    <div class="card"><div class="head"><span class="lbl">Pitch</span><div><span id="v-pitch" class="val">--</span><span class="unit">°</span></div></div><canvas id="c-pitch"></canvas></div>
  </div>

  <div class="row">
    <div class="card">
      <div class="lbl">3D Attitude (MPU6050 IMU)</div>
      <div class="cube-wrap">
        <div id="cube" class="cube">
          <div class="face f-front">+X</div><div class="face f-back">-X</div>
          <div class="face f-right">+Y</div><div class="face f-left">-Y</div>
          <div class="face f-top">+Z</div><div class="face f-bottom">-Z</div>
        </div>
        <div style="font-size:13px;line-height:1.8;color:var(--muted)">
          <div>Roll: <strong id="a-roll" style="color:#fff">--</strong>°</div>
          <div>Pitch: <strong id="a-pitch" style="color:#fff">--</strong>°</div>
          <div>Yaw: <strong id="a-yaw" style="color:#fff">--</strong>°</div>
        </div>
      </div>
    </div>
    <div class="card">
      <div class="lbl">FRAM Non-Volatile Storage & Commands</div>
      <div style="font-size:13px;line-height:1.8;color:var(--muted)">
        <div>FRAM Records Saved: <strong id="v-fram" style="color:#34d399">0</strong></div>
        <div>Uptime: <strong id="v-up" style="color:#fff">0</strong> s</div>
      </div>
      <div class="btns" style="margin-top:auto">
        <button onclick="cmd('mode=SIM')">Toggle Sim (FAKE)</button>
        <button onclick="poll()">Refresh Now (GET_STATUS)</button>
      </div>
    </div>
  </div>
</div>
<script>
const MAX=60;
const hist={temp:[],voltage:[],current:[],power:[],roll:[],pitch:[]};
const colors={temp:'#ff6b6b',voltage:'#00c6ff',current:'#f9d423',power:'#a855f7',roll:'#00ff7f',pitch:'#39ff14'};
function draw(k){
  const c=document.getElementById('c-'+k); if(!c)return;
  const ctx=c.getContext('2d'); const w=c.width=c.clientWidth; const h=c.height=c.clientHeight;
  ctx.clearRect(0,0,w,h);
  const arr=hist[k].filter(v=>v!==null&&!isNaN(v)); if(arr.length<2)return;
  let mn=Math.min(...arr), mx=Math.max(...arr); if(mx===mn){mx+=1;mn-=1;}
  ctx.strokeStyle=colors[k]; ctx.lineWidth=2; ctx.beginPath();
  arr.forEach((v,i)=>{ const x=(i/(arr.length-1))*w; const y=h-6-((v-mn)/(mx-mn))*(h-12); i===0?ctx.moveTo(x,y):ctx.lineTo(x,y); });
  ctx.stroke();
}
function setBadge(id,ok,txt){ const el=document.getElementById(id); if(!el)return; el.className='badge '+(ok?'ok':'off'); el.textContent=(ok?'● ':'○ ')+txt; }
async function cmd(q){ try{ await fetch('/api/cmd?'+q); poll(); }catch(e){} }
async function poll(){
  try{
    const r=await fetch('/api/telemetry'); const d=await r.json();
    setBadge('b-link',true,'Live');
    setBadge('b-ina',d.ina_ok,'INA219 (0x40)');
    setBadge('b-fram',d.fram_ok,'FRAM (0x50)');
    setBadge('b-tmp',d.tmp_ok,'TMP102');
    setBadge('b-mpu',d.mpu_ok,'MPU6050');
    ['temp','voltage','current','power','roll','pitch'].forEach(k=>{
      const v=d[k];
      document.getElementById('v-'+k).textContent=(v!==null&&v!==undefined)?Number(v).toFixed(k==='current'?3:2):'--';
      hist[k].push(v); if(hist[k].length>MAX)hist[k].shift(); draw(k);
    });
    document.getElementById('a-roll').textContent=d.roll!==null?Number(d.roll).toFixed(1):'--';
    document.getElementById('a-pitch').textContent=d.pitch!==null?Number(d.pitch).toFixed(1):'--';
    document.getElementById('a-yaw').textContent=d.yaw!==null?Number(d.yaw).toFixed(1):'--';
    document.getElementById('cube').style.transform=`rotateX(${-(d.pitch||0)}deg) rotateY(${d.yaw||0}deg) rotateZ(${d.roll||0}deg)`;
    document.getElementById('v-fram').textContent=d.fram_records||0;
    document.getElementById('v-up').textContent=d.uptime||0;
  }catch(e){ setBadge('b-link',false,'Offline'); }
}
setInterval(poll,1000); poll();
</script>
</body>
</html>
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
  j += "\"temp\":";    j += isnan(tempC)   ? "null" : String(tempC, 2);
  j += ",\"voltage\":"; j += isnan(busV)    ? "null" : String(busV, 3);
  j += ",\"current\":"; j += isnan(mA)      ? "null" : String(mA / 1000.0f, 4);
  j += ",\"power\":";   j += isnan(powerMw) ? "null" : String(powerMw, 2);
  j += ",\"roll\":";    j += (!mpuOk && !fakeMode) ? "null" : String(roll, 2);
  j += ",\"pitch\":";   j += (!mpuOk && !fakeMode) ? "null" : String(pitch, 2);
  j += ",\"yaw\":";     j += (!mpuOk && !fakeMode) ? "null" : String(yaw, 2);
  j += ",\"uptime\":";  j += String(millis() / 1000);
  j += ",\"fram_records\":"; j += String(framRecords);
  j += ",\"ina_ok\":";  j += (inaOk || fakeMode) ? "true" : "false";
  j += ",\"fram_ok\":"; j += (framOk || fakeMode) ? "true" : "false";
  j += ",\"tmp_ok\":";  j += (tmpOk || fakeMode) ? "true" : "false";
  j += ",\"mpu_ok\":";  j += (mpuOk || fakeMode) ? "true" : "false";
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
  server.send(200, "application/json", "{\"ok\":true}");
}

void handleCommand(String cmd) {
  cmd.trim();
  int space = cmd.indexOf(' ');
  String name = (space < 0) ? cmd : cmd.substring(0, space);
  name.toUpperCase();

  if (name == "PING") {
    Serial.println("[CDHS] PONG");
  } else if (name == "GET_STATUS") {
    lastSample = 0;
  } else if (name == "FAKE") {
    fakeMode = !fakeMode;
    Serial.println(fakeMode ? "[CDHS] simulated-data mode ON" : "[CDHS] simulated-data mode OFF");
  }
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

  // Kick MAX6369 watchdog every 100ms
  if (millis() - lastWdt >= 100) {
    lastWdt = millis();
    digitalWrite(WDT_PIN, !digitalRead(WDT_PIN));
  }

  // Poll USB Serial commands ("CMD PING", "CMD FAKE", "CMD GET_STATUS")
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      cmdBuffer.trim();
      if (cmdBuffer.startsWith("CMD ")) {
        handleCommand(cmdBuffer.substring(4));
      }
      cmdBuffer = "";
    } else if (c != '\r') {
      cmdBuffer += c;
    }
  }

  if (millis() - lastSample >= 1000) {
    float dt = (millis() - lastTime) / 1000.0f;
    lastTime = millis();
    lastSample = lastTime;

    scanSensors();
    readSensors(dt);
    if (framOk) writeFramRecord(framRecords++, isnan(tempC) ? 0 : tempC, isnan(busV) ? 0 : busV, isnan(mA) ? 0 : mA, roll, pitch);

    // Output 1 Hz JSON over USB Serial (parsed by SpacePoint Portal Web Serial)
    Serial.println(buildTelemetryJson());
  }
}

/* Minimal test sketch for the Ground Station's Web Serial direct-connect.
 * No radio, no sensors, no wiring required — plug a bare ESP32 (or any
 * Arduino-compatible board) in over USB, flash this, and it prints fake
 * telemetry once a second in the exact JSON shape the browser parser
 * expects (see frontend/src/lib/groundStationWebSerial.ts::parseTelemetryLine).
 *
 * Use this to prove the USB -> browser -> Ground Station pipeline works
 * before wiring up real sensors or debugging firmware that talks over
 * LoRa/MQTT instead of plain serial (ground_station.ino, satellite_board.ino).
 */

unsigned long lastSend = 0;

void setup() {
  Serial.begin(115200);
}

void loop() {
  unsigned long now = millis();
  if (now - lastSend < 1000) return;
  lastSend = now;

  float t = now / 1000.0;
  float temp = 25.0 + 5.0 * sin(t * 0.1);
  float voltage = 3.7 + 0.3 * sin(t * 0.05);
  float current = 0.4 + 0.1 * sin(t * 0.2);
  float power = voltage * current;
  float roll = 10.0 * sin(t * 0.3);
  float pitch = 8.0 * cos(t * 0.25);
  float yaw = fmod(t * 5.0, 360.0);

  Serial.print("{\"temp\":");
  Serial.print(temp, 2);
  Serial.print(",\"voltage\":");
  Serial.print(voltage, 2);
  Serial.print(",\"current\":");
  Serial.print(current, 2);
  Serial.print(",\"power\":");
  Serial.print(power, 2);
  Serial.print(",\"roll\":");
  Serial.print(roll, 2);
  Serial.print(",\"pitch\":");
  Serial.print(pitch, 2);
  Serial.print(",\"yaw\":");
  Serial.print(yaw, 2);
  Serial.println("}");
}

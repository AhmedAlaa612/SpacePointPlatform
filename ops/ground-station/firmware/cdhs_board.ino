/* CDHS board — the real direct-USB rig students wire up and connect via
 * Web Serial, per the SpacePoint curriculum (spacepoint-software-guide):
 *
 *   ESP32, I2C on SDA=21 / SCL=22
 *   - TMP102 temperature sensor  @ 0x49
 *   - INA219 current/voltage sensor @ 0x40
 *   - MPU6050 IMU (orientation)  @ 0x68 (default)
 *
 * Prints one JSON telemetry line per second — exactly the shape
 * frontend/src/lib/groundStationWebSerial.ts::parseTelemetryLine expects
 * (temp + voltage required; roll/pitch/yaw optional, triggers the ADCS
 * dispatch when yaw is present). No wrapper prefix needed — bare JSON.
 *
 * Libraries (Arduino Library Manager):
 *   - Adafruit INA219
 *   - Adafruit MPU6050 + Adafruit Unified Sensor
 *   (TMP102 is read directly over Wire — no extra library needed.)
 */

#include <Wire.h>
#include <Adafruit_INA219.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>

#define TMP102_ADDR 0x49

Adafruit_INA219 ina219;
Adafruit_MPU6050 mpu;

float roll = 0, pitch = 0, yaw = 0;
unsigned long lastSample = 0;
unsigned long lastTime = 0;

float readTmp102() {
  Wire.beginTransmission(TMP102_ADDR);
  Wire.write(0x00); // temperature register
  Wire.endTransmission();

  Wire.requestFrom(TMP102_ADDR, 2);
  if (Wire.available() < 2) return NAN;
  int16_t raw = (Wire.read() << 8) | Wire.read();
  raw >>= 4; // 12-bit value, left-justified
  return raw * 0.0625f;
}

void setup() {
  Serial.begin(115200);
  Wire.begin(21, 22);

  if (!ina219.begin()) {
    Serial.println("[CDHS ERROR] INA219 not found at 0x40");
  }
  if (!mpu.begin()) {
    Serial.println("[CDHS ERROR] MPU6050 not found at 0x68");
  } else {
    mpu.setAccelerometerRange(MPU6050_RANGE_2_G);
    mpu.setGyroRange(MPU6050_RANGE_250_DEG);
    mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
  }

  lastTime = millis();
}

void loop() {
  unsigned long now = millis();
  if (now - lastSample < 1000) return;
  lastSample = now;

  float temp = readTmp102();
  float voltage = ina219.getBusVoltage_V();
  float current = ina219.getCurrent_mA() / 1000.0f; // -> A
  float power = voltage * current;

  sensors_event_t accel, gyro, mpuTemp;
  mpu.getEvent(&accel, &gyro, &mpuTemp);
  float dt = (now - lastTime) / 1000.0f;
  lastTime = now;

  float accRoll  =  atan2(accel.acceleration.y, accel.acceleration.z) * 180.0 / PI;
  float accPitch = -atan2(accel.acceleration.x, accel.acceleration.z) * 180.0 / PI;
  float alpha = 0.96f;
  roll  = alpha * (roll  + gyro.gyro.x * dt * 180.0 / PI) + (1 - alpha) * accRoll;
  pitch = alpha * (pitch + gyro.gyro.y * dt * 180.0 / PI) + (1 - alpha) * accPitch;
  yaw += gyro.gyro.z * dt * 180.0 / PI;
  if (yaw > 180) yaw -= 360;
  if (yaw < -180) yaw += 360;

  Serial.print("{\"temp\":");
  Serial.print(temp, 2);
  Serial.print(",\"voltage\":");
  Serial.print(voltage, 2);
  Serial.print(",\"current\":");
  Serial.print(current, 3);
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

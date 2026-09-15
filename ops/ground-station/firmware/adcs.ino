/*
 * ============================================================
 * ADCS Firmware — SpacePoint Club
 * Board : Arduino Uno/Nano (or compatible)
 * Sensors: MPU6050 (I2C), GY-GPS6MV2 (UART @ 9600 baud)
 * Actuators: Reaction wheels on DC motor drivers (PWM)
 *
 * Serial output (to PC/ground station):
 *   ADCS:<roll>,<pitch>,<yaw>,<lat>,<lon>,<alt>,<wx>,<wy>,<wz>
 *
 * Serial commands received from PC:
 *   WHEEL:X,<speed>   — spin X-axis wheel (speed in -255..255 PWM)
 *   WHEEL:Y,<speed>
 *   WHEEL:Z,<speed>
 *
 * Libraries required (install via Arduino Library Manager):
 *   - Adafruit MPU6050
 *   - Adafruit Unified Sensor
 *   - TinyGPS++ (by Mikal Hart)
 * ============================================================
 */

#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <TinyGPS++.h>
#include <SoftwareSerial.h>

// ── Pin Definitions ──────────────────────────────────────────────────────────
// GPS uses SoftwareSerial so we keep the hardware UART for the PC link
#define GPS_RX_PIN  4   // Connect to GPS TX
#define GPS_TX_PIN  5   // Connect to GPS RX (usually unused)

// Reaction wheel motor driver PWM + direction pins
// Assumes L298N or similar H-bridge per axis
#define WHEEL_X_EN  9   // PWM enable
#define WHEEL_X_IN1 6
#define WHEEL_X_IN2 7

#define WHEEL_Y_EN  10
#define WHEEL_Y_IN1 8
#define WHEEL_Y_IN2 11  // re-wire if pin conflict

#define WHEEL_Z_EN  3
#define WHEEL_Z_IN1 12
#define WHEEL_Z_IN2 13

// ── Objects ───────────────────────────────────────────────────────────────────
Adafruit_MPU6050 mpu;
SoftwareSerial   gpsSerial(GPS_RX_PIN, GPS_TX_PIN);
TinyGPSPlus      gps;

// ── State ─────────────────────────────────────────────────────────────────────
float roll = 0, pitch = 0, yaw = 0;
float gyroYawRate = 0;
unsigned long lastTime = 0;

// Wheel speeds in -255..255 PWM units
int wheelX = 0, wheelY = 0, wheelZ = 0;

// ── Helpers ───────────────────────────────────────────────────────────────────

void setWheel(uint8_t enPin, uint8_t in1, uint8_t in2, int speed) {
  if (speed > 0) {
    digitalWrite(in1, HIGH);
    digitalWrite(in2, LOW);
  } else if (speed < 0) {
    digitalWrite(in1, LOW);
    digitalWrite(in2, HIGH);
    speed = -speed;
  } else {
    digitalWrite(in1, LOW);
    digitalWrite(in2, LOW);
  }
  analogWrite(enPin, constrain(speed, 0, 255));
}

// ── Setup ─────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  gpsSerial.begin(9600);

  // Motor driver pins
  pinMode(WHEEL_X_EN, OUTPUT); pinMode(WHEEL_X_IN1, OUTPUT); pinMode(WHEEL_X_IN2, OUTPUT);
  pinMode(WHEEL_Y_EN, OUTPUT); pinMode(WHEEL_Y_IN1, OUTPUT); pinMode(WHEEL_Y_IN2, OUTPUT);
  pinMode(WHEEL_Z_EN, OUTPUT); pinMode(WHEEL_Z_IN1, OUTPUT); pinMode(WHEEL_Z_IN2, OUTPUT);

  // All wheels stop at boot
  setWheel(WHEEL_X_EN, WHEEL_X_IN1, WHEEL_X_IN2, 0);
  setWheel(WHEEL_Y_EN, WHEEL_Y_IN1, WHEEL_Y_IN2, 0);
  setWheel(WHEEL_Z_EN, WHEEL_Z_IN1, WHEEL_Z_IN2, 0);

  // MPU6050
  Wire.begin();
  if (!mpu.begin()) {
    Serial.println("[ADCS ERROR] MPU6050 not found!");
    while (1) delay(100);
  }
  mpu.setAccelerometerRange(MPU6050_RANGE_2_G);
  mpu.setGyroRange(MPU6050_RANGE_250_DEG);
  mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);

  lastTime = millis();
  Serial.println("[ADCS] Boot OK");
}

// ── Loop ──────────────────────────────────────────────────────────────────────
void loop() {
  // 1. Feed GPS
  while (gpsSerial.available()) {
    gps.encode(gpsSerial.read());
  }

  // 2. Read IMU
  sensors_event_t accel, gyro, temp;
  mpu.getEvent(&accel, &gyro, &temp);

  unsigned long now     = millis();
  float         dt      = (now - lastTime) / 1000.0f;
  lastTime = now;

  // Complementary filter for roll and pitch (accelerometer + gyro)
  float accRoll  =  atan2(accel.acceleration.y, accel.acceleration.z) * 180.0 / PI;
  float accPitch = -atan2(accel.acceleration.x, accel.acceleration.z) * 180.0 / PI;

  float alpha = 0.96f;
  roll  = alpha * (roll  + gyro.gyro.x * dt * 180.0 / PI) + (1 - alpha) * accRoll;
  pitch = alpha * (pitch + gyro.gyro.y * dt * 180.0 / PI) + (1 - alpha) * accPitch;

  // Yaw: gyro integration only (magnetometer-free)
  yaw += gyro.gyro.z * dt * 180.0 / PI;
  if (yaw >  180) yaw -= 360;
  if (yaw < -180) yaw += 360;

  // 3. Read GPS fix
  double lat = 0, lon = 0, alt = 0;
  if (gps.location.isValid()) {
    lat = gps.location.lat();
    lon = gps.location.lng();
  }
  if (gps.altitude.isValid()) {
    alt = gps.altitude.meters();
  }

  // 4. Send telemetry line (parsed by backend parse_adcs_packet)
  //    Format: ADCS:<roll>,<pitch>,<yaw>,<lat>,<lon>,<alt>,<wx>,<wy>,<wz>
  Serial.print("ADCS:");
  Serial.print(roll,  2); Serial.print(",");
  Serial.print(pitch, 2); Serial.print(",");
  Serial.print(yaw,   2); Serial.print(",");
  Serial.print(lat,   6); Serial.print(",");
  Serial.print(lon,   6); Serial.print(",");
  Serial.print(alt,   2); Serial.print(",");
  Serial.print(wheelX);   Serial.print(",");
  Serial.print(wheelY);   Serial.print(",");
  Serial.println(wheelZ);

  // 5. Check for commands from PC
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    parseCommand(cmd);
  }

  delay(50);  // ~20 Hz
}

// ── Command Parser ────────────────────────────────────────────────────────────
void parseCommand(const String& cmd) {
  // Format: WHEEL:X,<speed>  (speed: -255..255)
  if (cmd.startsWith("WHEEL:")) {
    String body = cmd.substring(6);  // after "WHEEL:"
    int    comma = body.indexOf(',');
    if (comma < 0) return;

    char   axis  = body.charAt(0);
    int    speed = body.substring(comma + 1).toInt();

    switch (axis) {
      case 'X':
        wheelX = speed;
        setWheel(WHEEL_X_EN, WHEEL_X_IN1, WHEEL_X_IN2, speed);
        break;
      case 'Y':
        wheelY = speed;
        setWheel(WHEEL_Y_EN, WHEEL_Y_IN1, WHEEL_Y_IN2, speed);
        break;
      case 'Z':
        wheelZ = speed;
        setWheel(WHEEL_Z_EN, WHEEL_Z_IN1, WHEEL_Z_IN2, speed);
        break;
    }
    Serial.print("[ADCS] Wheel ");
    Serial.print(axis);
    Serial.print(" set to ");
    Serial.println(speed);
  }
}

/** Web Serial direct-connect — ported from the legacy app's `web_serial.js`.
 * Lets a student's own Chrome/Edge tab talk straight to the ESP32 over USB,
 * no on-site agent required. Parsed frames are POSTed to
 * `/ground-station/devices/{id}/telemetry/browser` so every other viewer
 * still sees them, same as the agent's path. */

export interface SerialCallbacks {
  onTelemetry?: (entry: { src: string; timestamp: number; data: Record<string, unknown> }) => void;
  onAdcsTelemetry?: (entry: {
    roll: number; pitch: number; yaw: number;
    lat: number | null; lon: number | null; alt: number | null;
  }) => void;
  onSerialRx?: (line: { line: string; ts: number; dir: "rx" }) => void;
  onSerialTx?: (line: { line: string; ts: number; dir: "tx" }) => void;
  onConnect?: (port: SerialPort) => void;
  onDisconnect?: () => void;
}

let serialPort: SerialPort | null = null;
let serialWriter: WritableStreamDefaultWriter<string> | null = null;
let serialReader: ReadableStreamDefaultReader<string> | null = null;
let readerKeepAlive = true;

export function isWebSerialSupported(): boolean {
  return "serial" in navigator;
}

export function isWebSerialConnected(): boolean {
  return serialPort !== null;
}

export async function connectWebSerial(callbacks: SerialCallbacks): Promise<boolean> {
  if (!isWebSerialSupported()) {
    throw new Error("Web Serial API is not supported in this browser. Please use Chrome or Edge.");
  }

  serialPort = await navigator.serial.requestPort();
  await serialPort.open({ baudRate: 115200 });

  callbacks.onConnect?.(serialPort);

  readerKeepAlive = true;
  void readLoop(callbacks);

  return true;
}

export async function disconnectWebSerial(callbacks?: SerialCallbacks): Promise<void> {
  readerKeepAlive = false;

  if (serialReader) {
    try { await serialReader.cancel(); } catch { /* already closed */ }
  }
  if (serialWriter) {
    try { await serialWriter.close(); } catch { /* already closed */ }
  }
  if (serialPort) {
    try { await serialPort.close(); } catch { /* already closed */ }
  }

  serialPort = null;
  serialReader = null;
  serialWriter = null;

  callbacks?.onDisconnect?.();
}

async function readLoop(callbacks: SerialCallbacks): Promise<void> {
  if (!serialPort?.readable) return;
  const textDecoder = new TextDecoderStream();
  const readableStreamClosed = serialPort.readable.pipeTo(textDecoder.writable);
  serialReader = textDecoder.readable.getReader();

  let buffer = "";

  try {
    while (readerKeepAlive) {
      const { value, done } = await serialReader.read();
      if (done) break;

      buffer += value;

      let newlineIndex: number;
      while ((newlineIndex = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, newlineIndex).trim();
        buffer = buffer.slice(newlineIndex + 1);
        if (!line) continue;

        callbacks.onSerialRx?.({ line, ts: Math.floor(Date.now() / 1000), dir: "rx" });
        parseTelemetryLine(line, callbacks);
      }
    }
  } catch (error) {
    console.error("Serial Read Error:", error);
  } finally {
    serialReader?.releaseLock();
    void readableStreamClosed.catch(() => undefined);
  }
}

function finiteNum(v: unknown): number | undefined {
  if (v === null || v === undefined || v === "") return undefined;
  const n = Number(v);
  return Number.isFinite(n) ? n : undefined;
}

/** Normalize any telemetry object — whether flat Ground Station JSON,
 * nested AlFalaj_CDHS `/api/telemetry` JSON, or partial sensor JSON — into
 * the unified flat record that DeviceConsole and the backend ingest expect. */
export function normalizeTelemetryPayload(raw: Record<string, unknown>): Record<string, unknown> | null {
  const imu = (raw.imu && typeof raw.imu === "object" ? raw.imu : {}) as Record<string, unknown>;
  const mag = (raw.mag && typeof raw.mag === "object" ? raw.mag : {}) as Record<string, unknown>;
  const tempObj = (raw.temp && typeof raw.temp === "object" ? raw.temp : {}) as Record<string, unknown>;
  const powerObj = (raw.power && typeof raw.power === "object" ? raw.power : {}) as Record<string, unknown>;
  const gps = (raw.gps && typeof raw.gps === "object" ? raw.gps : {}) as Record<string, unknown>;
  const wifi = (raw.wifi && typeof raw.wifi === "object" ? raw.wifi : {}) as Record<string, unknown>;
  const sys = (raw.sys && typeof raw.sys === "object" ? raw.sys : {}) as Record<string, unknown>;

  const temp =
    finiteNum(raw.temp) ??
    finiteNum(raw.temp_C) ??
    finiteNum(tempObj.c) ??
    finiteNum(imu.temp_c) ??
    finiteNum(sys.cpu_c);

  const voltage =
    finiteNum(raw.voltage) ??
    finiteNum(raw.bus_voltage_V) ??
    finiteNum(raw.bus_v) ??
    finiteNum(powerObj.bus_v);

  // AlFalaj reports `power.ma` in mA; GroundStationPage chart displays Current in A
  const rawCurrentA = finiteNum(raw.current) ?? finiteNum(raw.current_A);
  const rawCurrentMa = finiteNum(raw.current_mA) ?? finiteNum(raw.ma) ?? finiteNum(powerObj.ma);
  const current = rawCurrentA ?? (rawCurrentMa !== undefined ? Math.round((rawCurrentMa / 1000) * 10000) / 10000 : undefined);

  const power =
    finiteNum(raw.power) ??
    finiteNum(raw.power_mW) ??
    finiteNum(raw.mw) ??
    finiteNum(powerObj.mw) ??
    (voltage !== undefined && current !== undefined ? Math.round(voltage * current * 1000 * 100) / 100 : undefined);

  const rssi = finiteNum(raw.rssi) ?? finiteNum(wifi.rssi);
  const snr = finiteNum(raw.snr);
  const roll = finiteNum(raw.roll) ?? finiteNum(imu.roll);
  const pitch = finiteNum(raw.pitch) ?? finiteNum(imu.pitch);
  const yaw = finiteNum(raw.yaw) ?? finiteNum(raw.heading) ?? finiteNum(mag.heading) ?? finiteNum(imu.gz);

  const rawLat = finiteNum(raw.lat) ?? finiteNum(gps.lat);
  const rawLon = finiteNum(raw.lon) ?? finiteNum(raw.lng) ?? finiteNum(gps.lon);
  const rawAlt = finiteNum(raw.alt) ?? finiteNum(gps.alt);
  const lat = rawLat && rawLat !== 0 ? rawLat : undefined;
  const lon = rawLon && rawLon !== 0 ? rawLon : undefined;
  const alt = rawAlt && rawAlt !== 0 ? rawAlt : undefined;

  const hasAnyMetric =
    temp !== undefined ||
    voltage !== undefined ||
    current !== undefined ||
    power !== undefined ||
    roll !== undefined ||
    pitch !== undefined ||
    yaw !== undefined ||
    raw.fw !== undefined;

  if (!hasAnyMetric) return null;

  const out: Record<string, unknown> = { ...raw };
  if (temp !== undefined) out.temp = temp;
  if (voltage !== undefined) out.voltage = voltage;
  if (current !== undefined) out.current = current;
  if (power !== undefined) out.power = power;
  if (rssi !== undefined) out.rssi = rssi;
  if (snr !== undefined) out.snr = snr;
  if (roll !== undefined) out.roll = roll;
  if (pitch !== undefined) out.pitch = pitch;
  if (yaw !== undefined) out.yaw = yaw;
  if (lat !== undefined) out.lat = lat;
  if (lon !== undefined) out.lon = lon;
  if (alt !== undefined) out.alt = alt;
  return out;
}

/** Parse plain-text serial lines from AlFalaj_Sensors.ino, e.g.:
 * "T 24.5 C | 4.248 V 158.0 mA | roll -0.5 pitch -15.3 | FRAM saving (355 records)"
 * or "T nan C | 4.248 V 158.0 mA | roll -0.5 pitch -15.3" */
function parseTextTelemetryLine(line: string): Record<string, unknown> | null {
  if (!line.includes(" V ") && !line.includes("roll ")) return null;
  const tempMatch = line.match(/T\s+([-+]?\d+(?:\.\d+)?)\s*C/i);
  const voltMatch = line.match(/([-+]?\d+(?:\.\d+)?)\s*V\b/);
  const maMatch = line.match(/([-+]?\d+(?:\.\d+)?)\s*mA\b/i);
  const rollMatch = line.match(/roll\s+([-+]?\d+(?:\.\d+)?)/i);
  const pitchMatch = line.match(/pitch\s+([-+]?\d+(?:\.\d+)?)/i);
  const yawMatch = line.match(/(?:yaw|hdg|heading)\s+([-+]?\d+(?:\.\d+)?)/i);

  const raw: Record<string, unknown> = {};
  if (tempMatch) raw.temp = Number(tempMatch[1]);
  if (voltMatch) raw.voltage = Number(voltMatch[1]);
  if (maMatch) raw.current_mA = Number(maMatch[1]);
  if (rollMatch) raw.roll = Number(rollMatch[1]);
  if (pitchMatch) raw.pitch = Number(pitchMatch[1]);
  if (yawMatch) raw.yaw = Number(yawMatch[1]);
  else if (rollMatch || pitchMatch) raw.yaw = 0;

  return normalizeTelemetryPayload(raw);
}

export function parseTelemetryLine(rawLine: string, callbacks: SerialCallbacks): void {
  let line = rawLine.trim();
  if (line.startsWith("TX: ")) line = line.slice(4).trim();
  else if (line.startsWith("TX ")) line = line.slice(3).trim();
  else if (line.startsWith("ACK TX: ")) line = line.split("ACK TX: ")[1]?.trim() ?? line;

  const timestamp = Math.floor(Date.now() / 1000);

  // Sanitize any unquoted `nan` or `inf` emitted by C/Arduino Serial.print(NAN)
  const sanitizedJson = line.startsWith("{")
    ? line.replace(/:\s*-?(?:nan|inf|infinity)\b/gi, ":null")
    : line;

  try {
    const parsed = JSON.parse(sanitizedJson) as Record<string, unknown>;
    const normalized = normalizeTelemetryPayload(parsed);
    if (normalized) {
      callbacks.onTelemetry?.({
        src: "CDHS_Board",
        timestamp,
        data: normalized,
      });
      if (normalized.roll !== undefined || normalized.pitch !== undefined || normalized.yaw !== undefined) {
        callbacks.onAdcsTelemetry?.({
          roll: Number(normalized.roll ?? 0),
          pitch: Number(normalized.pitch ?? 0),
          yaw: Number(normalized.yaw ?? 0),
          lat: typeof normalized.lat === "number" ? normalized.lat : null,
          lon: typeof normalized.lon === "number" ? normalized.lon : null,
          alt: typeof normalized.alt === "number" ? normalized.alt : null,
        });
      }
      return;
    }
  } catch {
    // Fall through to text telemetry parser (e.g. AlFalaj_Sensors.ino output)
  }

  const textNormalized = parseTextTelemetryLine(line);
  if (textNormalized) {
    callbacks.onTelemetry?.({
      src: "CDHS_Board",
      timestamp,
      data: textNormalized,
    });
  }
}

export async function writeSerialCommand(commandStr: string, callbacks?: SerialCallbacks): Promise<boolean> {
  if (!serialPort?.writable) {
    console.warn("Cannot write: Serial port not open");
    return false;
  }

  try {
    if (!serialWriter) {
      const textEncoder = new TextEncoderStream();
      void textEncoder.readable.pipeTo(serialPort.writable);
      serialWriter = textEncoder.writable.getWriter();
    }

    const payload = `CMD ${commandStr}\n`;
    await serialWriter.write(payload);
    callbacks?.onSerialTx?.({ line: payload.trim(), ts: Math.floor(Date.now() / 1000), dir: "tx" });
    return true;
  } catch (e) {
    console.error("Serial Write Error:", e);
    return false;
  }
}

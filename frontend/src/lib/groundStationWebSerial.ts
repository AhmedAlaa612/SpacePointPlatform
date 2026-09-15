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

function parseTelemetryLine(rawLine: string, callbacks: SerialCallbacks): void {
  let line = rawLine;
  if (line.startsWith("TX: ")) line = line.slice(4).trim();
  else if (line.startsWith("TX ")) line = line.slice(3).trim();
  else if (line.startsWith("ACK TX: ")) line = line.split("ACK TX: ")[1]?.trim() ?? line;

  try {
    const raw = JSON.parse(line) as Record<string, number | undefined>;
    const timestamp = Math.floor(Date.now() / 1000);

    if (raw.temp !== undefined && raw.voltage !== undefined) {
      const v = Number(raw.voltage || 0);
      const c = Number(raw.current || 0);
      const p = raw.power ?? Math.round(v * c * 100) / 100;

      callbacks.onTelemetry?.({
        src: "CDHS_Board", timestamp,
        data: { temp: raw.temp, voltage: v, current: c, power: p },
      });

      if (raw.yaw !== undefined) {
        callbacks.onAdcsTelemetry?.({
          roll: raw.roll || 0, pitch: raw.pitch || 0, yaw: raw.yaw || 0,
          lat: raw.lat && raw.lat !== 0 ? raw.lat : null,
          lon: raw.lng && raw.lng !== 0 ? raw.lng : null,
          alt: raw.alt && raw.alt !== 0 ? raw.alt : null,
        });
      }
    }
  } catch {
    // not a JSON telemetry line — ignore, same as the legacy parser
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

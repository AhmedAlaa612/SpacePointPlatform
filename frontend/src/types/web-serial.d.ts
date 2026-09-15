/** Minimal Web Serial API surface — only what `lib/groundStationWebSerial.ts`
 * uses. @types/w3c-web-serial ships the full spec but isn't picked up by
 * this project's tsconfig automatically; declaring the small subset we
 * actually touch here is simpler than chasing that. */
interface SerialPort extends EventTarget {
  readonly readable: ReadableStream<BufferSource> | null;
  readonly writable: WritableStream<BufferSource> | null;
  open(options: { baudRate: number }): Promise<void>;
  close(): Promise<void>;
}

interface Serial extends EventTarget {
  requestPort(): Promise<SerialPort>;
}

interface Navigator {
  readonly serial: Serial;
}

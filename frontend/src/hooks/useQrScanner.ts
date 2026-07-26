import { useCallback, useEffect, useRef, useState, type RefObject } from "react"
import { Html5Qrcode, Html5QrcodeSupportedFormats } from "html5-qrcode"

/**
 * Reusable QR camera lifecycle (extracted from the original R2-5 check-in
 * scanner so the W5 S5-1 instructor attendance scan can reuse it verbatim
 * instead of duplicating ~150 lines of camera setup/teardown).
 *
 * Strategy: try the native `BarcodeDetector` API first (fast, no extra JS,
 * Chromium-only today); fall back to the `html5-qrcode` library everywhere
 * else (most desktop browsers, iOS Safari, older Android WebViews). Both
 * paths feed the same `onDetect(rawValue)` callback — extraction of a token
 * out of that raw string is the caller's job (see `extractQrToken` below),
 * not this hook's, since what a scan "means" is domain-specific.
 */

// Not yet in the standard TS DOM lib this project targets, so it's typed
// minimally here rather than pulled from @types/dom-*.
interface NativeBarcodeDetector {
  detect: (source: CanvasImageSource) => Promise<Array<{ rawValue: string }>>
}
declare global {
  interface Window {
    BarcodeDetector?: new (options?: { formats?: string[] }) => NativeBarcodeDetector
  }
}

/** The QR encodes a full URL, {FRONTEND_URL}/t/{token} (see backend
 * services/documents/ticket.py) — never assume the raw scanned string IS the
 * token. Also usable for manual entry, since staff may paste the whole link. */
export function extractQrToken(raw: string): string {
  const trimmed = raw.trim()
  if (!trimmed) return ""
  try {
    const url = new URL(trimmed)
    const segments = url.pathname.split("/").filter(Boolean)
    const tIndex = segments.indexOf("t")
    if (tIndex !== -1 && segments[tIndex + 1]) return segments[tIndex + 1]
    // Unexpected URL shape (no literal /t/ segment) — the last path segment
    // is still a better guess than the whole URL.
    return segments.length > 0 ? segments[segments.length - 1] : trimmed
  } catch {
    // Not a URL at all — a bare token, typed or scanned from a damaged QR.
    return trimmed
  }
}

export function describeCameraError(err: unknown): string {
  const name = (err as { name?: string } | undefined)?.name
  if (name === "NotAllowedError" || name === "PermissionDeniedError") {
    return "Camera access was denied. Enable camera permission for this site in your browser settings, or use manual entry below."
  }
  if (name === "NotFoundError" || name === "DevicesNotFoundError") {
    return "No camera was found on this device. Use manual entry below."
  }
  if (name === "NotReadableError") {
    return "The camera is already in use by another app. Use manual entry below."
  }
  return "Couldn't start the camera. Use manual entry below."
}

interface UseQrScannerOptions {
  /** Camera only runs while true — flip off (e.g. no session chosen yet, or
   * navigating away) to release it. */
  enabled: boolean
  /** Fired with the raw scanned string every time a code is detected and
   * `busyRef.current` is false at that instant. */
  onDetect: (rawValue: string) => void
  /** Scans while this is true are ignored — the caller sets it while a
   * submit is in flight or a result is showing, so one QR can't fire twice. */
  busyRef: RefObject<boolean>
  /** DOM id for html5-qrcode's target element — must be unique among any
   * scanners mounted at once (there's normally only ever one). */
  readerElementId: string
}

interface UseQrScannerResult {
  videoRef: RefObject<HTMLVideoElement | null>
  scannerMode: "native" | "html5-qrcode"
  cameraError: string | null
}

export function useQrScanner({ enabled, onDetect, busyRef, readerElementId }: UseQrScannerOptions): UseQrScannerResult {
  const [cameraError, setCameraError] = useState<string | null>(null)
  const [scannerMode, setScannerMode] = useState<"native" | "html5-qrcode">(() =>
    typeof window !== "undefined" && "BarcodeDetector" in window ? "native" : "html5-qrcode",
  )

  const videoRef = useRef<HTMLVideoElement | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const detectTimerRef = useRef<number | null>(null)
  const html5QrRef = useRef<Html5Qrcode | null>(null)
  // Bumped on every (re)start so a getUserMedia promise that resolves after
  // a newer start (rapid session switches) knows to discard its stream.
  const startTokenRef = useRef(0)

  const onDetectRef = useRef(onDetect)
  onDetectRef.current = onDetect

  const stopScanner = useCallback(() => {
    if (detectTimerRef.current) {
      window.clearInterval(detectTimerRef.current)
      detectTimerRef.current = null
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop())
      streamRef.current = null
    }
    if (videoRef.current) videoRef.current.srcObject = null
    if (html5QrRef.current) {
      const instance = html5QrRef.current
      html5QrRef.current = null
      try {
        if (instance.isScanning) {
          instance
            .stop()
            .then(() => {
              try {
                instance.clear()
              } catch {
                /* best-effort teardown */
              }
            })
            .catch(() => {})
        } else {
          instance.clear()
        }
      } catch {
        /* never let a scanner teardown glitch crash the page */
      }
    }
  }, [])

  useEffect(() => {
    if (!enabled) return
    const myStart = ++startTokenRef.current
    setCameraError(null)

    async function startNative() {
      const BarcodeDetectorCtor = window.BarcodeDetector
      if (!BarcodeDetectorCtor) {
        setScannerMode("html5-qrcode")
        return
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } })
        if (myStart !== startTokenRef.current) {
          // Superseded by a newer start (e.g. enabled toggled off/on while
          // the permission prompt was open) — release this stream, do nothing else.
          stream.getTracks().forEach((t) => t.stop())
          return
        }
        streamRef.current = stream
        if (videoRef.current) {
          videoRef.current.srcObject = stream
          await videoRef.current.play().catch(() => {})
        }

        let detector: NativeBarcodeDetector
        try {
          detector = new BarcodeDetectorCtor({ formats: ["qr_code"] })
        } catch {
          // Declared on window but unusable in this browser (e.g. no
          // 'qr_code' format support) — fall back to the library instead.
          if (myStart === startTokenRef.current) setScannerMode("html5-qrcode")
          return
        }

        detectTimerRef.current = window.setInterval(() => {
          if (busyRef.current || !videoRef.current) return
          detector
            .detect(videoRef.current)
            .then((codes) => {
              if (codes.length > 0) onDetectRef.current(codes[0].rawValue)
            })
            .catch(() => {
              /* a transient mid-frame decode failure — skip this tick */
            })
        }, 300)
      } catch (err) {
        setCameraError(describeCameraError(err))
      }
    }

    async function startHtml5Qrcode() {
      try {
        const instance = new Html5Qrcode(readerElementId, {
          formatsToSupport: [Html5QrcodeSupportedFormats.QR_CODE],
          verbose: false,
        })
        html5QrRef.current = instance
        await instance.start(
          { facingMode: "environment" },
          { fps: 10, qrbox: { width: 250, height: 250 } },
          (decodedText) => {
            if (!busyRef.current) onDetectRef.current(decodedText)
          },
          () => {
            /* fires continuously while no code is in frame — not an error */
          },
        )
      } catch (err) {
        setCameraError(describeCameraError(err))
      }
    }

    if (scannerMode === "native") void startNative()
    else void startHtml5Qrcode()

    return () => {
      stopScanner()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, scannerMode, readerElementId, busyRef, stopScanner])

  return { videoRef, scannerMode, cameraError }
}

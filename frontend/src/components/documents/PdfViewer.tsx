import { useEffect, useRef, useState } from "react"
import { FileWarning, Maximize2, ZoomIn, ZoomOut } from "lucide-react"
import * as pdfjsLib from "pdfjs-dist"
import type { PDFDocumentProxy, PDFPageProxy, RenderTask } from "pdfjs-dist"
import { cn } from "@/lib/utils"
// ?url: served as a raw asset, bypassing Vite's dev-mode JS transform (which
// injects an HMR-client import that breaks once this runs inside a Worker).
import pdfjsWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url"
import "./PdfViewer.css"

// A worker bundled by pdfjs-dist itself — not the browser's own PDF plugin.
// Native <iframe>/browser PDF viewing depends on the visitor's own Chrome
// setting ("open PDFs" vs "download PDFs"); rendering to canvas ourselves
// sidesteps that entirely and works the same for every reader, and — the
// actual point — never puts a download/print control in front of them.
// Set once at module load, shared by every PdfViewer instance.
pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorkerUrl

/** A no-download inline PDF viewer: canvas-rendered, no link to the
 * underlying file anywhere in the DOM. This is friction, not DRM — the
 * browser's own screenshot/devtools/print-to-PDF still work, and nothing
 * here stops that. What it removes is the one-click "Download" a plain
 * `<a href=pdfUrl>` or a native `<iframe>` viewer would otherwise offer.
 *
 * Every page renders into its own canvas, stacked vertically in one
 * scrollable pane — a continuous scroll like a normal PDF reader, not a
 * page-at-a-time flip. The pane caps its own height at a viewport-relative
 * max (not a `flex-1`/`h-full` chain a plain, non-flex ancestor won't
 * supply) so it's self-contained: it never grows taller than the visible
 * browser window, on desktop or on a phone, regardless of what it's
 * embedded in.
 *
 * The canvas is rendered at `devicePixelRatio` — not just the CSS-pixel
 * "fit width" scale — then displayed back down at that CSS size via
 * `canvas.style.width/height`. Skipping this is why text used to look soft
 * on any HiDPI/Retina screen: a canvas backed by exactly as many pixels as
 * its CSS width has no room for the extra sharpness those screens show
 * everything else at. A transparent, absolutely-positioned text layer
 * (pdfjs-dist's own `TextLayer`, styled by PdfViewer.css) sits on top of
 * each canvas so the page is still selectable/copyable/Ctrl+F-able, even
 * though what's visible is a raster image.
 *
 * Takes an already-resolved URL (a short-lived signed one, ideally — see
 * callers) rather than fetching one itself, so it stays reusable regardless
 * of where that URL comes from.
 */
const MIN_ZOOM = 0.5
const MAX_ZOOM = 3
const ZOOM_STEP = 0.25

type TextLayerInstance = InstanceType<typeof pdfjsLib.TextLayer>

function withEncryptedPdfParam(rawUrl: string): string {
  try {
    const parsed = new URL(rawUrl, window.location.origin)
    if (parsed.pathname.includes("/files/")) {
      parsed.searchParams.set("enc", "1")
      return parsed.toString()
    }
  } catch {
    // Leave non-standard or relative URLs untouched if URL parsing fails
  }
  return rawUrl
}

async function decryptPdfBufferIfNeeded(res: Response, buffer: ArrayBuffer): Promise<Uint8Array> {
  const keyB64 = res.headers.get("X-Pdf-Key")
  const ivB64 = res.headers.get("X-Pdf-Iv")
  if (!keyB64 || !ivB64) {
    return new Uint8Array(buffer)
  }

  const rawKey = Uint8Array.from(atob(keyB64), (c) => c.charCodeAt(0))
  const iv = Uint8Array.from(atob(ivB64), (c) => c.charCodeAt(0))
  const cryptoKey = await window.crypto.subtle.importKey(
    "raw",
    rawKey,
    { name: "AES-GCM" },
    false,
    ["decrypt"],
  )
  const decrypted = await window.crypto.subtle.decrypt(
    { name: "AES-GCM", iv },
    cryptoKey,
    buffer,
  )
  return new Uint8Array(decrypted)
}

async function renderPage(
  page: PDFPageProxy,
  canvas: HTMLCanvasElement,
  wrapper: HTMLDivElement,
  textLayerEl: HTMLDivElement,
  cssScale: number,
): Promise<{ renderTask: RenderTask; textLayer: TextLayerInstance }> {
  // Cap DPR to 2 to prevent excessive GPU memory and sluggish rendering on high-DPI displays at high zoom
  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  const cssViewport = page.getViewport({ scale: cssScale })
  const renderViewport = page.getViewport({ scale: cssScale * dpr })

  const pixelWidth = Math.round(renderViewport.width)
  const pixelHeight = Math.round(renderViewport.height)

  if (canvas.width !== pixelWidth) canvas.width = pixelWidth
  if (canvas.height !== pixelHeight) canvas.height = pixelHeight

  const cssW = `${Math.round(cssViewport.width)}px`
  const cssH = `${Math.round(cssViewport.height)}px`
  canvas.style.width = cssW
  canvas.style.height = cssH
  wrapper.style.width = cssW
  wrapper.style.height = cssH
  wrapper.style.setProperty("--total-scale-factor", String(cssScale))

  const renderTask = page.render({ canvas, viewport: renderViewport })

  textLayerEl.replaceChildren()
  const textLayer = new pdfjsLib.TextLayer({
    textContentSource: page.streamTextContent({ includeMarkedContent: true, disableNormalization: true }),
    container: textLayerEl,
    viewport: cssViewport,
  })

  return { renderTask, textLayer }
}

export function PdfViewer({ url, className }: { url: string; className?: string }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const wrapperRefs = useRef<(HTMLDivElement | null)[]>([])
  const canvasRefs = useRef<(HTMLCanvasElement | null)[]>([])
  const textLayerRefs = useRef<(HTMLDivElement | null)[]>([])
  const activeRenderTasksRef = useRef<Map<number, RenderTask>>(new Map())
  const activeTextLayersRef = useRef<Map<number, TextLayerInstance>>(new Map())
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null)
  const [pdfError, setPdfError] = useState(false)
  // The "fit width" baseline — how wide the container actually is right now,
  // tracked live via ResizeObserver. Debounced and thresholded to prevent
  // feedback loops when scrollbars appear or subpixel values fluctuate.
  const [containerWidth, setContainerWidth] = useState(800)
  // Multiplies the fit-width scale — 1 means "fit width" exactly.
  const [zoom, setZoom] = useState(1)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    let timeoutId: number | null = null
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width
      if (!width || width <= 0) return
      if (timeoutId) window.clearTimeout(timeoutId)
      timeoutId = window.setTimeout(() => {
        const rounded = Math.round(width)
        setContainerWidth((prev) => (Math.abs(prev - rounded) > 4 ? rounded : prev))
      }, 60)
    })
    observer.observe(el)
    return () => {
      if (timeoutId) window.clearTimeout(timeoutId)
      observer.disconnect()
    }
  }, [])

  useEffect(() => {
    if (!url) return
    let cancelled = false
    let loadedDoc: PDFDocumentProxy | null = null
    let loadingTask: ReturnType<typeof pdfjsLib.getDocument> | null = null
    setPdfError(false)
    setDoc(null)
    setZoom(1)
    wrapperRefs.current = []
    canvasRefs.current = []
    textLayerRefs.current = []

    async function loadPdf() {
      try {
        // Fetching in the main thread bypasses web-worker CORS restrictions,
        // decrypts AES-256-GCM payloads in RAM when served by /files/, and
        // passes raw bytes directly into the worker as transferable data.
        const res = await fetch(withEncryptedPdfParam(url))
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const buffer = await res.arrayBuffer()
        if (cancelled) return
        const pdfBytes = await decryptPdfBufferIfNeeded(res, buffer)
        if (cancelled) return
        loadingTask = pdfjsLib.getDocument({ data: pdfBytes })
        const loaded = await loadingTask.promise
        if (cancelled) {
          loaded.destroy()
          return
        }
        loadedDoc = loaded
        setDoc(loaded)
      } catch (err) {
        if (cancelled) return
        console.warn("PdfViewer encrypted fetch failed, falling back to direct URL:", err)
        // Fallback: try direct URL loading with pdfjs
        try {
          loadingTask = pdfjsLib.getDocument({
            url,
            withCredentials: false,
          })
          const loaded = await loadingTask.promise
          if (cancelled) {
            loaded.destroy()
            return
          }
          loadedDoc = loaded
          setDoc(loaded)
        } catch (fallbackErr) {
          console.error("PdfViewer fallback load failed:", fallbackErr)
          if (!cancelled) setPdfError(true)
        }
      }
    }

    void loadPdf()
    return () => {
      cancelled = true
      loadingTask?.destroy()
      loadedDoc?.destroy()
    }
  }, [url])

  // Renders every page in order — canvas pixels plus matching text layer.
  // Cancels previous in-flight tasks cleanly to prevent multiple render
  // operations on the same canvas. Applies immediate CSS scaling for instant
  // visual feedback before the background high-res rasterization completes.
  useEffect(() => {
    if (!doc) return
    let cancelled = false

    // Cancel all in-flight rendering from any prior zoom/resize pass
    for (const task of activeRenderTasksRef.current.values()) {
      task.cancel()
    }
    for (const tl of activeTextLayersRef.current.values()) {
      tl.cancel()
    }

    ;(async () => {
      // Pass 1: Immediate CSS dimension update for instant 60fps responsiveness
      for (let i = 1; i <= doc.numPages; i++) {
        if (cancelled) return
        const wrapper = wrapperRefs.current[i - 1]
        const canvas = canvasRefs.current[i - 1]
        if (!wrapper || !canvas) continue
        try {
          const page = await doc.getPage(i)
          if (cancelled) return
          const unscaled = page.getViewport({ scale: 1 })
          const cssScale = (containerWidth / unscaled.width) * zoom
          const cssViewport = page.getViewport({ scale: cssScale })
          const cssW = `${Math.round(cssViewport.width)}px`
          const cssH = `${Math.round(cssViewport.height)}px`
          wrapper.style.width = cssW
          wrapper.style.height = cssH
          wrapper.style.setProperty("--total-scale-factor", String(cssScale))
          canvas.style.width = cssW
          canvas.style.height = cssH
        } catch {
          // Handled in main rasterization loop
        }
      }

      // Pass 2: High-DPI rasterization and textLayer attachment
      for (let i = 1; i <= doc.numPages; i++) {
        if (cancelled) return
        const wrapper = wrapperRefs.current[i - 1]
        const canvas = canvasRefs.current[i - 1]
        const textLayerEl = textLayerRefs.current[i - 1]
        if (!wrapper || !canvas || !textLayerEl) continue
        try {
          const page = await doc.getPage(i)
          if (cancelled) return

          // Safely wait for any prior render task on this specific canvas to finish releasing it
          const prevTask = activeRenderTasksRef.current.get(i)
          if (prevTask) {
            prevTask.cancel()
            try {
              await prevTask.promise
            } catch {
              // Expected cancellation
            }
            activeRenderTasksRef.current.delete(i)
          }

          const prevTl = activeTextLayersRef.current.get(i)
          if (prevTl) {
            prevTl.cancel()
            activeTextLayersRef.current.delete(i)
          }

          if (cancelled) return
          const unscaled = page.getViewport({ scale: 1 })
          const cssScale = (containerWidth / unscaled.width) * zoom
          const { renderTask, textLayer } = await renderPage(page, canvas, wrapper, textLayerEl, cssScale)
          activeRenderTasksRef.current.set(i, renderTask)
          activeTextLayersRef.current.set(i, textLayer)

          await Promise.all([renderTask.promise, textLayer.render()])
        } catch (err: unknown) {
          const name = (err as { name?: string })?.name
          if (!cancelled && name !== "RenderingCancelledException" && name !== "AbortException") {
            setPdfError(true)
          }
        } finally {
          activeRenderTasksRef.current.delete(i)
          activeTextLayersRef.current.delete(i)
        }
      }
    })()

    return () => {
      cancelled = true
      for (const task of activeRenderTasksRef.current.values()) {
        task.cancel()
      }
      for (const tl of activeTextLayersRef.current.values()) {
        tl.cancel()
      }
    }
  }, [doc, containerWidth, zoom])

  if (pdfError) {
    return (
      <div className="flex items-center gap-2 p-4 rounded-2xl ring-1 ring-destructive/30 bg-destructive/5 text-destructive text-sm">
        <FileWarning className="size-4 shrink-0" /> Couldn't load this document.
      </div>
    )
  }

  return (
    <div className={cn("flex flex-col gap-3 min-w-0 max-w-full", className)}>
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-1">
          <button
            type="button"
            disabled={zoom <= MIN_ZOOM}
            onClick={() => setZoom((z) => Math.max(MIN_ZOOM, +(z - ZOOM_STEP).toFixed(2)))}
            className="inline-flex items-center justify-center size-8 border border-border text-foreground rounded-lg hover:bg-muted disabled:opacity-40 disabled:pointer-events-none"
            title="Zoom out"
          >
            <ZoomOut className="size-4" />
          </button>
          <span className="text-xs text-muted-foreground w-11 text-center tabular-nums">{Math.round(zoom * 100)}%</span>
          <button
            type="button"
            disabled={zoom >= MAX_ZOOM}
            onClick={() => setZoom((z) => Math.min(MAX_ZOOM, +(z + ZOOM_STEP).toFixed(2)))}
            className="inline-flex items-center justify-center size-8 border border-border text-foreground rounded-lg hover:bg-muted disabled:opacity-40 disabled:pointer-events-none"
            title="Zoom in"
          >
            <ZoomIn className="size-4" />
          </button>
          <button
            type="button"
            onClick={() => setZoom(1)}
            disabled={zoom === 1}
            className="inline-flex items-center justify-center size-8 border border-border text-foreground rounded-lg hover:bg-muted disabled:opacity-40 disabled:pointer-events-none"
            title="Fit width"
          >
            <Maximize2 className="size-4" />
          </button>
        </div>
        {doc && doc.numPages > 1 && (
          <p className="text-xs text-muted-foreground whitespace-nowrap">{doc.numPages} pages</p>
        )}
      </div>
      <div
        ref={containerRef}
        className="w-full flex-1 min-h-0 max-h-[80vh] overflow-auto rounded-2xl ring-1 ring-border bg-card p-3 min-w-0"
      >
        {!doc && <p className="text-sm text-muted-foreground py-16 text-center">Loading document...</p>}
        {doc && (
          <div className="flex flex-col items-center min-w-full w-fit gap-3 mx-auto">
            {Array.from({ length: doc.numPages }, (_, i) => (
              <div
                key={i}
                ref={(el) => { wrapperRefs.current[i] = el }}
                className="relative shadow-md shrink-0 bg-white"
              >
                <canvas ref={(el) => { canvasRefs.current[i] = el }} className="block" />
                <div ref={(el) => { textLayerRefs.current[i] = el }} className="textLayer" />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

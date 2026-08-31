import { useEffect, useRef, useState } from "react"
import { ChevronLeft, ChevronRight, FileWarning, Maximize2, ZoomIn, ZoomOut } from "lucide-react"
import * as pdfjsLib from "pdfjs-dist"
import type { PDFDocumentProxy, RenderTask } from "pdfjs-dist"
// ?url: served as a raw asset, bypassing Vite's dev-mode JS transform (which
// injects an HMR-client import that breaks once this runs inside a Worker).
import pdfjsWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url"

// A worker bundled by pdfjs-dist itself — not the browser's own PDF plugin.
// Native <iframe>/browser PDF viewing depends on the visitor's own Chrome
// setting ("open PDFs" vs "download PDFs"); rendering to canvas ourselves
// sidesteps that entirely and works the same for every reader, and — the
// actual point — never puts a download/print control in front of them.
// Set once at module load, shared by every PdfViewer instance.
pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorkerUrl

/** A no-download inline PDF viewer: canvas-rendered, paginated, no link to
 * the underlying file anywhere in the DOM. This is friction, not DRM — the
 * browser's own screenshot/devtools/print-to-PDF still work, and nothing
 * here stops that. What it removes is the one-click "Download" a plain
 * `<a href=pdfUrl>` or a native `<iframe>` viewer would otherwise offer.
 *
 * Takes an already-resolved URL (a short-lived signed one, ideally — see
 * callers) rather than fetching one itself, so it stays reusable regardless
 * of where that URL comes from.
 */
const MIN_ZOOM = 0.5
const MAX_ZOOM = 3
const ZOOM_STEP = 0.25

export function PdfViewer({ url, className }: { url: string; className?: string }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null)
  const [pageNum, setPageNum] = useState(1)
  const [pdfError, setPdfError] = useState(false)
  // The "fit width" baseline — how wide the container actually is right now,
  // not a one-time read at mount. Tracked live via ResizeObserver so the
  // page re-fits correctly whether the container was still animating open
  // (a Dialog's enter transition) when the doc first loaded, or the window
  // is resized afterward.
  const [containerWidth, setContainerWidth] = useState(800)
  // Multiplies the fit-width scale — 1 means "fit width" exactly, same as
  // before zoom controls existed.
  const [zoom, setZoom] = useState(1)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width
      if (width) setContainerWidth(width)
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (!url) return
    let cancelled = false
    let loadedDoc: PDFDocumentProxy | null = null
    setPdfError(false)
    setDoc(null)
    setZoom(1)
    const loadingTask = pdfjsLib.getDocument(url)
    loadingTask.promise.then((loaded) => {
      if (cancelled) { loaded.destroy(); return }
      loadedDoc = loaded
      setDoc(loaded)
      setPageNum(1)
    }).catch(() => { if (!cancelled) setPdfError(true) })
    return () => {
      cancelled = true
      loadedDoc?.destroy()
    }
  }, [url])

  // The RenderTask must be explicitly .cancel()'d in cleanup (not just
  // ignored via a `cancelled` flag) — pdfjs only auto-supersedes a prior
  // render on the same canvas if the earlier task is properly cancelled
  // first; otherwise a second render() on the same canvas (e.g. React
  // StrictMode's double-invoke in dev) leaves the worker's queue stuck and
  // the new task never resolves.
  useEffect(() => {
    const canvas = canvasRef.current
    if (!doc || !canvas) return
    let cancelled = false
    let renderTask: RenderTask | null = null
    doc.getPage(pageNum).then((page) => {
      if (cancelled) return
      const unscaled = page.getViewport({ scale: 1 })
      const viewport = page.getViewport({ scale: (containerWidth / unscaled.width) * zoom })
      canvas.width = viewport.width
      canvas.height = viewport.height
      renderTask = page.render({ canvas, viewport })
      renderTask.promise.catch((err) => {
        if (!cancelled && err?.name !== "RenderingCancelledException") setPdfError(true)
      })
    }).catch(() => { if (!cancelled) setPdfError(true) })
    return () => {
      cancelled = true
      renderTask?.cancel()
    }
  }, [doc, pageNum, containerWidth, zoom])

  if (pdfError) {
    return (
      <div className="flex items-center gap-2 p-4 rounded-2xl ring-1 ring-destructive/30 bg-destructive/5 text-destructive text-sm">
        <FileWarning className="size-4 shrink-0" /> Couldn't load this document.
      </div>
    )
  }

  return (
    <div className={className ?? "flex flex-col gap-3 h-full min-h-0"}>
      <div
        ref={containerRef}
        className="w-full flex-1 min-h-0 overflow-auto rounded-2xl ring-1 ring-border bg-card flex justify-center p-3"
      >
        {!doc && <p className="text-sm text-muted-foreground py-16">Loading document...</p>}
        <canvas ref={canvasRef} className={doc ? "h-fit" : "hidden"} />
      </div>
      {doc && (
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
          {doc.numPages > 1 && (
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={pageNum <= 1}
                onClick={() => setPageNum((p) => p - 1)}
                className="inline-flex items-center gap-1.5 h-9 px-3 border border-border text-foreground text-sm font-medium rounded-xl hover:bg-muted disabled:opacity-40 disabled:pointer-events-none"
              >
                <ChevronLeft className="size-4" /> Previous page
              </button>
              <p className="text-xs text-muted-foreground whitespace-nowrap">Page {pageNum} of {doc.numPages}</p>
              <button
                type="button"
                disabled={pageNum >= doc.numPages}
                onClick={() => setPageNum((p) => p + 1)}
                className="inline-flex items-center gap-1.5 h-9 px-3 border border-border text-foreground text-sm font-medium rounded-xl hover:bg-muted disabled:opacity-40 disabled:pointer-events-none"
              >
                Next page <ChevronRight className="size-4" />
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

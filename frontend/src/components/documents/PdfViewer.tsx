import { useEffect, useRef, useState } from "react"
import { FileWarning, Maximize2, ZoomIn, ZoomOut } from "lucide-react"
import * as pdfjsLib from "pdfjs-dist"
import type { PDFDocumentProxy, PDFPageProxy, RenderTask } from "pdfjs-dist"
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

async function renderPage(
  page: PDFPageProxy, canvas: HTMLCanvasElement, wrapper: HTMLDivElement, textLayerEl: HTMLDivElement,
  cssScale: number,
): Promise<{ renderTask: RenderTask; textLayer: TextLayerInstance }> {
  const dpr = window.devicePixelRatio || 1
  const cssViewport = page.getViewport({ scale: cssScale })
  const renderViewport = page.getViewport({ scale: cssScale * dpr })

  canvas.width = renderViewport.width
  canvas.height = renderViewport.height
  canvas.style.width = `${cssViewport.width}px`
  canvas.style.height = `${cssViewport.height}px`
  wrapper.style.width = `${cssViewport.width}px`
  wrapper.style.height = `${cssViewport.height}px`
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
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null)
  const [pdfError, setPdfError] = useState(false)
  // The "fit width" baseline — how wide the container actually is right now,
  // not a one-time read at mount. Tracked live via ResizeObserver so pages
  // re-fit correctly whether the container was still animating open (a
  // Dialog's enter transition) when the doc first loaded, or the window is
  // resized afterward.
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
    wrapperRefs.current = []
    canvasRefs.current = []
    textLayerRefs.current = []
    const loadingTask = pdfjsLib.getDocument(url)
    loadingTask.promise.then((loaded) => {
      if (cancelled) { loaded.destroy(); return }
      loadedDoc = loaded
      setDoc(loaded)
    }).catch(() => { if (!cancelled) setPdfError(true) })
    return () => {
      cancelled = true
      loadedDoc?.destroy()
    }
  }, [url])

  // Renders every page in order — canvas pixels plus its matching text
  // layer. Sequential (each awaited before the next starts) rather than
  // firing numPages renders at once — pdf.js handles one in-flight render
  // fine, a couple dozen concurrent ones on the same worker is the kind of
  // thing that's fine until it isn't. Both the RenderTask and the TextLayer
  // are tracked and cancelled on cleanup — pdf.js only auto-supersedes a
  // properly-cancelled prior task, so leaving one running (e.g. React
  // StrictMode's double-invoke in dev, or zoom changing mid-render) leaves
  // the worker's queue stuck.
  useEffect(() => {
    if (!doc) return
    let cancelled = false
    const renderTasks: RenderTask[] = []
    const textLayers: TextLayerInstance[] = []
    ;(async () => {
      for (let i = 1; i <= doc.numPages; i++) {
        if (cancelled) return
        const wrapper = wrapperRefs.current[i - 1]
        const canvas = canvasRefs.current[i - 1]
        const textLayerEl = textLayerRefs.current[i - 1]
        if (!wrapper || !canvas || !textLayerEl) continue
        try {
          const page = await doc.getPage(i)
          if (cancelled) return
          const unscaled = page.getViewport({ scale: 1 })
          const cssScale = (containerWidth / unscaled.width) * zoom
          const { renderTask, textLayer } = await renderPage(page, canvas, wrapper, textLayerEl, cssScale)
          renderTasks.push(renderTask)
          textLayers.push(textLayer)
          await Promise.all([renderTask.promise, textLayer.render()])
        } catch (err: unknown) {
          if (!cancelled && (err as { name?: string })?.name !== "RenderingCancelledException") setPdfError(true)
        }
      }
    })()
    return () => {
      cancelled = true
      renderTasks.forEach((t) => t.cancel())
      textLayers.forEach((t) => t.cancel())
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
    <div className={className ?? "flex flex-col gap-3"}>
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
        className="w-full flex-1 min-h-0 max-h-[80vh] overflow-y-auto rounded-2xl ring-1 ring-border bg-card flex flex-col items-center gap-3 p-3"
      >
        {!doc && <p className="text-sm text-muted-foreground py-16">Loading document...</p>}
        {doc && Array.from({ length: doc.numPages }, (_, i) => (
          <div
            key={i}
            ref={(el) => { wrapperRefs.current[i] = el }}
            className="relative max-w-full shadow-sm shrink-0"
          >
            <canvas ref={(el) => { canvasRefs.current[i] = el }} className="block max-w-full" />
            <div ref={(el) => { textLayerRefs.current[i] = el }} className="textLayer" />
          </div>
        ))}
      </div>
    </div>
  )
}

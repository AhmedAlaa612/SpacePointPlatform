import { useState, useRef, useCallback, useEffect } from "react"
import ReactCrop, { type Crop, type PixelCrop, type PercentCrop } from "react-image-crop"
import "react-image-crop/dist/ReactCrop.css"
import { Eye, Crop as CropIcon, Check, RotateCcw, ZoomIn, ZoomOut, Loader2 } from "lucide-react"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"

export interface ImageCropModalProps {
  isOpen: boolean
  onClose: () => void
  imageSrc: string | null
  title?: string
  /** Lock the crop to a fixed aspect ratio, e.g. 1 for square, 16/9 for widescreen. Freeform by default. */
  aspect?: number
  /** Show the LMS-style preview tab (default: true). Pass false for non-LMS contexts. */
  showPreview?: boolean
  programName?: string
  onCropComplete: (file: File) => Promise<void> | void
  isUploading?: boolean
}

/** Helper: Generate cropped canvas output with 100% original quality (lossless PNG, no compression) */
async function getCroppedFileAndDataUrl(
  image: HTMLImageElement,
  crop: PixelCrop,
  fileName = "banner.png"
): Promise<{ file: File; dataUrl: string }> {
  const canvas = document.createElement("canvas")
  const scaleX = image.naturalWidth / image.width
  const scaleY = image.naturalHeight / image.height

  const cropX = Math.max(0, Math.min(Math.round(crop.x * scaleX), image.naturalWidth - 1))
  const cropY = Math.max(0, Math.min(Math.round(crop.y * scaleY), image.naturalHeight - 1))
  const cropWidth = Math.max(1, Math.min(Math.round(crop.width * scaleX), image.naturalWidth - cropX))
  const cropHeight = Math.max(1, Math.min(Math.round(crop.height * scaleY), image.naturalHeight - cropY))

  // Exact 1-to-1 pixel dimensions from the original high-resolution source image
  canvas.width = cropWidth
  canvas.height = cropHeight

  const ctx = canvas.getContext("2d")
  if (!ctx) {
    throw new Error("Could not create 2D canvas context")
  }

  ctx.imageSmoothingEnabled = true
  ctx.imageSmoothingQuality = "high"

  // 1:1 pixel mapping: source width/height to destination width/height with zero downsampling
  ctx.drawImage(
    image,
    cropX,
    cropY,
    cropWidth,
    cropHeight,
    0,
    0,
    cropWidth,
    cropHeight
  )

  // 100% Lossless PNG (zero compression loss of any kind)
  const dataUrl = canvas.toDataURL("image/png")

  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (!blob) {
          reject(new Error("Canvas export produced an empty blob"))
          return
        }
        const file = new File([blob], fileName, { type: "image/png" })
        resolve({ file, dataUrl })
      },
      "image/png"
    )
  })
}

export function ImageCropModal({
  isOpen,
  onClose,
  imageSrc,
  title = "Crop Image",
  aspect,
  showPreview = true,
  programName = "Program Checklist",
  onCropComplete,
  isUploading = false,
}: ImageCropModalProps) {
  const imgRef = useRef<HTMLImageElement | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [crop, setCrop] = useState<Crop>()
  const [completedCrop, setCompletedCrop] = useState<PixelCrop | null>(null)

  const [zoom, setZoom] = useState(1)
  const [baseDimensions, setBaseDimensions] = useState<{ width: number; height: number } | null>(null)
  const [isPanning, setIsPanning] = useState(false)
  const zoomRef = useRef(zoom)
  zoomRef.current = zoom
  const baseDimensionsRef = useRef(baseDimensions)
  baseDimensionsRef.current = baseDimensions
  const panStartRef = useRef<{ x: number; y: number; scrollLeft: number; scrollTop: number } | null>(null)

  const [activeTab, setActiveTab] = useState<"crop" | "preview">("crop")
  const [previewDataUrl, setPreviewDataUrl] = useState<string | null>(null)
  const [previewFile, setPreviewFile] = useState<File | null>(null)
  const [isGeneratingPreview, setIsGeneratingPreview] = useState(false)

  // Auto-redirect to Crop tab and clear previous preview/zoom cache whenever opening or changing image
  useEffect(() => {
    if (isOpen) {
      setActiveTab("crop")
      setPreviewDataUrl(null)
      setPreviewFile(null)
      setZoom(1)
      setBaseDimensions(null)
      baseDimensionsRef.current = null
    }
  }, [isOpen, imageSrc])

  const handleZoomChange = useCallback((newZoom: number) => {
    const clampedZoom = Math.min(3, Math.max(1, Math.round(newZoom * 100) / 100))
    if (clampedZoom === zoomRef.current) return

    const container = containerRef.current
    const img = imgRef.current

    if (clampedZoom === 1) {
      setBaseDimensions(null)
      baseDimensionsRef.current = null
      setZoom(1)
      return
    }

    if (!baseDimensionsRef.current && img) {
      const initialDims = { width: img.width, height: img.height }
      setBaseDimensions(initialDims)
      baseDimensionsRef.current = initialDims
    }

    // Focal point ratio to preserve center of scroll view
    let centerX = 0.5
    let centerY = 0.5
    if (container && container.scrollWidth > container.clientWidth) {
      centerX = (container.scrollLeft + container.clientWidth / 2) / container.scrollWidth
    }
    if (container && container.scrollHeight > container.clientHeight) {
      centerY = (container.scrollTop + container.clientHeight / 2) / container.scrollHeight
    }

    setZoom(clampedZoom)

    requestAnimationFrame(() => {
      if (container) {
        container.scrollLeft = centerX * container.scrollWidth - container.clientWidth / 2
        container.scrollTop = centerY * container.scrollHeight - container.clientHeight / 2
      }
    })
  }, [])

  // Native wheel listener for trackpad pinch-to-zoom and Ctrl+Wheel
  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const onWheelNative = (e: WheelEvent) => {
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault()
        const delta = -e.deltaY * 0.005
        handleZoomChange(zoomRef.current + delta)
      }
    }

    container.addEventListener("wheel", onWheelNative, { passive: false })
    return () => container.removeEventListener("wheel", onWheelNative)
  }, [handleZoomChange])

  // Drag-to-pan handlers for zoomed view
  const handleContainerPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (zoom <= 1 || e.button !== 0) return
    const target = e.target as HTMLElement
    if (
      target.closest(".ReactCrop__crop-selection") ||
      target.closest(".ReactCrop__drag-handle") ||
      target.closest(".ReactCrop__drag-bar")
    ) {
      return
    }

    const container = containerRef.current
    if (!container) return

    panStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      scrollLeft: container.scrollLeft,
      scrollTop: container.scrollTop,
    }
    setIsPanning(true)
    try {
      container.setPointerCapture(e.pointerId)
    } catch {}
  }

  const handleContainerPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!panStartRef.current || !containerRef.current) return
    const dx = e.clientX - panStartRef.current.x
    const dy = e.clientY - panStartRef.current.y
    containerRef.current.scrollLeft = panStartRef.current.scrollLeft - dx
    containerRef.current.scrollTop = panStartRef.current.scrollTop - dy
  }

  const handleContainerPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (panStartRef.current && containerRef.current) {
      try {
        containerRef.current.releasePointerCapture(e.pointerId)
      } catch {}
      panStartRef.current = null
      setIsPanning(false)
    }
  }

  // Initialize crop when image loads in the DOM
  const onImageLoad = useCallback((e: React.SyntheticEvent<HTMLImageElement>) => {
    const { width, height } = e.currentTarget
    imgRef.current = e.currentTarget
    setBaseDimensions(null)
    baseDimensionsRef.current = null
    setZoom(1)

    if (aspect) {
      // Fit the largest centered rectangle that matches the requested aspect ratio
      let cropW: number, cropH: number
      if (width / height > aspect) {
        cropH = height
        cropW = height * aspect
      } else {
        cropW = width
        cropH = width / aspect
      }
      const x = (width - cropW) / 2
      const y = (height - cropH) / 2
      setCrop({
        unit: "%",
        x: (x / width) * 100,
        y: (y / height) * 100,
        width: (cropW / width) * 100,
        height: (cropH / height) * 100,
      })
      setCompletedCrop({ unit: "px", x, y, width: cropW, height: cropH })
    } else {
      setCrop({ unit: "%", x: 0, y: 0, width: 100, height: 100 })
      setCompletedCrop({ unit: "px", x: 0, y: 0, width, height })
    }
  }, [aspect])

  const resetCropToFull = () => {
    setZoom(1)
    setBaseDimensions(null)
    baseDimensionsRef.current = null
    if (!imgRef.current) return
    const { width, height } = imgRef.current

    if (aspect) {
      let cropW: number, cropH: number
      if (width / height > aspect) {
        cropH = height
        cropW = height * aspect
      } else {
        cropW = width
        cropH = width / aspect
      }
      const x = (width - cropW) / 2
      const y = (height - cropH) / 2
      setCrop({
        unit: "%",
        x: (x / width) * 100,
        y: (y / height) * 100,
        width: (cropW / width) * 100,
        height: (cropH / height) * 100,
      })
      setCompletedCrop({ unit: "px", x, y, width: cropW, height: cropH })
    } else {
      setCrop({ unit: "%", x: 0, y: 0, width: 100, height: 100 })
      setCompletedCrop({ unit: "px", x: 0, y: 0, width, height })
    }
    setPreviewFile(null)
    setPreviewDataUrl(null)
  }

  const getEffectivePixelCrop = (): PixelCrop | null => {
    if (!imgRef.current) return null
    const { width, height } = imgRef.current
    if (!width || !height) return null

    if (crop && crop.width > 0 && crop.height > 0) {
      if (crop.unit === "%") {
        return {
          unit: "px",
          x: Math.round((crop.x * width) / 100),
          y: Math.round((crop.y * height) / 100),
          width: Math.max(1, Math.round((crop.width * width) / 100)),
          height: Math.max(1, Math.round((crop.height * height) / 100)),
        }
      }
      return {
        unit: "px",
        x: Math.round(crop.x),
        y: Math.round(crop.y),
        width: Math.max(1, Math.round(crop.width)),
        height: Math.max(1, Math.round(crop.height)),
      }
    }

    if (completedCrop && completedCrop.width > 0 && completedCrop.height > 0) {
      return completedCrop
    }

    return {
      unit: "px",
      x: 0,
      y: 0,
      width,
      height,
    }
  }

  const handleSwitchToPreview = async () => {
    if (!imgRef.current) return
    const effectiveCrop = getEffectivePixelCrop()
    if (!effectiveCrop) return

    setIsGeneratingPreview(true)
    try {
      const { file, dataUrl } = await getCroppedFileAndDataUrl(imgRef.current, effectiveCrop)
      setPreviewDataUrl(dataUrl)
      setPreviewFile(file)
      setActiveTab("preview")
    } catch (err) {
      console.error("Failed to generate preview:", err)
    } finally {
      setIsGeneratingPreview(false)
    }
  }

  const handleApply = async () => {
    // If we are in preview and already generated the cropped file, apply it immediately!
    if (activeTab === "preview" && previewFile) {
      await onCropComplete(previewFile)
      return
    }

    if (!imgRef.current) return
    const effectiveCrop = getEffectivePixelCrop()
    if (!effectiveCrop) return

    try {
      const { file } = await getCroppedFileAndDataUrl(imgRef.current, effectiveCrop)
      await onCropComplete(file)
    } catch (err) {
      console.error("Failed to crop image:", err)
    }
  }

  if (!imageSrc) return null

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && !isUploading && onClose()}>
      <DialogContent className="max-w-3xl w-[96vw] sm:w-[92vw] p-0 overflow-hidden bg-card border-border rounded-2xl flex flex-col max-h-[92vh]">
        {/* Custom CSS overrides to guarantee 4-sided touch handles work seamlessly on mobile */}
        <style>{`
          .ReactCrop .ord-n, .ReactCrop .ord-e, .ReactCrop .ord-s, .ReactCrop .ord-w {
            display: block !important;
          }
          .ReactCrop__drag-handle {
            width: 12px;
            height: 12px;
            background-color: hsl(var(--primary));
            border: 2px solid #ffffff;
            border-radius: 3px;
          }
          .ReactCrop.is-zoomed {
            max-width: none !important;
            display: block !important;
          }
          .ReactCrop.is-zoomed .ReactCrop__child-wrapper {
            max-height: none !important;
            overflow: visible !important;
          }
          .ReactCrop.is-zoomed .ReactCrop__child-wrapper > img {
            max-width: none !important;
            max-height: none !important;
          }
          @media (pointer: coarse) {
            .ReactCrop .ord-n, .ReactCrop .ord-e, .ReactCrop .ord-s, .ReactCrop .ord-w {
              display: block !important;
            }
            .ReactCrop__drag-handle {
              width: 22px !important;
              height: 22px !important;
              border-radius: 4px !important;
            }
            .ReactCrop__drag-bar.ord-n, .ReactCrop__drag-bar.ord-s {
              height: 14px !important;
            }
            .ReactCrop__drag-bar.ord-e, .ReactCrop__drag-bar.ord-w {
              width: 14px !important;
            }
          }
        `}</style>

        {/* Header */}
        <DialogHeader className="px-4 sm:px-5 py-3 border-b border-border flex flex-row items-center justify-between shrink-0">
          <DialogTitle className="text-sm sm:text-base font-bold">
            {title}
          </DialogTitle>

          {/* Mode Switcher: Only shown when a preview context exists (e.g. LMS banner) */}
          {showPreview && (
            <div className="flex items-center gap-1 bg-muted p-0.5 rounded-xl">
              <button
                type="button"
                onClick={() => setActiveTab("crop")}
                className={`min-h-[34px] px-3 py-1 text-xs font-medium rounded-lg flex items-center gap-1.5 transition-colors cursor-pointer ${
                  activeTab === "crop"
                    ? "bg-card text-foreground shadow-xs font-semibold"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <CropIcon className="w-3.5 h-3.5" />
                <span>Crop</span>
              </button>
              <button
                type="button"
                onClick={handleSwitchToPreview}
                disabled={isGeneratingPreview}
                className={`min-h-[34px] px-3 py-1 text-xs font-medium rounded-lg flex items-center gap-1.5 transition-colors cursor-pointer ${
                  activeTab === "preview"
                    ? "bg-card text-foreground shadow-xs font-semibold"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {isGeneratingPreview ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Eye className="w-3.5 h-3.5 text-primary" />
                )}
                <span>Preview</span>
              </button>
            </div>
          )}
        </DialogHeader>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto">
          {/* ── CROP TAB (4-sided freeform drag) ────────────────────── */}
          <div className={activeTab === "crop" ? "flex flex-col" : "hidden"}>
            {/* Informative helper bar */}
            {/* Informative helper bar & zoom controls */}
            <div className="px-4 py-2 bg-muted/30 border-b border-border flex items-center justify-between text-xs text-muted-foreground gap-2 flex-wrap">
              <span className="hidden sm:inline">Drag to crop{zoom > 1 ? " • Pan to move" : ""}</span>

              {/* Zoom Controls */}
              <div className="flex items-center gap-1.5 sm:gap-2 bg-muted/60 px-2 py-0.5 rounded-lg border border-border/50">
                <button
                  type="button"
                  onClick={() => handleZoomChange(zoom - 0.25)}
                  disabled={zoom <= 1}
                  title="Zoom out"
                  className="p-1 rounded hover:bg-muted text-foreground disabled:opacity-30 disabled:pointer-events-none transition-colors cursor-pointer"
                >
                  <ZoomOut className="w-3.5 h-3.5" />
                </button>

                <input
                  type="range"
                  min={1}
                  max={3}
                  step={0.05}
                  value={zoom}
                  onChange={(e) => handleZoomChange(parseFloat(e.target.value))}
                  className="w-20 sm:w-28 h-1.5 bg-border rounded-lg appearance-none cursor-pointer accent-primary"
                  title={`Zoom: ${Math.round(zoom * 100)}%`}
                />

                <button
                  type="button"
                  onClick={() => handleZoomChange(zoom + 0.25)}
                  disabled={zoom >= 3}
                  title="Zoom in"
                  className="p-1 rounded hover:bg-muted text-foreground disabled:opacity-30 disabled:pointer-events-none transition-colors cursor-pointer"
                >
                  <ZoomIn className="w-3.5 h-3.5" />
                </button>

                <button
                  type="button"
                  onClick={() => handleZoomChange(1)}
                  title="Reset zoom to 100%"
                  className="text-[11px] font-mono font-medium text-foreground hover:text-primary min-w-[34px] text-right cursor-pointer"
                >
                  {Math.round(zoom * 100)}%
                </button>
              </div>

              <button
                type="button"
                onClick={resetCropToFull}
                className="inline-flex items-center gap-1 text-primary hover:underline font-medium cursor-pointer"
              >
                <RotateCcw className="w-3 h-3" />
                <span>Reset</span>
              </button>
            </div>

            {/* Cropper Container: Image preserves natural aspect ratio with zero letterbox padding */}
            <div
              ref={containerRef}
              onPointerDown={handleContainerPointerDown}
              onPointerMove={handleContainerPointerMove}
              onPointerUp={handleContainerPointerUp}
              onPointerCancel={handleContainerPointerUp}
              className={`p-3 sm:p-5 flex bg-neutral-950 overflow-auto select-none max-h-[58vh] min-h-[260px] ${
                zoom > 1 ? (isPanning ? "cursor-grabbing" : "cursor-grab") : ""
              }`}
            >
              <div className="m-auto flex items-center justify-center">
                <ReactCrop
                  crop={crop}
                  onChange={(pixelCrop, percentCrop) => {
                    setCrop(percentCrop)
                    setCompletedCrop(pixelCrop)
                  }}
                  onComplete={(pixelCrop, percentCrop) => {
                    setCompletedCrop(pixelCrop)
                    setCrop(percentCrop)
                  }}
                  aspect={aspect}
                  keepSelection={true}
                  className={zoom > 1 ? "is-zoomed" : "max-w-full"}
                >
                  <img
                    ref={imgRef}
                    src={imageSrc}
                    alt="Source banner to crop"
                    onLoad={onImageLoad}
                    crossOrigin="anonymous"
                    draggable={false}
                    style={
                      zoom > 1 && baseDimensions
                        ? {
                            width: `${baseDimensions.width * zoom}px`,
                            height: `${baseDimensions.height * zoom}px`,
                            maxWidth: "none",
                            maxHeight: "none",
                            display: "block",
                          }
                        : {
                            maxWidth: "100%",
                            maxHeight: "52vh",
                            width: "auto",
                            height: "auto",
                            display: "block",
                          }
                    }
                  />
                </ReactCrop>
              </div>
            </div>
          </div>

          {/* ── AUTHENTIC CHECKLIST PREVIEW TAB (LMS only) ──────────── */}
          {showPreview && (
            <div className={activeTab === "preview" ? "bg-background flex flex-col min-h-[300px]" : "hidden"}>
              {/* Banner Area (Identical to RoadmapBoard.tsx line 64-73) */}
              <div className="relative w-full overflow-hidden bg-neutral-950">
                {previewDataUrl ? (
                  <img
                    src={previewDataUrl}
                    alt="Cropped banner preview"
                    className="w-full h-auto block"
                  />
                ) : (
                  <div className="h-28 flex items-center justify-center text-xs text-muted-foreground">
                    Generating preview…
                  </div>
                )}
                {/* The exact bottom lighting cue gradient from RoadmapBoard.tsx line 71 */}
                <div className="pointer-events-none absolute inset-x-0 bottom-0 h-2.5 sm:h-4 bg-[linear-gradient(to_top,hsl(var(--background)/0.7)_0%,hsl(var(--background)/0.3)_35%,hsl(var(--primary)/0.28)_65%,transparent_100%)]" />
              </div>

              {/* Checklist Board Header (Matches RoadmapBoard.tsx and user's screenshot) */}
              <div className="px-4 sm:px-6 py-4 sm:py-6 flex flex-col gap-4 max-w-[1180px] mx-auto w-full">
                <div className="flex flex-col gap-1">
                  <h1 className="font-display text-lg sm:text-xl font-extrabold tracking-tight leading-tight text-foreground">
                    {programName}
                  </h1>
                  <p className="text-xs text-muted-foreground">L1 COMP 1</p>
                  <div className="inline-flex w-fit items-center gap-1 rounded-full border border-primary/30 bg-primary/10 px-2.5 py-0.5 text-xs font-semibold text-primary">
                    Team FALCON
                  </div>
                </div>

                {/* Steps done indicator */}
                <div className="flex items-center gap-3">
                  <div className="flex items-baseline gap-1 shrink-0">
                    <span className="font-display text-xl sm:text-2xl font-extrabold text-foreground">3</span>
                    <span className="text-sm font-semibold text-muted-foreground">/10</span>
                    <span className="ml-1 whitespace-nowrap text-xs text-muted-foreground">steps done</span>
                  </div>
                  <div className="h-px flex-1 bg-border relative">
                    <div className="absolute inset-y-0 left-0 bg-primary h-full" style={{ width: "30%" }} />
                  </div>
                </div>

                {/* Your Next Task Card (Matches user screenshot) */}
                <div className="flex items-center justify-between p-3.5 rounded-xl border border-primary/40 bg-card shadow-xs">
                  <div className="flex items-center gap-2.5">
                    <div className="w-7 h-7 rounded-lg bg-primary/15 flex items-center justify-center text-primary text-xs font-bold">
                      ◎
                    </div>
                    <div className="flex flex-col">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                        YOUR NEXT TASK
                      </span>
                      <span className="text-xs sm:text-sm font-bold text-foreground">tinker</span>
                    </div>
                  </div>
                  <div className="px-2.5 py-1 text-xs font-semibold rounded-lg bg-primary text-primary-foreground">
                    Start task →
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer Actions: Simple Cancel & Apply */}
        <div className="px-4 sm:px-5 py-3 border-t border-border bg-card flex items-center justify-between gap-3 shrink-0">
          <button
            type="button"
            onClick={onClose}
            disabled={isUploading}
            className="min-h-[42px] px-4 py-2 text-xs sm:text-sm font-medium rounded-xl border border-border bg-card hover:bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
          >
            Cancel
          </button>

          <button
            type="button"
            onClick={handleApply}
            disabled={isUploading}
            className="min-h-[42px] px-6 py-2 text-xs sm:text-sm font-semibold rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 shadow-sm transition-all flex items-center justify-center gap-2 cursor-pointer"
          >
            {isUploading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Applying…</span>
              </>
            ) : (
              <>
                <Check className="w-4 h-4" />
                <span>Apply</span>
              </>
            )}
          </button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

import { useState, useRef, useCallback, useEffect } from "react"
import ReactCrop, { type Crop, type PixelCrop } from "react-image-crop"
import "react-image-crop/dist/ReactCrop.css"
import { Eye, Crop as CropIcon, Check, RotateCcw, Loader2 } from "lucide-react"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"

export interface ImageCropModalProps {
  isOpen: boolean
  onClose: () => void
  imageSrc: string | null
  title?: string
  /** Lock the crop to a fixed aspect ratio, e.g. 1 for square, 16/9 for widescreen. Freeform by default. */
  aspect?: number
  /** Crop as a circle (forces 1:1 aspect ratio). Defaults to false. */
  circularCrop?: boolean
  /** Show the LMS-style preview tab (default: true). Pass false for non-LMS contexts. */
  showPreview?: boolean
  previewMode?: "lms" | "event"
  previewBreadcrumb?: string
  programName?: string
  onCropComplete: (file: File) => Promise<void> | void
  isUploading?: boolean
}

/** Helper: Generate cropped canvas output with 100% original quality (lossless PNG, no compression) */
async function getCroppedFileAndDataUrl(
  image: HTMLImageElement,
  crop: PixelCrop,
  fileName = "image.png",
  circular = false
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

  // If circular crop, clip canvas to a circle with transparent background outside
  if (circular) {
    ctx.beginPath()
    ctx.arc(cropWidth / 2, cropHeight / 2, Math.min(cropWidth, cropHeight) / 2, 0, Math.PI * 2)
    ctx.closePath()
    ctx.clip()
  }

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
  circularCrop = false,
  showPreview = true,
  previewMode = "lms",
  previewBreadcrumb,
  programName = "Program Checklist",
  onCropComplete,
  isUploading = false,
}: ImageCropModalProps) {
  const effectiveAspect = circularCrop ? (aspect ?? 1) : aspect

  const imgRef = useRef<HTMLImageElement | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [crop, setCrop] = useState<Crop>()
  const [completedCrop, setCompletedCrop] = useState<PixelCrop | null>(null)

  const [activeTab, setActiveTab] = useState<"crop" | "preview">("crop")
  const [previewDataUrl, setPreviewDataUrl] = useState<string | null>(null)
  const [previewFile, setPreviewFile] = useState<File | null>(null)
  const [isGeneratingPreview, setIsGeneratingPreview] = useState(false)

  // Auto-redirect to Crop tab and clear previous preview whenever opening or changing image
  useEffect(() => {
    if (isOpen) {
      setActiveTab("crop")
      setPreviewDataUrl(null)
      setPreviewFile(null)
    }
  }, [isOpen, imageSrc])

  // Initialize crop when image loads in the DOM
  const onImageLoad = useCallback((e: React.SyntheticEvent<HTMLImageElement>) => {
    const { width, height } = e.currentTarget
    imgRef.current = e.currentTarget

    if (effectiveAspect) {
      // Fit the largest centered rectangle that matches the requested aspect ratio
      let cropW: number, cropH: number
      if (width / height > effectiveAspect) {
        cropH = height
        cropW = height * effectiveAspect
      } else {
        cropW = width
        cropH = width / effectiveAspect
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
  }, [effectiveAspect])

  const resetCropToFull = () => {
    if (!imgRef.current) return
    const { width, height } = imgRef.current

    if (effectiveAspect) {
      let cropW: number, cropH: number
      if (width / height > effectiveAspect) {
        cropH = height
        cropW = height * effectiveAspect
      } else {
        cropW = width
        cropH = width / effectiveAspect
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
      const { file, dataUrl } = await getCroppedFileAndDataUrl(imgRef.current, effectiveCrop, "preview.png", circularCrop)
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
      const { file } = await getCroppedFileAndDataUrl(imgRef.current, effectiveCrop, "cropped.png", circularCrop)
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
          .ReactCrop--circular-crop .ord-n,
          .ReactCrop--circular-crop .ord-e,
          .ReactCrop--circular-crop .ord-s,
          .ReactCrop--circular-crop .ord-w {
            display: none !important;
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
            <div className="px-4 py-2 bg-muted/30 border-b border-border flex items-center justify-between text-xs text-muted-foreground">
              <span>Drag the corners or edges to crop</span>

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
              className="p-3 sm:p-5 flex items-center justify-center bg-neutral-950 overflow-auto select-none max-h-[58vh] min-h-[260px]"
            >
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
                aspect={effectiveAspect}
                circularCrop={circularCrop}
                keepSelection={true}
                className="max-w-full"
              >
                <img
                  ref={imgRef}
                  src={imageSrc}
                  alt="Source banner to crop"
                  onLoad={onImageLoad}
                  crossOrigin="anonymous"
                  draggable={false}
                  style={{
                    maxWidth: "100%",
                    maxHeight: "52vh",
                    width: "auto",
                    height: "auto",
                    display: "block",
                  }}
                />
              </ReactCrop>
            </div>
          </div>

          {/* ── AUTHENTIC CHECKLIST / EVENT PREVIEW TAB ──────────── */}
          {showPreview && (
            <div className={activeTab === "preview" ? "bg-background flex flex-col min-h-[300px]" : "hidden"}>
              {previewMode === "event" && (
                <div className="h-12 px-5 flex items-center justify-between bg-[#05030A] border-b border-white/10 text-white shrink-0">
                  <span className="font-extrabold tracking-widest text-sm text-[#A77DFF]">SPACE.</span>
                  <div className="flex items-center gap-5 text-xs text-white/75">
                    <span>Home</span>
                    <span>About</span>
                    <span>Programs</span>
                    <span className="text-white font-semibold">Events</span>
                  </div>
                </div>
              )}

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

              {previewMode === "event" ? (
                <div className="px-5 sm:px-8 py-5 sm:py-6 flex flex-col gap-4 bg-[#05030A] text-white">
                  <div className="flex flex-wrap items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-white/60">
                    <span>{previewBreadcrumb || `EVENTS / UAE / ${(programName || "EVENT").toUpperCase()}`}</span>
                  </div>
                  <div className="rounded-2xl border border-[#A77DFF]/30 bg-gradient-to-br from-[#160b24] via-[#0b0512] to-[#1f0e33] p-5 space-y-2">
                    <span className="inline-block rounded-full bg-[#A77DFF]/20 border border-[#A77DFF]/40 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-widest text-[#A77DFF]">
                      Event Landing Page
                    </span>
                    <h1 className="text-lg sm:text-2xl font-extrabold text-white leading-tight">
                      {programName}
                    </h1>
                  </div>
                </div>
              ) : (
                /* Checklist Board Header (Matches RoadmapBoard.tsx and user's screenshot) */
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
              )}
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

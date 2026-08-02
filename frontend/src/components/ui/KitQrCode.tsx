import { useEffect, useRef, useState } from "react"
import QRCode from "qrcode"
import { Download, Copy, Check } from "lucide-react"

interface KitQrCodeProps {
  label: string
  tokenOrId: string
  size?: number
  showDownload?: boolean
  showCopyLink?: boolean
  className?: string
}

export function downloadKitQrLabel(label: string, tokenOrId: string) {
  const scanUrl = `${window.location.origin}/k/${tokenOrId}`
  QRCode.toDataURL(
    scanUrl,
    {
      width: 400,
      margin: 1,
      color: {
        dark: "#0f172a",
        light: "#ffffff",
      },
    },
    (err, url) => {
      if (err || !url) return

      const exportCanvas = document.createElement("canvas")
      const ctx = exportCanvas.getContext("2d")
      if (!ctx) return

      const padding = 30
      const qrSize = 300
      const canvasWidth = qrSize + padding * 2
      const canvasHeight = qrSize + padding * 2 + 70

      exportCanvas.width = canvasWidth
      exportCanvas.height = canvasHeight

      // Background
      ctx.fillStyle = "#ffffff"
      ctx.fillRect(0, 0, canvasWidth, canvasHeight)

      // Outer Border
      ctx.strokeStyle = "#cbd5e1"
      ctx.lineWidth = 4
      ctx.strokeRect(4, 4, canvasWidth - 8, canvasHeight - 8)

      const img = new Image()
      img.onload = () => {
        ctx.drawImage(img, padding, padding, qrSize, qrSize)

        // Label
        ctx.fillStyle = "#0f172a"
        ctx.font = "bold 22px monospace"
        ctx.textAlign = "center"
        ctx.fillText(label, canvasWidth / 2, padding + qrSize + 30)

        // Brand
        ctx.fillStyle = "#64748b"
        ctx.font = "600 13px sans-serif"
        ctx.fillText("SPACEPOINT INVENTORY", canvasWidth / 2, padding + qrSize + 52)

        const link = document.createElement("a")
        link.download = `${label}-QR.png`
        link.href = exportCanvas.toDataURL("image/png")
        link.click()
      }
      img.src = url
    }
  )
}

export function KitQrCode({
  label,
  tokenOrId,
  size = 120,
  showDownload = true,
  showCopyLink = false,
  className = "",
}: KitQrCodeProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const [copied, setCopied] = useState(false)
  const scanUrl = `${window.location.origin}/k/${tokenOrId}`

  useEffect(() => {
    if (!canvasRef.current) return
    QRCode.toCanvas(
      canvasRef.current,
      scanUrl,
      {
        width: size,
        margin: 1,
        color: {
          dark: "#0f172a",
          light: "#ffffff",
        },
      },
      () => {}
    )
  }, [scanUrl, size])

  const handleDownload = (e: React.MouseEvent) => {
    e.stopPropagation()
    e.preventDefault()
    downloadKitQrLabel(label, tokenOrId)
  }

  const handleCopyLink = (e: React.MouseEvent) => {
    e.stopPropagation()
    e.preventDefault()
    navigator.clipboard.writeText(scanUrl)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className={`flex flex-col items-center gap-2 ${className}`}>
      <div className="relative p-1.5 bg-white rounded-xl border border-border shadow-xs">
        <canvas ref={canvasRef} className="block rounded-md" style={{ width: size, height: size }} />
      </div>

      {(showDownload || showCopyLink) && (
        <div className="flex items-center gap-1.5 flex-wrap justify-center">
          {showDownload && (
            <button
              type="button"
              onClick={handleDownload}
              title="Download printable QR Code label"
              className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-foreground bg-secondary hover:bg-secondary/80 rounded-lg transition-colors cursor-pointer"
            >
              <Download size={12} /> Download QR
            </button>
          )}
          {showCopyLink && (
            <button
              type="button"
              onClick={handleCopyLink}
              title="Copy public scan link"
              className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium text-muted-foreground hover:text-foreground bg-muted/60 hover:bg-muted rounded-lg transition-colors cursor-pointer"
            >
              {copied ? <Check size={12} className="text-emerald-600" /> : <Copy size={12} />}
              {copied ? "Copied" : "Copy link"}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

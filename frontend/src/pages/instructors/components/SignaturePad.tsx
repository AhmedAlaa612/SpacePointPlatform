import { useEffect, useRef, useState } from "react"
import SignatureCanvas from "react-signature-canvas"
import { RotateCcw } from "lucide-react"
import { Button } from "@/components/ui/button"

function isDarkMode(): boolean {
  return document.documentElement.classList.contains("dark")
}

/** Ink must contrast with the canvas's theme-aware `bg-background` — a
 * hardcoded pen color went invisible in dark mode (near-black ink on a
 * near-black background). Tracks the `dark` class via MutationObserver
 * so it also updates if the user toggles theme while the pad is open. */
function useSignaturePenColor(): string {
  const [dark, setDark] = useState(isDarkMode)

  useEffect(() => {
    const observer = new MutationObserver(() => setDark(isDarkMode()))
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] })
    return () => observer.disconnect()
  }, [])

  return dark ? "#FFFFFF" : "#000000"
}

interface SignaturePadProps {
  onSign: (dataUrl: string) => void
  signing?: boolean
}

function trimCanvas(canvas: HTMLCanvasElement): HTMLCanvasElement {
  const ctx = canvas.getContext("2d")
  if (!ctx) return canvas

  const width = canvas.width
  const height = canvas.height
  const pixels = ctx.getImageData(0, 0, width, height)
  const len = pixels.data.length

  let bound = {
    top: null as number | null,
    left: null as number | null,
    right: null as number | null,
    bottom: null as number | null,
  }

  for (let i = 0; i < len; i += 4) {
    if (pixels.data[i + 3] !== 0) { // If alpha channel is not 0 (not transparent)
      const x = (i / 4) % width
      const y = Math.floor((i / 4) / width)

      if (bound.top === null) bound.top = y
      if (bound.left === null || x < bound.left) bound.left = x
      if (bound.right === null || x > bound.right) bound.right = x
      if (bound.bottom === null || y > bound.bottom) bound.bottom = y
    }
  }

  if (bound.top === null || bound.left === null || bound.right === null || bound.bottom === null) {
    return canvas
  }

  const trimHeight = bound.bottom - bound.top + 1
  const trimWidth = bound.right - bound.left + 1
  const trimmed = ctx.getImageData(bound.left, bound.top, trimWidth, trimHeight)

  const copy = document.createElement("canvas")
  copy.width = trimWidth
  copy.height = trimHeight
  const copyCtx = copy.getContext("2d")
  if (copyCtx) {
    copyCtx.putImageData(trimmed, 0, 0)
  }
  return copy
}

/** Canvas-based e-signature capture for payment letters. */
export function SignaturePad({ onSign, signing }: SignaturePadProps) {
  const ref = useRef<SignatureCanvas>(null)
  const penColor = useSignaturePenColor()

  const handleSign = () => {
    if (!ref.current || ref.current.isEmpty()) return
    const canvas = ref.current.getCanvas()
    const trimmedCanvas = trimCanvas(canvas)
    onSign(trimmedCanvas.toDataURL("image/png"))
  }

  return (
    <div>
      <div className="rounded-lg border border-dashed border-border bg-background">
        <SignatureCanvas
          ref={ref}
          penColor={penColor}
          canvasProps={{ className: "w-full h-40 rounded-lg" }}
        />
      </div>
      <div className="flex gap-2 mt-3">
        <Button type="button" variant="outline" onClick={() => ref.current?.clear()}>
          <RotateCcw size={14} className="mr-1.5" /> Clear
        </Button>
        <Button type="button" onClick={handleSign} disabled={signing}>
          {signing ? "Signing…" : "Sign & submit"}
        </Button>
      </div>
    </div>
  )
}


import { useRef } from "react"
import SignatureCanvas from "react-signature-canvas"
import { RotateCcw } from "lucide-react"
import { Button } from "@/components/ui/button"

interface SignaturePadProps {
  onSign: (dataUrl: string) => void
  signing?: boolean
}

/** Canvas-based e-signature capture for payment letters. */
export function SignaturePad({ onSign, signing }: SignaturePadProps) {
  const ref = useRef<SignatureCanvas>(null)

  const handleSign = () => {
    if (!ref.current || ref.current.isEmpty()) return
    onSign(ref.current.getTrimmedCanvas().toDataURL("image/png"))
  }

  return (
    <div>
      <div className="rounded-lg border border-dashed border-border bg-background">
        <SignatureCanvas
          ref={ref}
          penColor="black"
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

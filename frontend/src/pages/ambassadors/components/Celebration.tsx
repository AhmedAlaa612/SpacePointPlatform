import { useEffect, useState } from "react"
import { Sparkles } from "lucide-react"
import type { TitleBrief } from "@/types/ambassadors"
import { Dialog, DialogContent } from "@/components/ui/dialog"
import { TitleBadge } from "./title"

const COLORS = ["#a880ff", "#643f83", "#d6c7e1", "#f5b942", "#4ade80", "#60a5fa"]

/** Lightweight, dependency-free confetti + title-up modal shown when an
 *  ambassador crosses into a new title. */
export function TitleUpCelebration({
  title,
  open,
  onClose,
}: {
  title: TitleBrief | null
  open: boolean
  onClose: () => void
}) {
  const [pieces] = useState(() =>
    Array.from({ length: 60 }, (_, i) => ({
      id: i,
      left: Math.random() * 100,
      delay: Math.random() * 0.6,
      duration: 1.8 + Math.random() * 1.4,
      color: COLORS[i % COLORS.length],
      rotate: Math.random() * 360,
    }))
  )

  useEffect(() => {
    if (!open) return
    const t = setTimeout(onClose, 6000)
    return () => clearTimeout(t)
  }, [open, onClose])

  if (!open || !title) return null

  return (
    <>
      <style>{`
        @keyframes confetti-fall {
          0% { transform: translateY(-10vh) rotate(0deg); opacity: 1; }
          100% { transform: translateY(110vh) rotate(720deg); opacity: 0; }
        }
      `}</style>
      <div className="pointer-events-none fixed inset-0 z-[60] overflow-hidden">
        {pieces.map((p) => (
          <span
            key={p.id}
            style={{
              position: "absolute",
              top: 0,
              left: `${p.left}%`,
              width: 9,
              height: 14,
              backgroundColor: p.color,
              transform: `rotate(${p.rotate}deg)`,
              animation: `confetti-fall ${p.duration}s ${p.delay}s ease-in forwards`,
              borderRadius: 2,
            }}
          />
        ))}
      </div>

      <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
        <DialogContent showCloseButton className="max-w-sm text-center">
          <div className="flex flex-col items-center gap-4 py-2">
            <div className="w-16 h-16 rounded-full bg-heliotrope/15 text-heliotrope flex items-center justify-center">
              <Sparkles size={30} />
            </div>
            <div>
              <p className="text-sm text-gray-500">You reached a new title</p>
              <div className="mt-2 flex justify-center">
                <TitleBadge title={title} />
              </div>
            </div>
            <p className="text-sm text-gray-500">
              Keep earning points — your title never goes down.
            </p>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

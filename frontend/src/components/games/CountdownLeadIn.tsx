import { useEffect, useState } from "react"

/** Shared 3-2-1 lead-in overlay — used identically by the student play
 * screen and the instructor console so the room's countdown looks the
 * same everywhere. Purely a client-local animation triggered by receiving
 * `question_started`; calls `onDone` once when it hits zero so the caller
 * can start its real per-question answer-timing clock at THAT moment, not
 * when the WS message arrived — otherwise every student loses ~3s of
 * speed-bonus to the lead-in itself. */
export function CountdownLeadIn({ seconds = 3, onDone }: { seconds?: number; onDone: () => void }) {
  const [count, setCount] = useState(seconds)

  useEffect(() => {
    if (count <= 0) {
      onDone()
      return
    }
    const id = setTimeout(() => setCount((c) => c - 1), 1000)
    return () => clearTimeout(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [count])

  return (
    <div className="flex flex-col items-center justify-center gap-3 py-20">
      <div key={count} className="font-display text-7xl font-extrabold text-primary animate-in zoom-in fade-in duration-300">
        {count > 0 ? count : "Go!"}
      </div>
      <p className="text-sm text-muted-foreground">Get ready…</p>
    </div>
  )
}

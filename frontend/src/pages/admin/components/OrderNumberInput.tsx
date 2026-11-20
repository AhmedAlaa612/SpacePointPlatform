import { useState } from "react"

/** Editable order number box (mobile & keyboard friendly jump-to-position). */
export function OrderNumberInput({
  value,
  totalCount,
  onCommit,
  disabled,
}: {
  value: number
  totalCount: number
  onCommit: (pos: number) => void
  disabled?: boolean
}) {
  const [draftText, setDraftText] = useState<string | null>(null)
  const displayValue = draftText ?? String(value)

  const commit = () => {
    const parsed = Number.parseInt(displayValue, 10)
    setDraftText(null)
    if (!Number.isFinite(parsed) || parsed === value) {
      return
    }
    onCommit(parsed)
  }

  return (
    <input
      type="number"
      value={displayValue}
      min={1}
      max={totalCount}
      inputMode="numeric"
      disabled={disabled}
      onFocus={() => setDraftText(String(value))}
      onChange={(e) => setDraftText(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur()
        if (e.key === "Escape") {
          setDraftText(null)
          ;(e.target as HTMLInputElement).blur()
        }
      }}
      onClick={(e) => e.stopPropagation()}
      className="w-9 h-7 px-1 border border-border bg-background text-foreground rounded text-xs font-semibold text-center focus:outline-none focus:border-primary transition-colors disabled:opacity-50 shrink-0"
    />
  )
}

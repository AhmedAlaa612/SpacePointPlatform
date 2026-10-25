import { useState } from "react"

// Built-in vector faces matching the 5-point emoji rating design
function EmojiFace({ level }: { level: 1 | 2 | 3 | 4 | 5 }) {
  return (
    <svg viewBox="0 0 36 36" className="w-full h-full" fill="none" stroke="currentColor">
      {/* Level 1: Angry (Slanted brows + frown) */}
      {level === 1 && (
        <>
          <line x1="9" y1="11" x2="15" y2="14" strokeWidth="2.5" strokeLinecap="round" />
          <line x1="27" y1="11" x2="21" y2="14" strokeWidth="2.5" strokeLinecap="round" />
          <circle cx="12.5" cy="16" r="1.8" fill="currentColor" />
          <circle cx="23.5" cy="16" r="1.8" fill="currentColor" />
          <path d="M11 26C13 22 23 22 25 26" strokeWidth="2.5" strokeLinecap="round" />
        </>
      )}

      {/* Level 2: Sad / Frown */}
      {level === 2 && (
        <>
          <circle cx="12" cy="14" r="2" fill="currentColor" />
          <circle cx="24" cy="14" r="2" fill="currentColor" />
          <path d="M11.5 25C13.5 21.5 22.5 21.5 24.5 25" strokeWidth="2.5" strokeLinecap="round" />
        </>
      )}

      {/* Level 3: Neutral (Flat line) */}
      {level === 3 && (
        <>
          <circle cx="12" cy="14" r="2" fill="currentColor" />
          <circle cx="24" cy="14" r="2" fill="currentColor" />
          <line x1="12" y1="23.5" x2="24" y2="23.5" strokeWidth="2.5" strokeLinecap="round" />
        </>
      )}

      {/* Level 4: Happy / Smile */}
      {level === 4 && (
        <>
          <circle cx="12" cy="14" r="2" fill="currentColor" />
          <circle cx="24" cy="14" r="2" fill="currentColor" />
          <path d="M11.5 21.5C13.5 25.5 22.5 25.5 24.5 21.5" strokeWidth="2.5" strokeLinecap="round" />
        </>
      )}

      {/* Level 5: Very Happy / Wide Grin */}
      {level === 5 && (
        <>
          <circle cx="12" cy="13" r="2" fill="currentColor" />
          <circle cx="24" cy="13" r="2" fill="currentColor" />
          <path d="M10.5 20C10.5 26.5 25.5 26.5 25.5 20Z" fill="currentColor" strokeWidth="2" strokeLinejoin="round" />
        </>
      )}
    </svg>
  )
}

export interface EmojiRatingProps {
  value?: number | null
  onChange?: (val: number) => void
  readOnly?: boolean
  size?: "sm" | "md" | "lg"
  className?: string
}

export function EmojiRating({
  value = null,
  onChange,
  readOnly = false,
  size = "md",
  className = "",
}: EmojiRatingProps) {
  const [hovered, setHovered] = useState<number | null>(null)
  const activeRating = hovered ?? value

  const sizeClasses = {
    sm: "w-9 h-9 p-1.5",
    md: "w-11 h-11 p-2",
    lg: "w-14 h-14 p-2.5",
  }[size]

  return (
    <div
      role="radiogroup"
      aria-label="Rating out of 5 stars"
      className={`inline-flex items-center gap-3.5 pt-8 pb-2 select-none ${className}`}
    >
      {([1, 2, 3, 4, 5] as const).map((level) => {
        const isSelected = value === level
        const isHovered = hovered === level
        const isActive = isSelected || isHovered

        return (
          <div key={level} className="relative flex flex-col items-center">
            {/* Tooltip bubble pointing down with the rating number */}
            {activeRating === level && (
              <div
                className="absolute -top-10 px-2.5 py-0.5 rounded-lg bg-[#24292F] text-white text-xs font-black shadow-lg animate-in fade-in zoom-in-95 duration-150 pointer-events-none z-10 flex flex-col items-center"
                aria-hidden="true"
              >
                <span>{level}</span>
                <span className="w-2 h-2 bg-[#24292F] rotate-45 absolute -bottom-1" />
              </div>
            )}

            {/* Emoji Circle Button */}
            <button
              type="button"
              role="radio"
              aria-checked={isSelected}
              aria-label={`${level} star${level === 1 ? "" : "s"}`}
              disabled={readOnly}
              onClick={() => !readOnly && onChange?.(level)}
              onMouseEnter={() => !readOnly && setHovered(level)}
              onMouseLeave={() => !readOnly && setHovered(null)}
              className={`${sizeClasses} rounded-full border-2 transition-all duration-200 flex items-center justify-center cursor-pointer ${
                readOnly ? "cursor-default" : ""
              } ${
                isActive
                  ? "border-[#1F2328] bg-[#F5B82E] text-[#1F2328] scale-110 shadow-md shadow-[#F5B82E]/30 ring-2 ring-[#F5B82E]/40"
                  : "border-[#4A5568] bg-[#9CA3AF] dark:bg-[#4B5563] text-[#1F2328] dark:text-[#E5E7EB] opacity-75 hover:opacity-100 hover:scale-105"
              }`}
            >
              <EmojiFace level={level} />
            </button>
          </div>
        )
      })}
    </div>
  )
}
export default EmojiRating

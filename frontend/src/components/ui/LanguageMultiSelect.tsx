import { useEffect, useMemo, useRef, useState } from "react"
import { Check, ChevronDown, Search, X, Plus } from "lucide-react"
import { POPULAR_LANGUAGES } from "@/lib/languages"

interface LanguageMultiSelectProps {
  value: string[]
  onChange: (value: string[]) => void
  placeholder?: string
  className?: string
  disabled?: boolean
}

export function LanguageMultiSelect({
  value = [],
  onChange,
  placeholder = "Select fluent languages...",
  className = "",
  disabled = false,
}: LanguageMultiSelectProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [search, setSearch] = useState("")
  const containerRef = useRef<HTMLDivElement>(null)
  const searchInputRef = useRef<HTMLInputElement>(null)

  // Close on click outside or Escape key
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setIsOpen(false)
      }
    }
    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside)
      document.addEventListener("keydown", handleKeyDown)
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside)
      document.removeEventListener("keydown", handleKeyDown)
    }
  }, [isOpen])

  // Focus search input when dropdown opens
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => {
        searchInputRef.current?.focus()
      }, 50)
    } else {
      setSearch("")
    }
  }, [isOpen])

  // Combine standard languages with any custom selected ones
  const allKnownLanguages = useMemo(() => {
    const set = new Set(POPULAR_LANGUAGES)
    value.forEach((v) => {
      if (v) set.add(v)
    })
    return Array.from(set)
  }, [value])

  const filteredLanguages = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return allKnownLanguages
    return allKnownLanguages.filter((lang) => lang.toLowerCase().includes(q))
  }, [allKnownLanguages, search])

  const exactMatchExists = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return true
    return allKnownLanguages.some((lang) => lang.toLowerCase() === q)
  }, [allKnownLanguages, search])

  const toggleLanguage = (lang: string) => {
    if (value.includes(lang)) {
      onChange(value.filter((v) => v !== lang))
    } else {
      onChange([...value, lang])
    }
  }

  const addCustomLanguage = () => {
    const custom = search.trim()
    if (!custom) return
    // Capitalize first letter of each word
    const formatted = custom
      .split(" ")
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ")
    if (!value.includes(formatted)) {
      onChange([...value, formatted])
    }
    setSearch("")
  }

  const removeLanguage = (lang: string) => {
    onChange(value.filter((v) => v !== lang))
  }

  return (
    <div ref={containerRef} className={`relative w-full ${isOpen ? "z-50" : ""}`}>
      {/* Trigger Box */}
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        onClick={() => !disabled && setIsOpen((prev) => !prev)}
        onKeyDown={(e) => {
          if (!disabled && (e.key === "Enter" || e.key === " ")) {
            e.preventDefault()
            setIsOpen((prev) => !prev)
          }
        }}
        className={`w-full min-h-[44px] rounded-xl bg-background border border-border px-3.5 py-2 text-sm text-foreground flex items-center justify-between gap-2 cursor-pointer transition-all ${
          isOpen ? "ring-2 ring-primary/40 border-primary" : "hover:border-border/80"
        } ${disabled ? "opacity-60 cursor-not-allowed" : ""} ${className}`}
      >
        <div className="flex flex-wrap items-center gap-1.5 flex-1 min-w-0">
          {value.length === 0 ? (
            <span className="text-muted-foreground/50 text-sm select-none">{placeholder}</span>
          ) : (
            value.map((lang) => (
              <span
                key={lang}
                className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-lg text-xs font-medium bg-primary/10 text-primary border border-primary/20 animate-in fade-in-50 duration-150"
              >
                <span>{lang}</span>
                {!disabled && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      removeLanguage(lang)
                    }}
                    className="text-primary/60 hover:text-primary hover:bg-primary/20 rounded-full p-0.5 transition-colors focus:outline-none"
                    aria-label={`Remove ${lang}`}
                  >
                    <X className="w-3 h-3" />
                  </button>
                )}
              </span>
            ))
          )}
        </div>

        <div className="flex items-center gap-1 shrink-0 text-muted-foreground">
          {value.length > 0 && !disabled && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                onChange([])
              }}
              title="Clear all"
              className="p-1 hover:text-foreground hover:bg-muted rounded-md transition-colors"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
          <ChevronDown
            className={`w-4 h-4 transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`}
          />
        </div>
      </div>

      {/* Dropdown Popover */}
      {isOpen && !disabled && (
        <div className="absolute left-0 right-0 top-full mt-1.5 z-50 rounded-xl border border-border bg-popover text-popover-foreground shadow-2xl p-2 flex flex-col gap-2 animate-in fade-in-0 zoom-in-95 duration-150 ring-1 ring-border">
          {/* Search box inside popover */}
          <div className="relative flex items-center">
            <Search className="w-3.5 h-3.5 absolute left-3 text-muted-foreground pointer-events-none" />
            <input
              ref={searchInputRef}
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !exactMatchExists && search.trim()) {
                  e.preventDefault()
                  addCustomLanguage()
                }
              }}
              placeholder="Search or type language..."
              className="w-full pl-8 pr-7 py-1.5 rounded-lg bg-background border border-border/80 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary transition-all"
            />
            {search && (
              <button
                type="button"
                onClick={() => setSearch("")}
                className="absolute right-2 text-muted-foreground hover:text-foreground p-0.5 rounded"
              >
                <X className="w-3 h-3" />
              </button>
            )}
          </div>

          {/* Languages list */}
          <div className="max-h-52 overflow-y-auto space-y-0.5 pr-1 divide-y divide-border/20">
            {/* Custom Language Add option */}
            {!exactMatchExists && search.trim() && (
              <button
                type="button"
                onClick={addCustomLanguage}
                className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium text-primary hover:bg-primary/10 transition-colors text-left"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Add &quot;{search.trim()}&quot; as language</span>
              </button>
            )}

            {filteredLanguages.length === 0 && exactMatchExists ? (
              <div className="py-4 text-center text-xs text-muted-foreground">
                No languages found
              </div>
            ) : (
              filteredLanguages.map((lang) => {
                const isSelected = value.includes(lang)
                return (
                  <div
                    key={lang}
                    role="checkbox"
                    aria-checked={isSelected}
                    tabIndex={0}
                    onClick={() => toggleLanguage(lang)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault()
                        toggleLanguage(lang)
                      }
                    }}
                    className={`flex items-center justify-between px-3 py-1.5 rounded-lg text-xs cursor-pointer select-none transition-colors ${
                      isSelected
                        ? "bg-primary/10 text-primary font-medium"
                        : "hover:bg-muted text-foreground"
                    }`}
                  >
                    <span>{lang}</span>
                    <span
                      className={`w-4 h-4 rounded border flex items-center justify-center transition-colors ${
                        isSelected
                          ? "bg-primary border-primary text-primary-foreground"
                          : "border-border bg-background"
                      }`}
                    >
                      {isSelected && <Check className="w-3 h-3 stroke-[3]" />}
                    </span>
                  </div>
                )
              })
            )}
          </div>

          {/* Footer count indicator */}
          <div className="pt-1.5 border-t border-border/40 flex items-center justify-between text-[11px] text-muted-foreground px-1">
            <span>{value.length} selected</span>
            <button
              type="button"
              onClick={() => setIsOpen(false)}
              className="text-primary hover:underline font-medium"
            >
              Done
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

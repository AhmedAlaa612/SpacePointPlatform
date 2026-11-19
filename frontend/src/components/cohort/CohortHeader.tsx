/* Shared cohort page header — the dark banner every cohort detail page uses
 * (Ops `/operations/cohorts/:id` and Partner Org `/organization/programs/:id`).
 *
 * These two pages are deliberately the same page for training purposes: one
 * guide, one set of tab names, one look. Keeping the markup here rather than
 * copying it into each page is what makes that true after the next edit, too.
 *
 * Presentation only: the pages still own their tabs, counters, actions and
 * data. Anything Ops has and the sandbox doesn't (status select, warehouse)
 * is simply an omitted prop. */

import type { ReactNode } from "react"
import { useNavigate, useSearch } from "@tanstack/react-router"
import { ArrowLeft, Calendar, Layers, MapPin, Package } from "lucide-react"

import { useAuth } from "@/context/AuthContext"

export interface CohortHeaderTab {
  key: string
  label: string
}

export interface CohortHeaderCounter {
  label: string
  value: ReactNode
  onClick: () => void
  tone?: "default" | "alert"
}

export interface CohortHeaderProps {
  name: string
  /** Status pill (Ops only — org cohorts have no delivery status). */
  status?: ReactNode
  /** Extra pills next to the title (partner-org link, Public, code…). */
  badges?: ReactNode
  programName?: string | null
  dates?: string | null
  location?: string | null
  warehouse?: string | null
  back?: ReactNode
  /** Right-hand column; pages pass their own Edit / status / link buttons. */
  actions?: ReactNode
  counters?: CohortHeaderCounter[]
  tabs: CohortHeaderTab[]
  activeTab: string
  onTabChange: (key: string) => void
  className?: string
}

export const COHORT_BACK_BUTTON_CLASS =
  "inline-flex w-fit items-center gap-1.5 text-sm font-medium text-white/75 hover:text-white transition-colors mb-4 cursor-pointer"

function CounterChip({ label, value, onClick, tone = "default" }: CohortHeaderCounter) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex items-center justify-center gap-1.5 h-9 px-4 rounded-[10px] border-[2px] bg-transparent text-sm transition-colors cursor-pointer ${
        tone === "alert"
          ? "border-rose-400/80 text-rose-300 hover:bg-rose-500/15"
          : "border-[#D7D2CB] text-white hover:bg-white/10"
      }`}
    >
      <span className="font-semibold tabular-nums leading-none flex items-center">{value}</span>
      <span
        className={`text-xs leading-none flex items-center ${
          tone === "alert" ? "text-rose-200/85" : "text-white/75"
        }`}
      >
        {label}
      </span>
    </button>
  )
}

export function CohortHeader({
  name,
  status,
  badges,
  programName,
  dates,
  location,
  warehouse,
  back,
  actions,
  counters,
  tabs,
  activeTab,
  onTabChange,
  className,
}: CohortHeaderProps) {
  return (
    <div
      className={
        className ??
        "sp-wireframe-header relative overflow-hidden -mx-4 -mt-4 sm:-mx-6 sm:-mt-6 lg:-mx-10 lg:-mt-10 px-4 sm:px-6 lg:px-10 pt-5 bg-[#231134] text-white"
      }
    >
      <img
        src="/space-logo-white.png"
        alt=""
        aria-hidden="true"
        className="pointer-events-none select-none absolute bottom-0 right-6 w-48 sm:w-64 opacity-10"
      />

      <div className="relative z-10">
        {back}

        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="min-w-0 space-y-3">
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="text-2xl font-bold tracking-tight text-white">{name}</h1>
              {status}
              {badges}
            </div>

            <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-white/85">
              {programName && (
                <div className="inline-flex items-center gap-1.5">
                  <Layers size={13} className="text-white/55 shrink-0" />
                  <span className="text-white/55">Program:</span>
                  <span className="font-medium text-white">{programName}</span>
                </div>
              )}

              {dates && (
                <div className="inline-flex items-center gap-1.5">
                  <Calendar size={13} className="text-white/55 shrink-0" />
                  <span className="text-white/55">Dates:</span>
                  <span className="font-medium text-white">{dates}</span>
                </div>
              )}

              {location && (
                <div className="inline-flex items-center gap-1.5">
                  <MapPin size={13} className="text-white/55 shrink-0" />
                  <span className="text-white/55">Location:</span>
                  <span className="font-medium text-white">{location}</span>
                </div>
              )}

              {warehouse && (
                <div className="inline-flex items-center gap-1.5">
                  <Package size={13} className="text-white/55 shrink-0" />
                  <span className="text-white/55">Warehouse:</span>
                  <span className="font-medium text-white">{warehouse}</span>
                </div>
              )}
            </div>
          </div>

          {actions && (
            <div className="flex flex-col gap-2 shrink-0 sm:min-w-[210px]">{actions}</div>
          )}
        </div>

        {counters && counters.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-5 pb-4">
            {counters.map((c) => (
              <CounterChip key={c.label} {...c} />
            ))}
          </div>
        )}

        <div
          className="flex items-center gap-1 border-b border-white/15 overflow-x-auto scrollbar-none no-scrollbar"
          role="tablist"
        >
          {tabs.map((t) => (
            <button
              key={t.key}
              role="tab"
              type="button"
              aria-selected={activeTab === t.key}
              onClick={() => onTabChange(t.key)}
              className={`h-9 px-3 -mb-px border-b-2 text-sm font-medium transition-colors shrink-0 whitespace-nowrap cursor-pointer ${
                activeTab === t.key
                  ? "border-[#D7D2CB] text-white"
                  : "border-transparent text-white/70 hover:text-white"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

/* ── Back button ─────────────────────────────────────────────────────────────
 * Same control on both pages. Ops can arrive from applications, programs,
 * organizations or instructor views; the org sandbox mostly from its Programs
 * list. */

function resolveCohortBackTarget(
  from: string | undefined,
  activeRole: string | null | undefined,
  cohort?: { program_name?: string | null },
): { label: string; to: string; useHistory?: boolean } {
  if (from?.startsWith("/instructors")) return { label: "Instructor View", to: from }
  if (from?.startsWith("/operations/organizations/")) return { label: "Organization", to: from }
  if (from?.startsWith("/operations/programs/")) {
    return { label: cohort?.program_name || "Program", to: from }
  }
  if (from?.startsWith("/operations/programs")) return { label: "Programs", to: from }
  if (from?.startsWith("/operations/cohorts")) return { label: "Cohorts", to: from }
  if (from?.startsWith("/organization")) return { label: "Programs", to: from }
  if (from?.startsWith("/")) return { label: "Back", to: from }
  if (activeRole === "instructor") {
    return { label: "Instructor View", to: "/instructors/sessions", useHistory: true }
  }
  if (activeRole === "organization") return { label: "Programs", to: "/organization/programs" }
  return { label: "Cohorts", to: "/operations/cohorts" }
}

export function CohortBackButton({
  className = COHORT_BACK_BUTTON_CLASS,
  cohort,
}: {
  className?: string
  cohort?: { program_name?: string | null }
}) {
  const navigate = useNavigate()
  const { from } = useSearch({ strict: false }) as { from?: string }
  const { activeRole } = useAuth()
  const target = resolveCohortBackTarget(from, activeRole, cohort)

  const handleClick = () => {
    if (target.useHistory && window.history.length > 1) {
      window.history.back()
      return
    }
    const [pathname, rawQuery] = target.to.split("?")
    const searchObj = rawQuery ? Object.fromEntries(new URLSearchParams(rawQuery)) : undefined
    void navigate({ to: pathname as never, search: searchObj as never })
  }

  return (
    <button type="button" onClick={handleClick} className={className}>
      <ArrowLeft size={14} /> {target.label}
    </button>
  )
}

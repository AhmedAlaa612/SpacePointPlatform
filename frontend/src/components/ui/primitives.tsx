import type { ReactNode } from "react"

/** Shared, domain-agnostic UI primitives. Domain `common.tsx` files re-export
 *  these so there's a single source of truth (previously duplicated across the
 *  ambassadors / instructors / admin folders). */

export function Spinner() {
  return (
    <div className="flex items-center justify-center py-16">
      <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
    </div>
  )
}

export function PageHeader({
  title,
  subtitle,
  action,
}: {
  title: string
  subtitle?: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
      <div>
        <h1 className="font-display text-2xl sm:text-3xl font-bold tracking-tight">{title}</h1>
        {subtitle && <p className="text-sm text-muted-foreground mt-1">{subtitle}</p>}
      </div>
      {action}
    </div>
  )
}

export function StatCard({
  icon,
  label,
  value,
  sub,
}: {
  icon: ReactNode
  label: string
  value: ReactNode
  sub?: string
}) {
  return (
    <div className="rounded-2xl bg-card/70 dark:bg-card/60 backdrop-blur-xl ring-1 ring-black/5 dark:ring-white/10 p-4 sm:p-5 flex items-center gap-4">
      <div className="w-11 h-11 rounded-xl bg-primary/10 text-primary flex items-center justify-center shrink-0">
        {icon}
      </div>
      <div className="min-w-0">
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide truncate">{label}</p>
        <p className="font-display text-2xl font-bold leading-tight break-all">{value}</p>
        {sub && <p className="text-xs text-muted-foreground mt-0.5 truncate">{sub}</p>}
      </div>
    </div>
  )
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-12 px-4">
      <p className="text-base font-semibold">{title}</p>
      {hint && <p className="text-sm text-muted-foreground mt-1 max-w-xs">{hint}</p>}
    </div>
  )
}

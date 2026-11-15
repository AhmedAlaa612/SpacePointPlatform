import { useMemo, useState } from "react"
import { Link, useNavigate } from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import {
  getAdminOverviewApi,
  type AdminActionKind,
  type AdminActionQueueItem,
  type AdminActionTone,
} from "@/api/admin/overview"
import { cn } from "@/lib/utils"

type ActionFilter = "all" | AdminActionKind

const ACTION_FILTERS: { value: ActionFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "app", label: "Applications" },
  { value: "role_request", label: "Role Requests" },
  { value: "doc_request", label: "Documents" },
  { value: "applicant", label: "Onboarding" },
  { value: "payment", label: "Payments" },
]

// Strictly Purple / Black / White / Grayscale, with Rose & Emerald reserved for alerts/status.
const TONE_BADGE: Record<AdminActionTone, string> = {
  purple: "bg-[#653F84] text-white",
  emerald: "bg-[#16A34A] text-white",
  rose: "bg-[#E11D48] text-white",
  neutral: "bg-zinc-700 text-white",
}

function formatShortDate(iso: string | null) {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" })
}

export default function AdminHub() {
  const navigate = useNavigate()
  const [filter, setFilter] = useState<ActionFilter>("all")
  const [showAllActions, setShowAllActions] = useState(false)

  const { data, isLoading, isError } = useQuery({
    queryKey: ["admin-command-overview"],
    queryFn: getAdminOverviewApi,
    staleTime: 30_000,
    refetchInterval: 60_000,
  })

  const goTo = (href: string) => {
    const u = new URL(href, window.location.origin)
    const searchObj = Object.fromEntries(u.searchParams.entries())
    void navigate({
      to: u.pathname as never,
      search: (Object.keys(searchObj).length ? searchObj : undefined) as never,
      hash: u.hash ? u.hash.slice(1) : undefined,
    })
  }

  const actions = data?.actions ?? []
  const filteredActions = useMemo(
    () => (filter === "all" ? actions : actions.filter((a) => a.kind === filter)),
    [actions, filter]
  )
  const visibleActions = showAllActions ? filteredActions : filteredActions.slice(0, 8)

  const kindCounts = useMemo(() => {
    const counts: Record<ActionFilter, number> = {
      all: actions.length,
      app: 0,
      role_request: 0,
      doc_request: 0,
      applicant: 0,
      payment: 0,
    }
    for (const a of actions) counts[a.kind] += 1
    return counts
  }, [actions])

  if (isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <div>
          <h1 className="font-display text-2xl font-bold text-foreground tracking-tight">Admin Hub</h1>
        </div>
        <div className="grid grid-cols-1 xl:grid-cols-12 gap-4">
          <div className="xl:col-span-6 h-36 rounded-[10px] bg-card animate-pulse" />
          <div className="xl:col-span-3 h-36 rounded-[10px] bg-card animate-pulse" />
          <div className="xl:col-span-3 h-36 rounded-[10px] bg-card animate-pulse" />
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
          <div className="lg:col-span-7 h-96 rounded-[10px] bg-card animate-pulse" />
          <div className="lg:col-span-5 h-96 rounded-[10px] bg-card animate-pulse" />
        </div>
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div className="rounded-[10px] bg-card p-8 text-center">
        <p className="text-sm font-semibold text-rose-500">Failed to load admin overview.</p>
      </div>
    )
  }

  const { pending_requests, onboarding, payments, business } = data
  const totalRequests =
    pending_requests.applications + pending_requests.role_requests + pending_requests.documents
  const totalOnboarding = onboarding.pending + onboarding.to_be_reviewed
  const totalOpenPayments = payments.pending + payments.published + payments.signed

  const onboardingPhases = [
    {
      label: "Phase 1 (Videos & Modules)",
      count: onboarding.phase1_in_progress,
      href: "/instructors/admin/applicants?status=in_progress",
      widthClass: "w-full",
    },
    {
      label: "Phase 2 (Assessment)",
      count: onboarding.phase2_in_progress,
      href: "/instructors/admin/applicants?status=research_approved",
      widthClass: "w-full sm:w-[86%]",
    },
    {
      label: "Phase 3 (Presentation)",
      count: onboarding.phase3_in_progress,
      href: "/instructors/admin/applicants?status=phase_1_approved",
      widthClass: "w-full sm:w-[72%]",
    },
  ]

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <h1 className="font-display text-2xl sm:text-3xl font-bold text-foreground tracking-tight">
          Admin Hub
        </h1>
        <Link
          to="/operations/dashboard"
          className="inline-flex items-center justify-center self-start sm:self-auto px-4 py-2 rounded-[10px] bg-[#653F84] text-xs font-semibold text-white"
        >
          Operations Portal
        </Link>
      </div>

      {/* Top Status Strip: Pending Requests (6 cols) + Onboarding (3 cols) + Payments (3 cols) */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4">
        {/* 1. Pending Requests with dedicated navigation button under each count */}
        <div className="xl:col-span-6 rounded-[10px] bg-card p-5 flex flex-col gap-4">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-bold uppercase tracking-wider text-foreground">
              Pending Requests
            </span>
            <span className="px-2.5 py-0.5 rounded-[10px] bg-[#653F84] text-xs font-bold text-white">
              {totalRequests}
            </span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="rounded-[10px] border border-border p-3 flex flex-col justify-between gap-3">
              <p className="font-display text-2xl font-bold text-foreground leading-none">
                {pending_requests.applications}
              </p>
              <button
                type="button"
                onClick={() => goTo("/admin/applications")}
                className="w-full px-3 py-2 rounded-[10px] bg-[#653F84] text-xs font-semibold text-white text-center"
              >
                Applications
              </button>
            </div>
            <div className="rounded-[10px] border border-border p-3 flex flex-col justify-between gap-3">
              <p className="font-display text-2xl font-bold text-foreground leading-none">
                {pending_requests.role_requests}
              </p>
              <button
                type="button"
                onClick={() => goTo("/admin/role-requests")}
                className="w-full px-3 py-2 rounded-[10px] bg-[#653F84] text-xs font-semibold text-white text-center"
              >
                Role Requests
              </button>
            </div>
            <div className="rounded-[10px] border border-border p-3 flex flex-col justify-between gap-3">
              <p className="font-display text-2xl font-bold text-foreground leading-none">
                {pending_requests.documents}
              </p>
              <button
                type="button"
                onClick={() => goTo("/admin/documents?tab=requests")}
                className="w-full px-3 py-2 rounded-[10px] bg-[#653F84] text-xs font-semibold text-white text-center"
              >
                Document Requests
              </button>
            </div>
          </div>
        </div>

        {/* 2. Onboarding */}
        <div className="xl:col-span-3 rounded-[10px] bg-card p-5 flex flex-col gap-4">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-bold uppercase tracking-wider text-foreground">
              Onboarding
            </span>
            <span className="px-2.5 py-0.5 rounded-[10px] bg-[#653F84] text-xs font-bold text-white">
              {totalOnboarding}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2.5 flex-1">
            <button
              type="button"
              onClick={() => goTo("/instructors/admin/applicants?status=pending_onboarding")}
              className="rounded-[10px] border border-border px-3 py-3 text-left flex flex-col justify-between"
            >
              <p className="font-display text-2xl font-bold text-foreground leading-none">
                {onboarding.pending}
              </p>
              <p className="text-xs font-medium text-foreground mt-2">In Progress</p>
            </button>
            <button
              type="button"
              onClick={() => goTo("/instructors/admin/applicants?status=under_review")}
              className="rounded-[10px] border border-primary px-3 py-3 text-left flex flex-col justify-between"
            >
              <p className="font-display text-2xl font-bold text-foreground leading-none">
                {onboarding.to_be_reviewed}
              </p>
              <p className="text-xs font-medium text-foreground mt-2">To be reviewed</p>
            </button>
          </div>
        </div>

        {/* 3. Payments (status counts only, no monetary amounts) */}
        <div className="xl:col-span-3 rounded-[10px] bg-card p-5 flex flex-col gap-4">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-bold uppercase tracking-wider text-foreground">
              Payments
            </span>
            <span className="px-2.5 py-0.5 rounded-[10px] bg-[#653F84] text-xs font-bold text-white">
              {totalOpenPayments}
            </span>
          </div>
          <div className="grid grid-cols-3 gap-2 flex-1">
            <button
              type="button"
              onClick={() => goTo("/instructors/admin/payments#todo")}
              className="rounded-[10px] border border-border px-2.5 py-3 text-left flex flex-col justify-between"
            >
              <p className="font-display text-xl font-bold text-foreground leading-none">
                {payments.pending}
              </p>
              <p className="text-xs font-medium text-foreground mt-2">Pending</p>
            </button>
            <button
              type="button"
              onClick={() => goTo("/instructors/admin/payments?status=published")}
              className="rounded-[10px] border border-border px-2.5 py-3 text-left flex flex-col justify-between"
            >
              <p className="font-display text-xl font-bold text-foreground leading-none">
                {payments.published}
              </p>
              <p className="text-xs font-medium text-foreground mt-2">Published</p>
            </button>
            <button
              type="button"
              onClick={() => goTo("/instructors/admin/payments?status=signed")}
              className={cn(
                "rounded-[10px] border-2 px-2.5 py-3 text-left flex flex-col justify-between",
                payments.signed > 0 ? "border-[#16A34A]" : "border-border"
              )}
            >
              <p className="font-display text-xl font-bold text-foreground leading-none">
                {payments.signed}
              </p>
              <p className="text-xs font-medium text-foreground mt-2">Signed</p>
            </button>
          </div>
        </div>
      </div>

      {/* Main 7/5 Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
        {/* Left (7 cols): Actions */}
        <div className="lg:col-span-7 rounded-[10px] bg-card p-5 flex flex-col gap-4">
          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-2.5">
              <h2 className="text-base font-bold text-foreground">Actions</h2>
              <span className="px-2.5 py-0.5 rounded-[10px] bg-[#653F84] text-xs font-bold text-white">
                {filteredActions.length}
              </span>
            </div>
            <div className="flex flex-nowrap items-center gap-1.5 overflow-x-auto no-scrollbar">
              {ACTION_FILTERS.map((f) => {
                const count = kindCounts[f.value]
                const active = filter === f.value
                return (
                  <button
                    key={f.value}
                    type="button"
                    onClick={() => {
                      setFilter(f.value)
                      setShowAllActions(false)
                    }}
                    className={cn(
                      "px-2.5 py-1.5 rounded-[10px] text-xs font-semibold border whitespace-nowrap shrink-0 transition-colors",
                      active
                        ? "bg-[#653F84] text-white border-primary"
                        : "bg-transparent text-foreground border-border"
                    )}
                  >
                    {f.label}
                    {count > 0 && ` (${count})`}
                  </button>
                )
              })}
            </div>
          </div>

          {filteredActions.length === 0 ? (
            <div className="py-14 text-center border border-border rounded-[10px]">
              <p className="text-sm font-semibold text-foreground">All caught up</p>
            </div>
          ) : (
            <div className="flex flex-col divide-y divide-border rounded-[10px] border border-border overflow-hidden">
              {visibleActions.map((item: AdminActionQueueItem) => {
                const dateLabel = formatShortDate(item.created_at)
                return (
                  <button
                    key={`${item.kind}-${item.id}`}
                    type="button"
                    onClick={() => goTo(item.href)}
                    className="w-full flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-4 py-3.5 text-left"
                  >
                    <div className="min-w-0 flex-1 flex flex-col gap-1.5">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span
                          className={cn(
                            "text-[11px] font-semibold px-2.5 py-0.5 rounded-[10px] shrink-0",
                            TONE_BADGE[item.tone]
                          )}
                        >
                          {item.tag}
                        </span>
                        <p className="text-sm font-semibold text-foreground">
                          {item.title}
                        </p>
                      </div>
                      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-foreground">
                        <span>{item.subtitle}</span>
                        {dateLabel && <span>{dateLabel}</span>}
                      </div>
                    </div>
                    <span className="text-xs font-semibold text-foreground underline underline-offset-4 shrink-0">
                      {item.cta}
                    </span>
                  </button>
                )
              })}
            </div>
          )}

          {filteredActions.length > 8 && (
            <button
              type="button"
              onClick={() => setShowAllActions((v) => !v)}
              className="self-center text-xs font-semibold text-foreground hover:underline"
            >
              {showAllActions
                ? "Show top 8"
                : `Show all ${filteredActions.length} actions`}
            </button>
          )}
        </div>

        {/* Right (5 cols): Business Overview + Onboarding */}
        <div className="lg:col-span-5 flex flex-col gap-5">
          {/* Business Overview */}
          <div className="rounded-[10px] bg-card p-5 flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-bold text-foreground">Business Overview</h2>
              <button
                type="button"
                onClick={() => goTo("/admin/users")}
                className="text-xs font-semibold text-foreground hover:underline"
              >
                Users
              </button>
            </div>

            {/* Tier 1: Students, Instructors, Interns */}
            <div className="grid grid-cols-3 gap-2.5">
              <button
                type="button"
                onClick={() => goTo("/admin/users?view=students")}
                className="rounded-[10px] border border-primary p-3 text-left"
              >
                <p className="text-xs font-medium text-foreground">Students</p>
                <p className="font-display text-2xl font-bold text-foreground mt-1">
                  {business.students}
                </p>
              </button>
              <button
                type="button"
                onClick={() => goTo("/instructors/admin/instructors")}
                className="rounded-[10px] border border-primary p-3 text-left"
              >
                <p className="text-xs font-medium text-foreground">Instructors</p>
                <p className="font-display text-2xl font-bold text-foreground mt-1">
                  {business.instructors}
                </p>
              </button>
              <button
                type="button"
                onClick={() => goTo("/admin/users?view=staff&role=intern")}
                className="rounded-[10px] border border-primary p-3 text-left"
              >
                <p className="text-xs font-medium text-foreground">Interns</p>
                <p className="font-display text-2xl font-bold text-foreground mt-1">
                  {business.interns}
                </p>
              </button>
            </div>

            {/* Tier 2: Organizations, Ambassadors, Mentors */}
            <div className="grid grid-cols-3 gap-2.5">
              <button
                type="button"
                onClick={() => goTo("/admin/users?view=organizations")}
                className="rounded-[10px] border border-primary p-3 text-left"
              >
                <p className="text-xs font-medium text-foreground">Organizations</p>
                <p className="font-display text-xl font-bold text-foreground mt-1">
                  {business.organizations}
                </p>
              </button>
              <button
                type="button"
                onClick={() => goTo("/admin/users?view=staff&role=ambassador")}
                className="rounded-[10px] border border-primary p-3 text-left"
              >
                <p className="text-xs font-medium text-foreground">Ambassadors</p>
                <p className="font-display text-xl font-bold text-foreground mt-1">
                  {business.ambassadors}
                </p>
              </button>
              <button
                type="button"
                onClick={() => goTo("/admin/users?view=staff&role=mentor")}
                className="rounded-[10px] border border-primary p-3 text-left"
              >
                <p className="text-xs font-medium text-foreground">Mentors</p>
                <p className="font-display text-xl font-bold text-foreground mt-1">
                  {business.mentors}
                </p>
              </button>
            </div>

            {/* Reconciliation row */}
            <div className="pt-3 border-t border-border flex flex-wrap items-center justify-between gap-2 text-xs text-foreground">
              <div className="flex flex-wrap gap-x-4 gap-y-1">
                <span>Facilitators: <strong>{business.facilitators}</strong></span>
                <span>Applicants: <strong>{business.applicants}</strong></span>
                <span>Org accounts: <strong>{business.org_members}</strong></span>
                <span>Ops/Admin: <strong>{business.ops_admin}</strong></span>
              </div>
              <span>
                Total accounts: <strong>{business.total_users}</strong>
              </span>
            </div>
          </div>

          {/* Onboarding Summary */}
          <div className="rounded-[10px] bg-card p-5 flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-bold text-foreground">Onboarding</h2>
              <Link
                to="/instructors/admin/applicants"
                className="text-xs font-semibold text-foreground hover:underline"
              >
                All Applicants
              </Link>
            </div>

            <div className="grid grid-cols-2 gap-2.5">
              <button
                type="button"
                onClick={() => goTo("/instructors/admin/applicants?status=pending_onboarding")}
                className="rounded-[10px] border border-border p-3 text-left"
              >
                <p className="text-xs font-medium text-foreground">In Progress</p>
                <p className="font-display text-2xl font-bold text-foreground mt-0.5">
                  {onboarding.pending}
                </p>
              </button>
              <button
                type="button"
                onClick={() => goTo("/instructors/admin/applicants?status=under_review")}
                className="rounded-[10px] border border-primary p-3 text-left"
              >
                <p className="text-xs font-medium text-foreground">To be reviewed</p>
                <p className="font-display text-2xl font-bold text-foreground mt-0.5">
                  {onboarding.to_be_reviewed}
                </p>
              </button>
            </div>

            {/* 3-phase onboarding funnel */}
            <div className="flex flex-col items-center gap-1.5 pt-1">
              {onboardingPhases.map((phase) => (
                <button
                  key={phase.href}
                  type="button"
                  onClick={() => goTo(phase.href)}
                  className={cn(
                    "mx-auto flex items-center justify-between gap-2 px-3.5 py-2 rounded-[10px] text-xs font-semibold transition-colors",
                    phase.widthClass,
                    phase.count > 0
                      ? "bg-[#653F84] text-white"
                      : "border border-border text-foreground"
                  )}
                >
                  <span>{phase.label}</span>
                  <span className="font-display text-sm font-bold tabular-nums">
                    {phase.count}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

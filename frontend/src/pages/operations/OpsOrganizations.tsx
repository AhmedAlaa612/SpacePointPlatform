import { useMemo, useState } from "react"
import { Link } from "@tanstack/react-router"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Clock,
  CreditCard,
  Globe,
  GraduationCap,
  Layers,
  Mail,
  MapPin,
  Plus,
  Search,
  SlidersHorizontal,
  Ticket,
  Users,
} from "lucide-react"
import {
  getAdminEventOrganizations,
  updateAdminOrganizationAccount,
  type OrganizationAccountSummary,
} from "@/api/websiteEvents"
import {
  ORG_TYPE_OPTIONS,
  OrgAccountModal,
  buildOrgApprovePayload,
  formatOrgType,
  quotaPct,
} from "@/components/operations/OrgManagementModals"
import { Button } from "@/components/ui/button"
import { PageHeader, Spinner, SubCard } from "@/components/ui/primitives"
import { useToast } from "@/components/ui/toast"
import { cn, getErrorMessage } from "@/lib/utils"

type ApprovalFilter = "all" | "approved" | "pending"
type ActivityFilter = "all" | "running_cohorts" | "has_courses" | "pending_course_review"
type SortKey = "pending_first" | "students" | "cohorts" | "name" | "newest"

function QuotaBar({ used, limit }: { used: number; limit?: number | null }) {
  if (limit == null || limit <= 0) return null
  const pct = quotaPct(used, limit)
  return (
    <div className="mt-2 h-1.5 w-full overflow-hidden rounded-[10px] bg-muted">
      <div
        className="h-full rounded-[10px] bg-primary transition-all"
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

export default function OpsOrganizations() {
  const qc = useQueryClient()
  const toast = useToast()

  const { data: orgs = [], isLoading, isError } = useQuery({
    queryKey: ["admin-website-organizations"],
    queryFn: getAdminEventOrganizations,
  })

  const [search, setSearch] = useState("")
  const [approvalFilter, setApprovalFilter] = useState<ApprovalFilter>("all")
  const [typeFilter, setTypeFilter] = useState<string>("all")
  const [activityFilter, setActivityFilter] = useState<ActivityFilter>("all")
  const [sortKey, setSortKey] = useState<SortKey>("pending_first")

  const [modalMode, setModalMode] = useState<"closed" | "create" | "edit">("closed")
  const [editingOrg, setEditingOrg] = useState<OrganizationAccountSummary | null>(null)

  const approveMut = useMutation({
    mutationFn: (org: OrganizationAccountSummary) =>
      updateAdminOrganizationAccount(org.id, buildOrgApprovePayload(org, true)),
    onSuccess: (updated) => {
      void qc.invalidateQueries({ queryKey: ["admin-website-organizations"] })
      void qc.invalidateQueries({ queryKey: ["admin-organization-detail", updated.id] })
      toast.success(`${updated.name_latin} approved`)
    },
    onError: (err) => toast.error(getErrorMessage(err, "Could not approve organization")),
  })

  const kpis = useMemo(() => {
    const approvedCount = orgs.filter((o) => o.is_approved).length
    const pendingCount = orgs.filter((o) => !o.is_approved).length
    const activeCohorts = orgs.reduce((sum, o) => sum + (o.running_cohorts_count ?? 0), 0)
    const totalCohorts = orgs.reduce((sum, o) => sum + (o.cohorts_count ?? 0), 0)
    const totalStudents = orgs.reduce((sum, o) => sum + (o.enrolled_students_count ?? 0), 0)
    const pendingCourses = orgs.reduce((sum, o) => sum + (o.pending_review_courses_count ?? 0), 0)
    return {
      total: orgs.length,
      approvedCount,
      pendingCount,
      activeCohorts,
      totalCohorts,
      totalStudents,
      pendingCourses,
    }
  }, [orgs])

  const filteredOrgs = useMemo(() => {
    const q = search.trim().toLowerCase()
    const list = orgs.filter((o) => {
      if (q) {
        const hay = [
          o.name_latin,
          o.name_arabic ?? "",
          o.owner_name ?? "",
          o.owner_email ?? "",
          o.city ?? "",
          o.country ?? "",
          o.owner_card_id ?? "",
        ]
          .join(" ")
          .toLowerCase()
        if (!hay.includes(q)) return false
      }
      if (approvalFilter === "approved" && !o.is_approved) return false
      if (approvalFilter === "pending" && o.is_approved) return false
      if (typeFilter !== "all" && o.org_type !== typeFilter) return false
      if (activityFilter === "running_cohorts" && (o.running_cohorts_count ?? 0) === 0) return false
      if (activityFilter === "has_courses" && (o.authored_courses_count ?? 0) === 0) return false
      if (activityFilter === "pending_course_review" && (o.pending_review_courses_count ?? 0) === 0)
        return false
      return true
    })

    list.sort((a, b) => {
      if (sortKey === "pending_first") {
        if (a.is_approved !== b.is_approved) return a.is_approved ? 1 : -1
        const pDiff = (b.pending_review_courses_count ?? 0) - (a.pending_review_courses_count ?? 0)
        if (pDiff !== 0) return pDiff
        const sDiff = (b.enrolled_students_count ?? 0) - (a.enrolled_students_count ?? 0)
        if (sDiff !== 0) return sDiff
        return a.name_latin.localeCompare(b.name_latin)
      }
      if (sortKey === "students") {
        return (b.enrolled_students_count ?? 0) - (a.enrolled_students_count ?? 0)
      }
      if (sortKey === "cohorts") {
        return (b.running_cohorts_count ?? 0) - (a.running_cohorts_count ?? 0)
      }
      if (sortKey === "newest") {
        return (b.created_at ?? "").localeCompare(a.created_at ?? "")
      }
      return a.name_latin.localeCompare(b.name_latin)
    })
    return list
  }, [orgs, search, approvalFilter, typeFilter, activityFilter, sortKey])

  const hasFilters =
    search.trim().length > 0 ||
    approvalFilter !== "all" ||
    typeFilter !== "all" ||
    activityFilter !== "all"

  if (isLoading) return <Spinner />

  if (isError) {
    return (
      <div className="rounded-[10px] border border-destructive/40 bg-card p-6 text-sm text-destructive">
        Could not load partner organizations.
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Partner Organizations"
        action={
          <Button
            type="button"
            onClick={() => {
              setEditingOrg(null)
              setModalMode("create")
            }}
            className="h-9 rounded-[10px] px-4 text-xs font-semibold"
          >
            <Plus className="h-4 w-4" />
            New Organization
          </Button>
        }
      />

      {/* 4 KPI Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-[10px] border border-border bg-card p-4 sm:p-5">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Total Organizations
          </p>
          <p className="mt-1 text-2xl font-bold leading-tight text-foreground">{kpis.total}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">{kpis.approvedCount} approved</p>
        </div>

        <button
          type="button"
          onClick={() => setApprovalFilter((prev) => (prev === "pending" ? "all" : "pending"))}
          className={cn(
            "rounded-[10px] border p-4 text-left transition-colors sm:p-5",
            approvalFilter === "pending"
              ? "border-primary bg-primary/10"
              : "border-border bg-card hover:border-primary/40"
          )}
        >
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Pending Approval
          </p>
          <p className="mt-1 text-2xl font-bold leading-tight text-foreground">{kpis.pendingCount}</p>
          <p className="mt-0.5 text-xs text-primary">
            {approvalFilter === "pending" ? "Showing pending only" : "Filter pending"}
          </p>
        </button>

        <div className="rounded-[10px] border border-border bg-card p-4 sm:p-5">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Active Org Cohorts
          </p>
          <p className="mt-1 text-2xl font-bold leading-tight text-foreground">{kpis.activeCohorts}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">{kpis.totalCohorts} total cohorts</p>
        </div>

        <div className="rounded-[10px] border border-border bg-card p-4 sm:p-5">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Enrolled Org Students
          </p>
          <p className="mt-1 text-2xl font-bold leading-tight text-foreground">{kpis.totalStudents}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {kpis.pendingCourses > 0
              ? `${kpis.pendingCourses} pending course review`
              : "Across active cohorts"}
          </p>
        </div>
      </div>

      {/* Single-Line Direct-on-Background Filter Bar */}
      <div className="flex flex-wrap items-center gap-2.5 lg:flex-nowrap">
        <div className="relative min-w-[220px] flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search name, email, city, or Card ID"
            className="h-9 w-full rounded-[10px] border border-border bg-background pl-9 pr-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none"
          />
        </div>

        <select
          aria-label="Filter by approval status"
          value={approvalFilter}
          onChange={(e) => setApprovalFilter(e.target.value as ApprovalFilter)}
          className="h-9 w-auto shrink-0 rounded-[10px] border border-border bg-background px-3 text-xs font-medium text-foreground focus:border-primary focus:outline-none"
        >
          <option value="all">Approval: All</option>
          <option value="approved">Approval: Approved</option>
          <option value="pending">Approval: Pending</option>
        </select>

        <select
          aria-label="Filter by organization type"
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="h-9 w-auto shrink-0 rounded-[10px] border border-border bg-background px-3 text-xs font-medium text-foreground focus:border-primary focus:outline-none"
        >
          <option value="all">Type: All</option>
          {ORG_TYPE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>

        <select
          aria-label="Filter by activity"
          value={activityFilter}
          onChange={(e) => setActivityFilter(e.target.value as ActivityFilter)}
          className="h-9 w-auto shrink-0 rounded-[10px] border border-border bg-background px-3 text-xs font-medium text-foreground focus:border-primary focus:outline-none"
        >
          <option value="all">Activity: All</option>
          <option value="running_cohorts">Running Cohorts</option>
          <option value="has_courses">Has LMS Courses</option>
          <option value="pending_course_review">Pending Course Review</option>
        </select>

        <select
          aria-label="Sort organizations"
          value={sortKey}
          onChange={(e) => setSortKey(e.target.value as SortKey)}
          className="h-9 w-auto shrink-0 rounded-[10px] border border-border bg-background px-3 text-xs font-medium text-foreground focus:border-primary focus:outline-none"
        >
          <option value="pending_first">Sort: Pending First</option>
          <option value="students">Sort: Most Students</option>
          <option value="cohorts">Sort: Most Running Cohorts</option>
          <option value="name">Sort: Name (A to Z)</option>
          <option value="newest">Sort: Newest Added</option>
        </select>

        {hasFilters && (
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              setSearch("")
              setApprovalFilter("all")
              setTypeFilter("all")
              setActivityFilter("all")
            }}
            className="h-9 shrink-0 rounded-[10px] px-3 text-xs font-medium"
          >
            Reset
          </Button>
        )}
      </div>

      {/* Directory List */}
      {filteredOrgs.length === 0 ? (
        <div className="rounded-[10px] border border-border bg-card p-10 text-center text-sm text-muted-foreground">
          No partner organizations match the current filters.
        </div>
      ) : (
        <div className="space-y-4">
          {filteredOrgs.map((org) => {
            const pendingCourses = org.pending_review_courses_count ?? 0

            return (
              <div
                key={org.id}
                className={cn(
                  "rounded-[10px] border bg-card p-6 transition-colors",
                  !org.is_approved
                    ? "border-primary/40"
                    : "border-border hover:border-primary/30"
                )}
              >
                {/* Top Header Row */}
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="flex items-start gap-4">
                    {org.logo_url && (
                      <img
                        src={org.logo_url}
                        alt={org.name_latin}
                        className="h-12 w-12 shrink-0 rounded-[10px] border border-border bg-muted object-contain"
                      />
                    )}
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-baseline gap-3">
                        <Link
                          to="/operations/organizations/$orgId"
                          params={{ orgId: org.id }}
                          className="text-lg font-bold text-foreground hover:text-primary transition-colors"
                        >
                          {org.name_latin}
                        </Link>
                        {org.name_arabic && (
                          <span dir="rtl" className="text-sm font-medium text-muted-foreground">
                            {org.name_arabic}
                          </span>
                        )}
                      </div>

                      <div className="flex flex-wrap items-center gap-2">
                        {org.is_approved ? (
                          <span className="inline-flex items-center gap-1.5 rounded-[10px] border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-xs font-semibold text-emerald-700 dark:text-emerald-300">
                            <CheckCircle2 className="h-3.5 w-3.5" />
                            Approved
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 rounded-[10px] border border-primary/30 bg-primary/10 px-2.5 py-1 text-xs font-semibold text-primary">
                            <Clock className="h-3.5 w-3.5" />
                            Pending Approval
                          </span>
                        )}

                        <span className="rounded-[10px] border border-border bg-muted px-2.5 py-1 text-xs font-semibold text-foreground">
                          {formatOrgType(org.org_type)}
                        </span>

                        {(org.city || org.country) && (
                          <span className="inline-flex items-center gap-1.5 rounded-[10px] border border-border bg-muted px-2.5 py-1 text-xs text-muted-foreground">
                            <MapPin className="h-3.5 w-3.5" />
                            {[org.city, org.country?.toUpperCase()].filter(Boolean).join(", ")}
                          </span>
                        )}

                        {org.can_publish_events && (
                          <span className="rounded-[10px] border border-primary/25 bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary">
                            Event Publishing
                          </span>
                        )}
                        {org.can_author_courses && (
                          <span className="rounded-[10px] border border-primary/25 bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary">
                            Course Authoring
                          </span>
                        )}
                        {org.can_publish_courses && (
                          <span className="rounded-[10px] border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-xs font-medium text-emerald-700 dark:text-emerald-300">
                            Self-Publish Courses
                          </span>
                        )}
                        {pendingCourses > 0 && (
                          <span className="inline-flex items-center gap-1.5 rounded-[10px] border border-primary/30 bg-primary/10 px-2.5 py-1 text-xs font-semibold text-primary">
                            <AlertTriangle className="h-3.5 w-3.5" />
                            {pendingCourses} Course Review
                          </span>
                        )}
                      </div>

                      {/* Owner & Team Strip */}
                      <div className="flex flex-wrap items-center gap-2 pt-1 text-xs text-muted-foreground">
                        {org.owner_name && (
                          <span className="inline-flex items-center gap-1.5 rounded-[10px] border border-border bg-background px-2.5 py-1 text-foreground">
                            <Users className="h-3.5 w-3.5 text-muted-foreground" />
                            {org.owner_name}
                          </span>
                        )}
                        {org.owner_email && (
                          <span className="inline-flex items-center gap-1.5 rounded-[10px] border border-border bg-background px-2.5 py-1">
                            <Mail className="h-3.5 w-3.5" />
                            {org.owner_email}
                          </span>
                        )}
                        {org.owner_card_id && (
                          <span className="inline-flex items-center gap-1.5 rounded-[10px] border border-primary/25 bg-primary/10 px-2.5 py-1 font-mono font-semibold text-primary">
                            <CreditCard className="h-3.5 w-3.5" />
                            {org.owner_card_id}
                          </span>
                        )}
                        <span className="inline-flex items-center gap-1.5 rounded-[10px] border border-border bg-background px-2.5 py-1">
                          {org.members_count} team members
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Card Actions */}
                  <div className="flex flex-wrap items-center gap-2">
                    {!org.is_approved && (
                      <Button
                        type="button"
                        disabled={approveMut.isPending}
                        onClick={() => approveMut.mutate(org)}
                        className="h-9 rounded-[10px] bg-emerald-600 px-3.5 text-xs font-semibold text-white hover:bg-emerald-500"
                      >
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        Approve Now
                      </Button>
                    )}

                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => {
                        setEditingOrg(org)
                        setModalMode("edit")
                      }}
                      className="h-9 rounded-[10px] px-3.5 text-xs font-semibold"
                    >
                      <SlidersHorizontal className="h-3.5 w-3.5" />
                      Quotas & Grants
                    </Button>

                    <Button asChild className="h-9 rounded-[10px] px-4 text-xs font-semibold">
                      <Link
                        to="/operations/organizations/$orgId"
                        params={{ orgId: org.id }}
                      >
                        Organization Page
                        <ArrowRight className="h-3.5 w-3.5" />
                      </Link>
                    </Button>
                  </div>
                </div>

                {/* 6 Live Usage Cells */}
                <div className="mt-5 grid grid-cols-2 gap-3 border-t border-border pt-5 sm:grid-cols-3 lg:grid-cols-6">
                  <SubCard>
                    <div className="flex items-center justify-between text-xs font-semibold text-muted-foreground">
                      <span>Programs</span>
                      <Layers className="h-3.5 w-3.5 text-primary" />
                    </div>
                    <div className="mt-2 text-base font-bold text-foreground">
                      {org.programs_count ?? 0}
                      <span className="ml-1 text-xs font-normal text-muted-foreground">
                        / {org.max_programs ?? "Unlimited"}
                      </span>
                    </div>
                    <QuotaBar used={org.programs_count ?? 0} limit={org.max_programs} />
                  </SubCard>

                  <SubCard>
                    <div className="flex items-center justify-between text-xs font-semibold text-muted-foreground">
                      <span>Cohorts</span>
                      <Users className="h-3.5 w-3.5 text-emerald-500" />
                    </div>
                    <div className="mt-2 text-base font-bold text-foreground">
                      {org.cohorts_count ?? 0}
                      <span className="ml-1 text-xs font-normal text-muted-foreground">
                        / {org.max_cohorts ?? "Unlimited"}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {org.running_cohorts_count ?? 0} running
                    </div>
                    <QuotaBar used={org.cohorts_count ?? 0} limit={org.max_cohorts} />
                  </SubCard>

                  <SubCard>
                    <div className="flex items-center justify-between text-xs font-semibold text-muted-foreground">
                      <span>Students</span>
                      <GraduationCap className="h-3.5 w-3.5 text-primary" />
                    </div>
                    <div className="mt-2 text-base font-bold text-foreground">
                      {org.enrolled_students_count ?? 0}
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {org.max_students_per_cohort
                        ? `Peak ${org.highest_cohort_students ?? 0} / ${org.max_students_per_cohort}`
                        : "Enrolled total"}
                    </div>
                    <QuotaBar
                      used={org.highest_cohort_students ?? 0}
                      limit={org.max_students_per_cohort}
                    />
                  </SubCard>

                  <SubCard>
                    <div className="flex items-center justify-between text-xs font-semibold text-muted-foreground">
                      <span>LMS Courses</span>
                      <BookOpen className="h-3.5 w-3.5 text-primary" />
                    </div>
                    <div className="mt-2 text-base font-bold text-foreground">
                      {org.authored_courses_count ?? 0} authored
                    </div>
                    <div
                      className={cn(
                        "mt-1 text-xs",
                        pendingCourses > 0 ? "font-semibold text-primary" : "text-muted-foreground"
                      )}
                    >
                      {pendingCourses > 0
                        ? `${pendingCourses} pending review`
                        : `${org.shared_courses_count ?? 0} shared`}
                    </div>
                  </SubCard>

                  <SubCard>
                    <div className="flex items-center justify-between text-xs font-semibold text-muted-foreground">
                      <span>Invite Batches</span>
                      <Ticket className="h-3.5 w-3.5 text-primary" />
                    </div>
                    <div className="mt-2 text-base font-bold text-foreground">
                      {org.invite_batches_active_count ?? 0} active
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {org.invite_used_count ?? 0} / {org.invite_max_count ?? 0} seats used
                    </div>
                  </SubCard>

                  <SubCard>
                    <div className="flex items-center justify-between text-xs font-semibold text-muted-foreground">
                      <span>Landing Pages</span>
                      <Globe className="h-3.5 w-3.5 text-primary" />
                    </div>
                    <div className="mt-2 text-base font-bold text-foreground">
                      {org.events_count ?? 0}
                      <span className="ml-1 text-xs font-normal text-muted-foreground">
                        / {org.max_events ?? "Unlimited"}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {org.published_events_count ?? 0} published
                    </div>
                    <QuotaBar used={org.events_count ?? 0} limit={org.max_events} />
                  </SubCard>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Create / Edit Quotas & Account Modal */}
      {modalMode !== "closed" && (
        <OrgAccountModal
          org={modalMode === "edit" ? editingOrg : null}
          onClose={() => {
            setModalMode("closed")
            setEditingOrg(null)
          }}
          onSaved={() => {
            setModalMode("closed")
            setEditingOrg(null)
          }}
        />
      )}
    </div>
  )
}

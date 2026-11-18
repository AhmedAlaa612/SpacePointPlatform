import { useMemo, useState } from "react"
import { Link, useNavigate, useParams } from "@tanstack/react-router"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  ArrowLeft,
  ArrowUpRight,
  BookOpen,
  Calendar,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Copy,
  CreditCard,
  ExternalLink,
  Globe,
  HelpCircle,
  KeyRound,
  Mail,
  MapPin,
  Phone,
  Search,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  Ticket,
  UserPlus,
  Users,
} from "lucide-react"
import {
  ORG_ASSIGNABLE_ROLES,
  createOrganizationMember,
  createOrganizationMemberResetLink,
  getAdminOrganizationDetail,
  getAdminOrganizationResetLink,
  removeOrganizationMember,
  toggleOrganizationCoursePublish,
  updateAdminOrganizationAccount,
  updateOrganizationMember,
  type OrgSandboxRole,
} from "@/api/websiteEvents"
import {
  OrgAccountModal,
  WEBSITE_BASE_URL,
  buildOrgApprovePayload,
  formatOrgType,
  quotaPct,
} from "@/components/operations/OrgManagementModals"
import { Button } from "@/components/ui/button"
import { SUB_CARD_CLASS, Spinner, SubCard } from "@/components/ui/primitives"
import { useToast } from "@/components/ui/toast"
import { cn, getErrorMessage } from "@/lib/utils"

type DetailTab = "overview" | "programs" | "students" | "courses" | "landing" | "team"

function formatShortDate(iso?: string | null): string {
  if (!iso) return "TBA"
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  })
}

function formatDateRange(startsOn?: string | null, endsOn?: string | null): string {
  if (!startsOn && !endsOn) return "Dates TBD"
  if (startsOn && endsOn) return `${formatShortDate(startsOn)} to ${formatShortDate(endsOn)}`
  return startsOn ? `Starts ${formatShortDate(startsOn)}` : `Ends ${formatShortDate(endsOn)}`
}

export default function OpsOrganizationDetail() {
  const { orgId } = useParams({ strict: false }) as { orgId: string }
  const navigate = useNavigate()
  const qc = useQueryClient()
  const toast = useToast()

  const { data: detail, isLoading, isError } = useQuery({
    queryKey: ["admin-organization-detail", orgId],
    queryFn: () => getAdminOrganizationDetail(orgId),
  })

  const [activeTab, setActiveTab] = useState<DetailTab>("overview")
  const [editOpen, setEditOpen] = useState(false)
  const [expandedPrograms, setExpandedPrograms] = useState<Record<string, boolean>>({})
  const [studentQuery, setStudentQuery] = useState("")
  const [studentCohortFilter, setStudentCohortFilter] = useState("all")
  const [copiedKey, setCopiedKey] = useState<string | null>(null)
  const [inviteOpen, setInviteOpen] = useState(false)

  const invalidateOrgQueries = () => {
    void qc.invalidateQueries({ queryKey: ["admin-organization-detail", orgId] })
    void qc.invalidateQueries({ queryKey: ["admin-website-organizations"] })
  }

  const toggleApprovalMut = useMutation({
    mutationFn: (nextApproved: boolean) => {
      if (!detail) throw new Error("Organization not loaded")
      return updateAdminOrganizationAccount(
        orgId,
        buildOrgApprovePayload(detail.organization, nextApproved)
      )
    },
    onSuccess: (updated) => {
      invalidateOrgQueries()
      toast.success(
        updated.is_approved ? "Organization approved for portal access" : "Organization approval revoked"
      )
    },
    onError: (err) => toast.error(getErrorMessage(err, "Could not update approval status")),
  })

  const ownerResetMut = useMutation({
    mutationFn: () => getAdminOrganizationResetLink(orgId),
    onSuccess: async (res) => {
      try {
        await navigator.clipboard.writeText(res.reset_url)
        setCopiedKey("owner-reset")
        setTimeout(() => setCopiedKey((cur) => (cur === "owner-reset" ? null : cur)), 2500)
        toast.success(
          res.email_sent
            ? `Password link emailed to ${res.email} (also copied)`
            : `Email failed — reset link copied for ${res.email}`
        )
      } catch {
        toast.success(
          res.email_sent ? `Password link emailed to ${res.email}` : `Reset link ready for ${res.email}`
        )
      }
    },
    onError: (err) => toast.error(getErrorMessage(err, "Could not generate owner reset link")),
  })

  const memberResetMut = useMutation({
    mutationFn: (userId: string) => createOrganizationMemberResetLink(orgId, userId),
    onSuccess: async (res, userId) => {
      try {
        await navigator.clipboard.writeText(res.reset_url)
        setCopiedKey(`member-${userId}`)
        setTimeout(() => setCopiedKey((cur) => (cur === `member-${userId}` ? null : cur)), 2500)
        toast.success(
          res.email_sent
            ? `Password link emailed to ${res.email} (also copied)`
            : `Email failed — reset link copied for ${res.email}`
        )
      } catch {
        toast.success(
          res.email_sent
            ? `Password link emailed to ${res.email}`
            : `Reset link generated for ${res.email}`
        )
      }
    },
    onError: (err) => toast.error(getErrorMessage(err, "Could not generate member reset link")),
  })

  const memberRoleMut = useMutation({
    mutationFn: ({ userId, orgRole }: { userId: string; orgRole: string }) =>
      updateOrganizationMember(orgId, userId, orgRole),
    onSuccess: () => {
      invalidateOrgQueries()
      toast.success("Member role updated")
    },
    onError: (err) => toast.error(getErrorMessage(err, "Could not update member role")),
  })

  const removeMemberMut = useMutation({
    mutationFn: (userId: string) => removeOrganizationMember(orgId, userId),
    onSuccess: () => {
      invalidateOrgQueries()
      toast.success("Member removed from this organization")
    },
    onError: (err) => toast.error(getErrorMessage(err, "Could not remove member")),
  })

  const coursePublishMut = useMutation({
    mutationFn: ({ courseId, isPublished }: { courseId: string; isPublished: boolean }) =>
      toggleOrganizationCoursePublish(orgId, courseId, isPublished),
    onSuccess: (res) => {
      invalidateOrgQueries()
      toast.success(res.is_published ? "Course published to catalog" : "Course unpublished")
    },
    onError: (err) => toast.error(getErrorMessage(err, "Could not update course publication")),
  })

  const filteredStudents = useMemo(() => {
    const list = detail?.students ?? []
    const q = studentQuery.trim().toLowerCase()
    return list.filter((s) => {
      if (studentCohortFilter !== "all" && s.cohort_id !== studentCohortFilter) return false
      if (!q) return true
      return [s.full_name, s.email, s.phone ?? "", s.cohort_name].join(" ").toLowerCase().includes(q)
    })
  }, [detail?.students, studentQuery, studentCohortFilter])

  const copyText = async (key: string, text: string, label: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedKey(key)
      setTimeout(() => setCopiedKey((cur) => (cur === key ? null : cur)), 2500)
      toast.success(`${label} copied`)
    } catch {
      toast.error("Could not copy to clipboard")
    }
  }

  if (isLoading) return <Spinner />

  if (isError || !detail) {
    return (
      <div className="space-y-4">
        <Button asChild variant="outline" className="h-9 rounded-[10px] px-4 text-xs font-semibold">
          <Link to="/operations/organizations">
            <ArrowLeft className="h-4 w-4" />
            Back to Organizations
          </Link>
        </Button>
        <div className="rounded-[10px] border border-destructive/40 bg-card p-6 text-sm text-destructive">
          Organization details could not be loaded.
        </div>
      </div>
    )
  }

  const org = detail.organization

  const quotaCards = [
    {
      label: "Programs",
      used: org.programs_count ?? detail.programs.length,
      limit: org.max_programs,
      sub: `${detail.programs.filter((p) => p.active).length} active`,
    },
    {
      label: "Cohorts",
      used: org.cohorts_count ?? detail.cohorts.length,
      limit: org.max_cohorts,
      sub: `${org.running_cohorts_count ?? 0} running`,
    },
    {
      label: "Peak Students / Cohort",
      used: org.highest_cohort_students ?? 0,
      limit: org.max_students_per_cohort,
      sub: org.highest_cohort_name
        ? `Top cohort: ${org.highest_cohort_name}`
        : `${org.enrolled_students_count ?? 0} total enrolled`,
    },
    {
      label: "Peak Observers / Cohort",
      used: org.highest_cohort_observers ?? 0,
      limit: org.max_observers_per_cohort,
      sub: org.highest_observers_cohort_name
        ? `Top cohort: ${org.highest_observers_cohort_name}`
        : `${detail.team.filter((m) => m.role === "Observer").length} total observers`,
    },
    {
      label: "Landing Pages",
      used: org.events_count ?? detail.landing_pages.length,
      limit: org.max_events,
      sub: `${org.published_events_count ?? 0} published`,
    },
  ]

  const tabs: { id: DetailTab; label: string; count: number | null }[] = [
    { id: "overview", label: "Overview & Activity", count: null },
    { id: "programs", label: "Programs & Cohorts", count: detail.cohorts.length },
    { id: "students", label: "Students & Invite Codes", count: detail.students.length },
    {
      id: "courses",
      label: "LMS Courses & Quiz Bank",
      count: detail.authored_courses.length + detail.quiz_templates.length,
    },
    { id: "landing", label: "Landing Pages", count: detail.landing_pages.length },
    { id: "team", label: "Team & Observers", count: detail.team.length },
  ]

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <Link
          to="/operations/organizations"
          className="inline-flex items-center gap-1.5 font-semibold text-foreground hover:text-primary transition-colors"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Organizations
        </Link>
        <ChevronRight className="h-3.5 w-3.5" />
        <span className="font-semibold text-foreground">{org.name_latin}</span>
      </div>

      {/* Hero Header Card */}
      <div className="rounded-[10px] border border-border bg-card p-6">
        <div className="flex flex-wrap items-start justify-between gap-6">
          <div className="flex items-start gap-4">
            {org.logo_url && (
              <img
                src={org.logo_url}
                alt={org.name_latin}
                className="h-14 w-14 shrink-0 rounded-[10px] border border-border bg-muted object-contain"
              />
            )}
            <div className="space-y-2.5">
              <div className="flex flex-wrap items-baseline gap-3">
                <h1 className="text-2xl font-bold text-foreground">{org.name_latin}</h1>
                {org.name_arabic && (
                  <span dir="rtl" className="text-base font-medium text-muted-foreground">
                    {org.name_arabic}
                  </span>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {org.is_approved ? (
                  <span className="inline-flex items-center gap-1.5 rounded-[10px] border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-xs font-semibold text-emerald-700 dark:text-emerald-300">
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    Approved Partner
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
                {org.created_at && (
                  <span className="inline-flex items-center gap-1.5 rounded-[10px] border border-border bg-muted px-2.5 py-1 text-xs text-muted-foreground">
                    <Calendar className="h-3.5 w-3.5" />
                    Joined {formatShortDate(org.created_at)}
                  </span>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-2 pt-1 text-xs">
                {org.owner_name && (
                  <span className="inline-flex items-center gap-1.5 rounded-[10px] border border-border bg-background px-2.5 py-1 text-foreground">
                    <Users className="h-3.5 w-3.5 text-muted-foreground" />
                    {org.owner_name}
                  </span>
                )}
                {org.owner_email && (
                  <span className="inline-flex items-center gap-1.5 rounded-[10px] border border-border bg-background px-2.5 py-1 text-muted-foreground">
                    <Mail className="h-3.5 w-3.5" />
                    {org.owner_email}
                  </span>
                )}
                {org.owner_phone && (
                  <span className="inline-flex items-center gap-1.5 rounded-[10px] border border-border bg-background px-2.5 py-1 text-muted-foreground">
                    <Phone className="h-3.5 w-3.5" />
                    {org.owner_phone}
                  </span>
                )}
                {org.owner_card_id && (
                  <span className="inline-flex items-center gap-1.5 rounded-[10px] border border-primary/25 bg-primary/10 px-2.5 py-1 font-mono font-semibold text-primary">
                    <CreditCard className="h-3.5 w-3.5" />
                    {org.owner_card_id}
                  </span>
                )}
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {org.is_approved ? (
              <Button
                type="button"
                variant="destructive"
                disabled={toggleApprovalMut.isPending}
                onClick={() => toggleApprovalMut.mutate(false)}
                className="h-9 rounded-[10px] px-3.5 text-xs font-semibold"
              >
                <ShieldAlert className="h-3.5 w-3.5" />
                Revoke Approval
              </Button>
            ) : (
              <Button
                type="button"
                disabled={toggleApprovalMut.isPending}
                onClick={() => toggleApprovalMut.mutate(true)}
                className="h-9 rounded-[10px] bg-emerald-600 px-4 text-xs font-semibold text-white hover:bg-emerald-500"
              >
                <ShieldCheck className="h-3.5 w-3.5" />
                Approve Organization
              </Button>
            )}

            {org.owner_user_id && (
              <Button
                type="button"
                variant="outline"
                disabled={ownerResetMut.isPending}
                onClick={() => ownerResetMut.mutate()}
                className="h-9 rounded-[10px] px-3.5 text-xs font-semibold"
              >
                {copiedKey === "owner-reset" ? (
                  <Check className="h-3.5 w-3.5 text-emerald-500" />
                ) : (
                  <KeyRound className="h-3.5 w-3.5" />
                )}
                Owner Reset Link
              </Button>
            )}

            <Button
              type="button"
              onClick={() => setEditOpen(true)}
              className="h-9 rounded-[10px] px-4 text-xs font-semibold"
            >
              <SlidersHorizontal className="h-3.5 w-3.5" />
              Edit Quotas & Permissions
            </Button>
          </div>
        </div>

        {/* Capabilities Strip */}
        <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-border pt-4">
          <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Capabilities:
          </span>
          <span
            className={cn(
              "rounded-[10px] border px-2.5 py-1 text-xs font-semibold",
              org.can_publish_events
                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                : "border-border bg-muted text-muted-foreground"
            )}
          >
            Event Publishing: {org.can_publish_events ? "Enabled" : "Restricted"}
          </span>
          <span
            className={cn(
              "rounded-[10px] border px-2.5 py-1 text-xs font-semibold",
              org.can_author_courses
                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                : "border-border bg-muted text-muted-foreground"
            )}
          >
            Course Authoring: {org.can_author_courses ? "Enabled" : "Disabled"}
          </span>
          <span
            className={cn(
              "rounded-[10px] border px-2.5 py-1 text-xs font-semibold",
              org.can_publish_courses
                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                : "border-border bg-muted text-muted-foreground"
            )}
          >
            Self-Publish Courses: {org.can_publish_courses ? "Enabled" : "Ops Review Required"}
          </span>
          <span className="rounded-[10px] border border-primary/25 bg-primary/10 px-2.5 py-1 text-xs font-semibold text-primary">
            Shared Courses: {org.course_scope_all ? "All Published SpacePoint" : `${detail.shared_courses.length} Selected`}
          </span>
          <span className="rounded-[10px] border border-primary/25 bg-primary/10 px-2.5 py-1 text-xs font-semibold text-primary">
            Quiz Bank:{" "}
            {org.quiz_scope === "all"
              ? "All Platform Templates"
              : org.quiz_scope === "selected"
              ? `${(org.allowed_quiz_template_ids ?? []).length} Selected Templates`
              : "Org Authored Only"}
          </span>
        </div>
      </div>

      {/* 5 Quota Progress Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {quotaCards.map((qcItem) => {
          const pct = quotaPct(qcItem.used, qcItem.limit)
          return (
            <div
              key={qcItem.label}
              className="rounded-[10px] border border-border bg-card p-5"
            >
              <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {qcItem.label}
              </div>
              <div className="mt-2 flex items-baseline gap-1.5">
                <span className="text-2xl font-bold text-foreground">{qcItem.used}</span>
                <span className="text-xs text-muted-foreground">/ {qcItem.limit ?? "Unlimited"}</span>
              </div>
              {qcItem.limit != null && qcItem.limit > 0 && (
                <div className="mt-2.5 h-1.5 w-full overflow-hidden rounded-[10px] bg-muted">
                  <div
                    className="h-full rounded-[10px] bg-primary transition-all"
                    style={{ width: `${pct}%` }}
                  />
                </div>
              )}
              <div className="mt-2 text-xs text-muted-foreground">{qcItem.sub}</div>
            </div>
          )
        })}
      </div>

      {/* Direct-on-Background Tabs */}
      <div className="flex flex-wrap items-center gap-2 border-b border-border pb-3">
        {tabs.map((t) => {
          const active = activeTab === t.id
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setActiveTab(t.id)}
              className={cn(
                "inline-flex items-center gap-2 rounded-[10px] border px-4 py-2 text-xs font-semibold transition-colors",
                active
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border bg-card text-muted-foreground hover:border-primary/50 hover:text-foreground"
              )}
            >
              <span>{t.label}</span>
              {t.count !== null && (
                <span
                  className={cn(
                    "rounded-[10px] px-2 py-0.5 text-xs font-bold",
                    active ? "bg-background/20 text-primary-foreground" : "bg-muted text-foreground"
                  )}
                >
                  {t.count}
                </span>
              )}
            </button>
          )
        })}
      </div>

      {/* TAB 1: Overview & Activity */}
      {activeTab === "overview" && (
        <div className="space-y-6">
          {/* Two Summary Panels */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {/* Active & Recent Cohorts Snapshot */}
            <div className="rounded-[10px] border border-border bg-card p-5">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-base font-bold text-foreground">Cohorts Snapshot</h2>
                <button
                  type="button"
                  onClick={() => setActiveTab("programs")}
                  className="text-xs font-semibold text-primary hover:underline"
                >
                  View all ({detail.cohorts.length})
                </button>
              </div>
              {detail.cohorts.length === 0 ? (
                <div className="rounded-[10px] border border-border bg-background p-5 text-center text-xs text-muted-foreground">
                  No cohorts created by this organization yet.
                </div>
              ) : (
                <div className="space-y-3">
                  {detail.cohorts.slice(0, 5).map((c) => (
                    <SubCard key={c.id}>
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div>
                          <Link
                            to="/operations/cohorts/$cohortId"
                            params={{ cohortId: c.id }}
                            className="text-sm font-bold text-foreground hover:text-primary"
                          >
                            {c.name}
                          </Link>
                          <div className="mt-1 text-xs text-muted-foreground">
                            {c.program_name}
                          </div>
                        </div>
                        <span
                          className={cn(
                            "rounded-[10px] border px-2.5 py-1 text-xs font-semibold uppercase",
                            c.status === "running"
                              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                              : "border-border bg-muted text-muted-foreground"
                          )}
                        >
                          {c.status}
                        </span>
                      </div>
                      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground">
                        <span>
                          Students: {c.enrolled_count}
                          {c.capacity ? ` / ${c.capacity}` : ""}
                        </span>
                        <span>Observers: {c.observers_count}</span>
                        <span className="font-semibold text-foreground">
                          Avg Completion: {c.completion_pct}%
                        </span>
                      </div>
                      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-[10px] bg-muted">
                        <div
                          className="h-full rounded-[10px] bg-primary"
                          style={{ width: `${c.completion_pct}%` }}
                        />
                      </div>
                    </SubCard>
                  ))}
                </div>
              )}
            </div>

            {/* Programs & Learning Checklists Snapshot */}
            <div className="rounded-[10px] border border-border bg-card p-5">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-base font-bold text-foreground">Programs & Checklists</h2>
                <button
                  type="button"
                  onClick={() => setActiveTab("programs")}
                  className="text-xs font-semibold text-primary hover:underline"
                >
                  Inspect ({detail.programs.length})
                </button>
              </div>
              {detail.programs.length === 0 ? (
                <div className="rounded-[10px] border border-border bg-background p-5 text-center text-xs text-muted-foreground">
                  No programs created yet.
                </div>
              ) : (
                <div className="space-y-3">
                  {detail.programs.slice(0, 5).map((p) => (
                    <SubCard key={p.id}>
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="text-sm font-bold text-foreground">{p.name}</div>
                        <span
                          className={cn(
                            "rounded-[10px] border px-2.5 py-1 text-xs font-semibold",
                            p.active
                              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                              : "border-border bg-muted text-muted-foreground"
                          )}
                        >
                          {p.active ? "Active" : "Inactive"}
                        </span>
                      </div>
                      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                        <span className="rounded-[10px] border border-border bg-muted px-2.5 py-1 text-foreground">
                          Type: {p.program_type}
                        </span>
                        <span className="rounded-[10px] border border-border bg-muted px-2.5 py-1">
                          {p.cohorts_count} cohorts
                        </span>
                        <span className="rounded-[10px] border border-border bg-muted px-2.5 py-1">
                          {p.checklist_items.length} checklist steps
                        </span>
                      </div>
                    </SubCard>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Quick 360 Activity Counters */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-[10px] border border-border bg-card p-5">
              <div className="flex items-center justify-between text-xs font-semibold uppercase text-muted-foreground">
                <span>Authored Courses</span>
                <BookOpen className="h-4 w-4 text-primary" />
              </div>
              <div className="mt-2 text-2xl font-bold text-foreground">{detail.authored_courses.length}</div>
              <div className="mt-1 text-xs text-muted-foreground">
                {detail.shared_courses.length} shared SpacePoint courses
              </div>
            </div>
            <div className="rounded-[10px] border border-border bg-card p-5">
              <div className="flex items-center justify-between text-xs font-semibold uppercase text-muted-foreground">
                <span>Quiz Bank</span>
                <HelpCircle className="h-4 w-4 text-primary" />
              </div>
              <div className="mt-2 text-2xl font-bold text-foreground">
                {org.quiz_templates_authored_count ?? detail.quiz_templates.length} templates
              </div>
              <div className="mt-1 text-xs text-muted-foreground">
                {org.quiz_questions_authored_count ?? 0} authored questions
              </div>
            </div>
            <div className="rounded-[10px] border border-border bg-card p-5">
              <div className="flex items-center justify-between text-xs font-semibold uppercase text-muted-foreground">
                <span>Invite Batches</span>
                <Ticket className="h-4 w-4 text-primary" />
              </div>
              <div className="mt-2 text-2xl font-bold text-foreground">{detail.invite_batches.length}</div>
              <div className="mt-1 text-xs text-muted-foreground">
                {org.invite_used_count ?? 0} / {org.invite_max_count ?? 0} redemptions
              </div>
            </div>
            <div className="rounded-[10px] border border-border bg-card p-5">
              <div className="flex items-center justify-between text-xs font-semibold uppercase text-muted-foreground">
                <span>Landing Pages</span>
                <Globe className="h-4 w-4 text-emerald-500" />
              </div>
              <div className="mt-2 text-2xl font-bold text-foreground">{detail.landing_pages.length}</div>
              <div className="mt-1 text-xs text-muted-foreground">
                {detail.landing_pages.filter((ev) => ev.is_published).length} published live
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: Programs & Cohorts */}
      {activeTab === "programs" && (
        <div className="space-y-6">
          <div className="rounded-[10px] border border-border bg-card p-5">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-base font-bold text-foreground">
                Programs & Curriculum Checklists ({detail.programs.length})
              </h2>
              <Button asChild variant="outline" className="h-8 rounded-[10px] px-3 text-xs font-semibold">
                <Link
                  to="/lms-authoring/curriculum"
                  search={{ programId: undefined, cohortId: undefined, tab: undefined }}
                >
                  Open Curriculum Manager
                  <ArrowUpRight className="h-3.5 w-3.5" />
                </Link>
              </Button>
            </div>

            {detail.programs.length === 0 ? (
              <div className="rounded-[10px] border border-border bg-background p-6 text-center text-xs text-muted-foreground">
                No programs configured for this organization.
              </div>
            ) : (
              <div className="space-y-3">
                {detail.programs.map((prog) => {
                  const isOpen = !!expandedPrograms[prog.id]
                  return (
                    <SubCard key={prog.id}>
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div className="flex flex-wrap items-center gap-2.5">
                          <button
                            type="button"
                            onClick={() =>
                              setExpandedPrograms((prev) => ({ ...prev, [prog.id]: !prev[prog.id] }))
                            }
                            className="inline-flex items-center gap-2 text-left text-sm font-bold text-foreground hover:text-primary"
                          >
                            {isOpen ? (
                              <ChevronDown className="h-4 w-4 text-primary" />
                            ) : (
                              <ChevronRight className="h-4 w-4 text-primary" />
                            )}
                            {prog.name}
                          </button>
                          <span
                            className={cn(
                              "rounded-[10px] border px-2.5 py-0.5 text-xs font-semibold",
                              prog.active
                                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                                : "border-border bg-muted text-muted-foreground"
                            )}
                          >
                            {prog.active ? "Active" : "Inactive"}
                          </span>
                          <span className="rounded-[10px] border border-border bg-muted px-2.5 py-0.5 text-xs text-muted-foreground">
                            {prog.program_type}
                          </span>
                        </div>

                        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                          {prog.checklist_name && (
                            <span className="rounded-[10px] border border-primary/25 bg-primary/10 px-2.5 py-1 font-medium text-primary">
                              Checklist: {prog.checklist_name}
                            </span>
                          )}
                          <span className="rounded-[10px] border border-border bg-muted px-2.5 py-1">
                            {prog.cohorts_count} cohorts
                          </span>
                          <span className="rounded-[10px] border border-border bg-muted px-2.5 py-1">
                            {prog.checklist_items.length} steps
                          </span>
                        </div>
                      </div>

                      {isOpen && (
                        <div className="mt-4 border-t border-border pt-3">
                          {prog.checklist_items.length === 0 ? (
                            <div className="text-xs text-muted-foreground">
                              No LMS checklist steps attached to this program yet.
                            </div>
                          ) : (
                            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                              {prog.checklist_items.map((step) => (
                                <div
                                  key={step.id}
                                  className="flex items-center justify-between gap-2 rounded-[10px] border border-border bg-card px-3 py-2 text-xs"
                                >
                                  <div className="flex items-center gap-2">
                                    <span className="font-mono font-bold text-primary">
                                      #{step.position}
                                    </span>
                                    <span className="font-medium text-foreground">{step.title}</span>
                                  </div>
                                  <div className="flex items-center gap-1.5">
                                    <span className="rounded-[10px] border border-border bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                                      {step.item_type}
                                    </span>
                                    {step.optional && (
                                      <span className="rounded-[10px] border border-border bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                                        Optional
                                      </span>
                                    )}
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </SubCard>
                  )
                })}
              </div>
            )}
          </div>

          <div className="rounded-[10px] border border-border bg-card p-5">
            <h2 className="mb-4 text-base font-bold text-foreground">
              Organization Cohorts ({detail.cohorts.length})
            </h2>
            {detail.cohorts.length === 0 ? (
              <div className="rounded-[10px] border border-border bg-background p-6 text-center text-xs text-muted-foreground">
                No cohorts registered for this organization.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-border text-muted-foreground">
                      <th className="py-3 pr-4 font-semibold uppercase">Cohort</th>
                      <th className="py-3 pr-4 font-semibold uppercase">Program</th>
                      <th className="py-3 pr-4 font-semibold uppercase">Dates</th>
                      <th className="py-3 pr-4 font-semibold uppercase">Status</th>
                      <th className="py-3 pr-4 font-semibold uppercase">Students</th>
                      <th className="py-3 pr-4 font-semibold uppercase">Observers</th>
                      <th className="py-3 pr-4 font-semibold uppercase">Sessions</th>
                      <th className="py-3 pr-4 font-semibold uppercase">Completion</th>
                      <th className="py-3 text-right font-semibold uppercase">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {detail.cohorts.map((c) => (
                      <tr key={c.id} className="hover:bg-muted/40">
                        <td className="py-3.5 pr-4 font-bold text-foreground">{c.name}</td>
                        <td className="py-3.5 pr-4 text-muted-foreground">{c.program_name}</td>
                        <td className="py-3.5 pr-4 text-muted-foreground">
                          {formatDateRange(c.starts_on, c.ends_on)}
                        </td>
                        <td className="py-3.5 pr-4">
                          <span
                            className={cn(
                              "rounded-[10px] border px-2.5 py-1 font-semibold uppercase",
                              c.status === "running"
                                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                                : "border-border bg-muted text-muted-foreground"
                            )}
                          >
                            {c.status}
                          </span>
                        </td>
                        <td className="py-3.5 pr-4 text-foreground">
                          {c.enrolled_count}
                          {c.capacity ? ` / ${c.capacity}` : ""}
                        </td>
                        <td className="py-3.5 pr-4 text-muted-foreground">{c.observers_count}</td>
                        <td className="py-3.5 pr-4 text-muted-foreground">{c.sessions_count}</td>
                        <td className="py-3.5 pr-4">
                          <div className="flex items-center gap-2">
                            <div className="h-1.5 w-20 overflow-hidden rounded-[10px] bg-muted">
                              <div
                                className="h-full rounded-[10px] bg-primary"
                                style={{ width: `${c.completion_pct}%` }}
                              />
                            </div>
                            <span className="font-semibold text-foreground">{c.completion_pct}%</span>
                          </div>
                        </td>
                        <td className="py-3.5 text-right">
                          <Button asChild variant="outline" size="sm" className="h-7 rounded-[10px] px-3 text-xs font-semibold">
                            <Link
                              to="/operations/cohorts/$cohortId"
                              params={{ cohortId: c.id }}
                              search={{ from: `/operations/organizations/${orgId}` } as never}
                            >
                              Open Cohort
                              <ArrowUpRight className="h-3.5 w-3.5" />
                            </Link>
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 3: Students & Invite Codes */}
      {activeTab === "students" && (
        <div className="space-y-6">
          <div className="rounded-[10px] border border-border bg-card p-5">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-base font-bold text-foreground">
                Invite Code Batches ({detail.invite_batches.length})
              </h2>
              <Button asChild variant="outline" className="h-8 rounded-[10px] px-3 text-xs font-semibold">
                <Link to="/lms-authoring/invite-codes">
                  Manage All Invite Codes
                  <ArrowUpRight className="h-3.5 w-3.5" />
                </Link>
              </Button>
            </div>
            {detail.invite_batches.length === 0 ? (
              <div className="rounded-[10px] border border-border bg-background p-6 text-center text-xs text-muted-foreground">
                No invite batches issued by this organization yet.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-border text-muted-foreground">
                      <th className="py-3 pr-4 font-semibold uppercase">Code</th>
                      <th className="py-3 pr-4 font-semibold uppercase">Label</th>
                      <th className="py-3 pr-4 font-semibold uppercase">Kind</th>
                      <th className="py-3 pr-4 font-semibold uppercase">Target Grant</th>
                      <th className="py-3 pr-4 font-semibold uppercase">Usage</th>
                      <th className="py-3 pr-4 font-semibold uppercase">Expires</th>
                      <th className="py-3 pr-4 font-semibold uppercase">Status</th>
                      <th className="py-3 text-right font-semibold uppercase">Copy</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {detail.invite_batches.map((inv) => (
                      <tr key={inv.id} className="hover:bg-muted/40">
                        <td className="py-3.5 pr-4 font-mono font-bold text-primary">{inv.code}</td>
                        <td className="py-3.5 pr-4 text-foreground">{inv.label || "Untitled Batch"}</td>
                        <td className="py-3.5 pr-4 uppercase text-muted-foreground">{inv.kind}</td>
                        <td className="py-3.5 pr-4 text-muted-foreground">{inv.granted_target || "Unspecified"}</td>
                        <td className="py-3.5 pr-4 text-foreground">
                          {inv.used_count} / {inv.max_uses}
                        </td>
                        <td className="py-3.5 pr-4 text-muted-foreground">
                          {inv.expires_at ? formatShortDate(inv.expires_at) : "Never"}
                        </td>
                        <td className="py-3.5 pr-4">
                          <span
                            className={cn(
                              "rounded-[10px] border px-2.5 py-1 font-semibold",
                              inv.is_active
                                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                                : "border-border bg-muted text-muted-foreground"
                            )}
                          >
                            {inv.is_active ? "Active" : "Inactive"}
                          </span>
                        </td>
                        <td className="py-3.5 text-right">
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            className="h-7 rounded-[10px] px-3 text-xs font-semibold"
                            onClick={() => copyText(`inv-${inv.id}`, inv.code, "Invite code")}
                          >
                            {copiedKey === `inv-${inv.id}` ? (
                              <Check className="h-3.5 w-3.5 text-emerald-500" />
                            ) : (
                              <Copy className="h-3.5 w-3.5" />
                            )}
                            Copy
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-base font-bold text-foreground">
                Enrolled Students ({filteredStudents.length})
              </h2>
              <div className="flex flex-wrap items-center gap-2.5 sm:flex-nowrap">
                <div className="relative min-w-[240px]">
                  <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <input
                    type="text"
                    value={studentQuery}
                    onChange={(e) => setStudentQuery(e.target.value)}
                    placeholder="Filter students by name or email"
                    className="h-9 w-full rounded-[10px] border border-border bg-background pl-9 pr-3 text-xs text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none"
                  />
                </div>
                <select
                  aria-label="Filter enrolled students by cohort"
                  value={studentCohortFilter}
                  onChange={(e) => setStudentCohortFilter(e.target.value)}
                  className="h-9 w-auto shrink-0 rounded-[10px] border border-border bg-background px-3 text-xs font-medium text-foreground focus:border-primary focus:outline-none"
                >
                  <option value="all">All Cohorts</option>
                  {detail.cohorts.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="rounded-[10px] border border-border bg-card p-5">
              {filteredStudents.length === 0 ? (
                <div className="rounded-[10px] border border-border bg-background p-6 text-center text-xs text-muted-foreground">
                  No enrolled students match the current filter.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-border text-muted-foreground">
                        <th className="py-3 pr-4 font-semibold uppercase">Student</th>
                        <th className="py-3 pr-4 font-semibold uppercase">Contact</th>
                        <th className="py-3 pr-4 font-semibold uppercase">Cohort</th>
                        <th className="py-3 pr-4 font-semibold uppercase">Status</th>
                        <th className="py-3 pr-4 font-semibold uppercase">Enrolled</th>
                        <th className="py-3 pr-4 font-semibold uppercase">Progress</th>
                        <th className="py-3 text-right font-semibold uppercase">Profile</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {filteredStudents.map((st) => (
                        <tr key={st.registration_id} className="hover:bg-muted/40">
                          <td className="py-3.5 pr-4 font-bold text-foreground">{st.full_name}</td>
                          <td className="py-3.5 pr-4 text-muted-foreground">
                            <div>{st.email}</div>
                            {st.phone && <div>{st.phone}</div>}
                          </td>
                          <td className="py-3.5 pr-4 text-foreground">{st.cohort_name}</td>
                          <td className="py-3.5 pr-4">
                            <span className="rounded-[10px] border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 font-semibold uppercase text-emerald-700 dark:text-emerald-300">
                              {st.status}
                            </span>
                          </td>
                          <td className="py-3.5 pr-4 text-muted-foreground">{formatShortDate(st.enrolled_at)}</td>
                          <td className="py-3.5 pr-4">
                            <div className="flex items-center gap-2">
                              <div className="h-1.5 w-20 overflow-hidden rounded-[10px] bg-muted">
                                <div
                                  className="h-full rounded-[10px] bg-primary"
                                  style={{ width: `${st.completion_pct}%` }}
                                />
                              </div>
                              <span className="font-semibold text-foreground">{st.completion_pct}%</span>
                            </div>
                          </td>
                          <td className="py-3.5 text-right">
                            {st.user_id ? (
                              <Button asChild variant="outline" size="sm" className="h-7 rounded-[10px] px-3 text-xs font-semibold">
                                <Link
                                  to="/lms-authoring/students/$userId"
                                  params={{ userId: st.user_id }}
                                  search={{ from: undefined }}
                                >
                                  LMS Profile
                                  <ArrowUpRight className="h-3.5 w-3.5" />
                                </Link>
                              </Button>
                            ) : (
                              <span className="text-muted-foreground">Contact Only</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* TAB 4: LMS Courses & Quiz Bank */}
      {activeTab === "courses" && (
        <div className="space-y-6">
          {/* Org-Authored Courses */}
          <div className="rounded-[10px] border border-border bg-card p-5">
            <h2 className="mb-4 text-base font-bold text-foreground">
              Organization-Authored Courses ({detail.authored_courses.length})
            </h2>
            {detail.authored_courses.length === 0 ? (
              <div className="rounded-[10px] border border-border bg-background p-6 text-center text-xs text-muted-foreground">
                This organization has not authored any LMS courses yet.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-border text-muted-foreground">
                      <th className="py-3 pr-4 font-semibold uppercase">Course</th>
                      <th className="py-3 pr-4 font-semibold uppercase">Track</th>
                      <th className="py-3 pr-4 font-semibold uppercase">Modules</th>
                      <th className="py-3 pr-4 font-semibold uppercase">Enrolled</th>
                      <th className="py-3 pr-4 font-semibold uppercase">Review Status</th>
                      <th className="py-3 text-right font-semibold uppercase">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {detail.authored_courses.map((c) => {
                      const awaitingReview = !c.is_published && c.submitted_for_review_at !== null
                      return (
                        <tr key={c.id} className="hover:bg-muted/40">
                          <td className="py-3.5 pr-4 font-bold text-foreground">{c.title}</td>
                          <td className="py-3.5 pr-4 text-muted-foreground">{c.track || "General"}</td>
                          <td className="py-3.5 pr-4 text-muted-foreground">{c.modules_count}</td>
                          <td className="py-3.5 pr-4 text-foreground">{c.enrolled_count}</td>
                          <td className="py-3.5 pr-4">
                            {c.is_published ? (
                              <span className="rounded-[10px] border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 font-semibold text-emerald-700 dark:text-emerald-300">
                                Published
                              </span>
                            ) : awaitingReview ? (
                              <span className="rounded-[10px] border border-primary/30 bg-primary/10 px-2.5 py-1 font-semibold text-primary">
                                Pending Review
                              </span>
                            ) : (
                              <span className="rounded-[10px] border border-border bg-muted px-2.5 py-1 font-semibold text-muted-foreground">
                                Draft
                              </span>
                            )}
                          </td>
                          <td className="py-3.5 text-right">
                            <div className="inline-flex flex-wrap items-center justify-end gap-2">
                              {c.is_published ? (
                                <Button
                                  type="button"
                                  variant="destructive"
                                  size="sm"
                                  className="h-7 rounded-[10px] px-3 text-xs font-semibold"
                                  disabled={coursePublishMut.isPending}
                                  onClick={() =>
                                    coursePublishMut.mutate({ courseId: c.id, isPublished: false })
                                  }
                                >
                                  Unpublish
                                </Button>
                              ) : (
                                <Button
                                  type="button"
                                  size="sm"
                                  className="h-7 rounded-[10px] bg-emerald-600 px-3 text-xs font-semibold text-white hover:bg-emerald-500"
                                  disabled={coursePublishMut.isPending}
                                  onClick={() =>
                                    coursePublishMut.mutate({ courseId: c.id, isPublished: true })
                                  }
                                >
                                  Approve & Publish
                                </Button>
                              )}
                              <Button asChild variant="outline" size="sm" className="h-7 rounded-[10px] px-3 text-xs font-semibold">
                                <Link
                                  to="/lms-authoring/courses/$courseId"
                                  params={{ courseId: c.id }}
                                >
                                  Inspect
                                  <ArrowUpRight className="h-3.5 w-3.5" />
                                </Link>
                              </Button>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Shared SpacePoint Platform Courses */}
          <div className="rounded-[10px] border border-border bg-card p-5">
            <h2 className="mb-4 text-base font-bold text-foreground">
              Shared SpacePoint Platform Courses ({detail.shared_courses.length})
            </h2>
            {detail.shared_courses.length === 0 ? (
              <div className="rounded-[10px] border border-border bg-background p-6 text-center text-xs text-muted-foreground">
                No platform courses currently shared with this organization.
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {detail.shared_courses.map((sc) => (
                  <Link
                    key={sc.id}
                    to="/lms-authoring/courses/$courseId"
                    params={{ courseId: sc.id }}
                    className={cn(SUB_CARD_CLASS, "hover:border-primary")}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-sm font-bold text-foreground">{sc.title}</span>
                      <ArrowUpRight className="h-4 w-4 shrink-0 text-primary" />
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                      {sc.track && (
                        <span className="rounded-[10px] border border-border bg-muted px-2 py-0.5">
                          {sc.track}
                        </span>
                      )}
                      {sc.level && (
                        <span className="rounded-[10px] border border-border bg-muted px-2 py-0.5">
                          {sc.level}
                        </span>
                      )}
                      <span className="rounded-[10px] border border-border bg-muted px-2 py-0.5">
                        {sc.modules_count} modules
                      </span>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </div>

          {/* Org Quiz Bank */}
          <div className="rounded-[10px] border border-border bg-card p-5">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-base font-bold text-foreground">
                Organization Quiz Templates ({detail.quiz_templates.length})
              </h2>
              <Button asChild variant="outline" className="h-8 rounded-[10px] px-3 text-xs font-semibold">
                <Link to="/lms-authoring/quiz-bank">
                  Open Quiz Bank
                  <ArrowUpRight className="h-3.5 w-3.5" />
                </Link>
              </Button>
            </div>

            {detail.quiz_templates.length === 0 ? (
              <div className="rounded-[10px] border border-border bg-background p-6 text-center text-xs text-muted-foreground">
                No custom quiz templates authored by this organization.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-border text-muted-foreground">
                      <th className="py-3 pr-4 font-semibold uppercase">Template Name</th>
                      <th className="py-3 pr-4 font-semibold uppercase">Questions</th>
                      <th className="py-3 pr-4 font-semibold uppercase">Linked Cohorts</th>
                      <th className="py-3 pr-4 font-semibold uppercase">Status</th>
                      <th className="py-3 text-right font-semibold uppercase">Created</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {detail.quiz_templates.map((qt) => (
                      <tr key={qt.id} className="hover:bg-muted/40">
                        <td className="py-3.5 pr-4 font-bold text-foreground">{qt.name}</td>
                        <td className="py-3.5 pr-4 text-foreground">{qt.questions_count} questions</td>
                        <td className="py-3.5 pr-4">
                          {qt.linked_cohorts.length === 0 ? (
                            <span className="text-muted-foreground">Not linked yet</span>
                          ) : (
                            <div className="flex flex-wrap gap-1.5">
                              {qt.linked_cohorts.map((cname) => (
                                <span
                                  key={cname}
                                  className="rounded-[10px] border border-border bg-muted px-2 py-0.5 text-foreground"
                                >
                                  {cname}
                                </span>
                              ))}
                            </div>
                          )}
                        </td>
                        <td className="py-3.5 pr-4">
                          <span
                            className={cn(
                              "rounded-[10px] border px-2.5 py-1 font-semibold",
                              qt.is_active
                                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                                : "border-border bg-muted text-muted-foreground"
                            )}
                          >
                            {qt.is_active ? "Active" : "Inactive"}
                          </span>
                        </td>
                        <td className="py-3.5 text-right text-muted-foreground">
                          {formatShortDate(qt.created_at)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 5: Landing Pages */}
      {activeTab === "landing" && (
        <div className="rounded-[10px] border border-border bg-card p-5">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-base font-bold text-foreground">
              Event Landing Pages ({detail.landing_pages.length})
            </h2>
            <Button asChild variant="outline" className="h-8 rounded-[10px] px-3 text-xs font-semibold">
              <Link to="/operations/website/events">
                Open Website Events
                <ArrowUpRight className="h-3.5 w-3.5" />
              </Link>
            </Button>
          </div>

          {detail.landing_pages.length === 0 ? (
            <div className="rounded-[10px] border border-border bg-background p-6 text-center text-xs text-muted-foreground">
              No public event landing pages created by this organization yet.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-border text-muted-foreground">
                    <th className="py-3 pr-4 font-semibold uppercase">Title</th>
                    <th className="py-3 pr-4 font-semibold uppercase">Public Route</th>
                    <th className="py-3 pr-4 font-semibold uppercase">Linked Cohort</th>
                    <th className="py-3 pr-4 font-semibold uppercase">Registrations</th>
                    <th className="py-3 pr-4 font-semibold uppercase">Status</th>
                    <th className="py-3 pr-4 font-semibold uppercase">Updated</th>
                    <th className="py-3 text-right font-semibold uppercase">Preview</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {detail.landing_pages.map((ev) => (
                    <tr key={ev.id} className="hover:bg-muted/40">
                      <td className="py-3.5 pr-4 font-bold text-foreground">{ev.title}</td>
                      <td className="py-3.5 pr-4 font-mono text-primary">
                        /{ev.country}/{ev.slug}
                      </td>
                      <td className="py-3.5 pr-4 text-muted-foreground">
                        {ev.cohort_id && ev.cohort_name ? (
                          <Link
                            to="/operations/cohorts/$cohortId"
                            params={{ cohortId: ev.cohort_id }}
                            className="text-primary hover:underline"
                          >
                            {ev.cohort_name}
                          </Link>
                        ) : (
                          <span>Unlinked</span>
                        )}
                      </td>
                      <td className="py-3.5 pr-4 text-foreground">{ev.registrations_count}</td>
                      <td className="py-3.5 pr-4">
                        <span
                          className={cn(
                            "rounded-[10px] border px-2.5 py-1 font-semibold",
                            ev.is_published
                              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                              : "border-border bg-muted text-muted-foreground"
                          )}
                        >
                          {ev.is_published ? "Published Live" : "Draft"}
                        </span>
                      </td>
                      <td className="py-3.5 pr-4 text-muted-foreground">{formatShortDate(ev.updated_at)}</td>
                      <td className="py-3.5 text-right">
                        <Button asChild variant="outline" size="sm" className="h-7 rounded-[10px] px-3 text-xs font-semibold">
                          <a
                            href={`${WEBSITE_BASE_URL}/events/${ev.country}/${ev.slug}`}
                            target="_blank"
                            rel="noreferrer"
                          >
                            Live Page
                            <ExternalLink className="h-3.5 w-3.5" />
                          </a>
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* TAB 6: Team & Observers */}
      {activeTab === "team" && (
        <div className="rounded-[10px] border border-border bg-card p-5">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 className="text-base font-bold text-foreground">
              Organization Team & Cohort Observers ({detail.team.length})
            </h2>
            <Button
              type="button"
              size="sm"
              className="h-8 rounded-[10px] px-3 text-xs font-semibold"
              onClick={() => setInviteOpen(true)}
            >
              <UserPlus className="h-3.5 w-3.5" />
              Invite Member
            </Button>
          </div>

          {detail.team.length === 0 ? (
            <div className="rounded-[10px] border border-border bg-background p-6 text-center text-xs text-muted-foreground">
              No portal accounts associated with this organization.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-border text-muted-foreground">
                    <th className="py-3 pr-4 font-semibold uppercase">Member</th>
                    <th className="py-3 pr-4 font-semibold uppercase">Role</th>
                    <th className="py-3 pr-4 font-semibold uppercase">Contact</th>
                    <th className="py-3 pr-4 font-semibold uppercase">Card ID</th>
                    <th className="py-3 pr-4 font-semibold uppercase">Observer Cohorts</th>
                    <th className="py-3 pr-4 font-semibold uppercase">Account Status</th>
                    <th className="py-3 text-right font-semibold uppercase">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {detail.team.map((m) => (
                    <tr key={m.user_id} className="hover:bg-muted/40">
                      <td className="py-3.5 pr-4 font-bold text-foreground">{m.full_name}</td>
                      <td className="py-3.5 pr-4">
                        {m.role === "Owner" ? (
                          <span className="rounded-[10px] border border-primary/30 bg-primary/10 px-2.5 py-1 font-semibold text-primary">
                            Owner
                          </span>
                        ) : (
                          <select
                            aria-label={`Role for ${m.full_name}`}
                            value={m.org_role ?? "observer"}
                            disabled={memberRoleMut.isPending}
                            onChange={(e) =>
                              memberRoleMut.mutate({
                                userId: m.user_id,
                                orgRole: e.target.value,
                              })
                            }
                            className="h-8 rounded-[10px] border border-border bg-background px-2 text-xs font-semibold text-foreground focus:border-primary focus:outline-none"
                          >
                            {ORG_ASSIGNABLE_ROLES.map((r) => (
                              <option key={r.value} value={r.value}>
                                {r.label}
                              </option>
                            ))}
                          </select>
                        )}
                      </td>
                      <td className="py-3.5 pr-4 text-muted-foreground">
                        <div>{m.email}</div>
                        {m.phone && <div>{m.phone}</div>}
                      </td>
                      <td className="py-3.5 pr-4">
                        {m.card_id ? (
                          <span className="rounded-[10px] border border-primary/25 bg-primary/10 px-2.5 py-1 font-mono font-semibold text-primary">
                            {m.card_id}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">Unassigned</span>
                        )}
                      </td>
                      <td className="py-3.5 pr-4">
                        {m.observer_cohorts.length === 0 ? (
                          <span className="text-muted-foreground">All Org Scoped</span>
                        ) : (
                          <div className="flex flex-wrap gap-1.5">
                            {m.observer_cohorts.map((cname) => (
                              <span
                                key={cname}
                                className="rounded-[10px] border border-border bg-muted px-2 py-0.5 text-foreground"
                              >
                                {cname}
                              </span>
                            ))}
                          </div>
                        )}
                      </td>
                      <td className="py-3.5 pr-4">
                        <span
                          className={cn(
                            "rounded-[10px] border px-2.5 py-1 font-semibold uppercase",
                            m.invite_pending
                              ? "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300"
                              : m.status === "active"
                              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                              : "border-border bg-muted text-muted-foreground"
                          )}
                        >
                          {m.invite_pending ? "Invite pending" : m.status}
                        </span>
                      </td>
                      <td className="py-3.5 text-right">
                        <div className="inline-flex items-center justify-end gap-2">
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            className="h-7 rounded-[10px] px-3 text-xs font-semibold"
                            disabled={memberResetMut.isPending}
                            onClick={() => memberResetMut.mutate(m.user_id)}
                          >
                            {copiedKey === `member-${m.user_id}` ? (
                              <Check className="h-3.5 w-3.5 text-emerald-500" />
                            ) : (
                              <KeyRound className="h-3.5 w-3.5" />
                            )}
                            Send Link
                          </Button>
                          {m.role !== "Owner" && (
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              className="h-7 rounded-[10px] px-3 text-xs font-semibold text-destructive hover:text-destructive"
                              disabled={removeMemberMut.isPending}
                              onClick={() => {
                                if (
                                  window.confirm(
                                    `Remove ${m.full_name} from ${org.name_latin}? They lose all org access and cohort assignments.`
                                  )
                                ) {
                                  removeMemberMut.mutate(m.user_id)
                                }
                              }}
                            >
                              Remove
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Edit Quotas & Permissions Modal */}
      {editOpen && (
        <OrgAccountModal
          org={org}
          onClose={() => setEditOpen(false)}
          onSaved={() => setEditOpen(false)}
          onDeleted={() => navigate({ to: "/operations/organizations" })}
        />
      )}

      {inviteOpen && (
        <InviteOrgMemberModal
          orgId={orgId}
          orgName={org.name_latin}
          onClose={() => setInviteOpen(false)}
          onSuccess={() => {
            setInviteOpen(false)
            setActiveTab("team")
            invalidateOrgQueries()
          }}
        />
      )}
    </div>
  )
}


function InviteOrgMemberModal({
  orgId,
  orgName,
  onClose,
  onSuccess,
}: {
  orgId: string
  orgName: string
  onClose: () => void
  onSuccess: () => void
}) {
  const toast = useToast()
  const [fullName, setFullName] = useState("")
  const [email, setEmail] = useState("")
  const [phone, setPhone] = useState("")
  const [orgRole, setOrgRole] = useState<Exclude<OrgSandboxRole, "owner">>("coordinator")

  const mut = useMutation({
    mutationFn: () =>
      createOrganizationMember(orgId, {
        full_name: fullName.trim(),
        email: email.trim(),
        phone: phone.trim() || null,
        org_role: orgRole,
      }),
    onSuccess: (res) => {
      if (res.existing_account) {
        toast.success(
          res.invite_email_sent
            ? `Added ${res.full_name} — they can sign in with their existing account (email sent)`
            : `Added ${res.full_name} — they can sign in with their existing account`
        )
      } else {
        toast.success(
          res.invite_email_sent
            ? `Invite emailed to ${res.email}`
            : `Member added. Email failed — use Send Link to share it.`
        )
      }
      onSuccess()
    },
    onError: (err) => toast.error(getErrorMessage(err, "Could not invite this member")),
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="w-full max-w-md space-y-4 rounded-[12px] border border-border bg-card p-6 shadow-xl">
        <div>
          <h2 className="text-base font-bold text-foreground">Invite Team Member</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            New accounts get a set-password invite email. Existing SpacePoint accounts are
            linked to {orgName} and emailed a sign-in notice.
          </p>
        </div>

        <div className="space-y-3">
          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-muted-foreground">Full Name *</span>
            <input
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="e.g. Sarah Jenkins"
              className="h-9 rounded-[10px] border border-border bg-background px-3 text-sm focus:border-primary focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-muted-foreground">Email Address *</span>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="sarah@example.com"
              className="h-9 rounded-[10px] border border-border bg-background px-3 text-sm focus:border-primary focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-muted-foreground">Phone (optional)</span>
            <input
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+971 50 000 0000"
              className="h-9 rounded-[10px] border border-border bg-background px-3 text-sm focus:border-primary focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-muted-foreground">Organization Role</span>
            <select
              value={orgRole}
              onChange={(e) => setOrgRole(e.target.value as Exclude<OrgSandboxRole, "owner">)}
              className="h-9 rounded-[10px] border border-border bg-background px-3 text-sm text-foreground focus:border-primary focus:outline-none"
            >
              {ORG_ASSIGNABLE_ROLES.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
            <span className="text-[11px] text-muted-foreground">
              {ORG_ASSIGNABLE_ROLES.find((r) => r.value === orgRole)?.hint}
            </span>
          </label>
        </div>

        <div className="flex items-center justify-end gap-2 pt-2">
          <Button type="button" variant="outline" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="button"
            size="sm"
            disabled={!fullName.trim() || !email.trim() || mut.isPending}
            onClick={() => mut.mutate()}
          >
            {mut.isPending ? "Sending invite…" : "Send Invite"}
          </Button>
        </div>
      </div>
    </div>
  )
}

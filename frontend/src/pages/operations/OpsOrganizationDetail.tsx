import { useMemo, useState } from "react"
import { Link, useNavigate, useParams } from "@tanstack/react-router"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  ArrowLeft,
  ArrowRight,
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
  Layers,
  Mail,
  MapPin,
  Phone,
  Plus,
  Search,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  Ticket,
  UserPlus,
  Users,
  Warehouse as WarehouseIcon,
  X,
} from "lucide-react"
import { createOrgProgramApi } from "@/api/organizationPrograms"
import { createCohortApi, updateCohortApi } from "@/api/sessions/cohorts"
import { getFilteredProgramsApi, listProgramVariationsApi } from "@/api/sessions/programs"
import { getLocationsApi, getWarehousesApi } from "@/api/inventory"
import { QuickCreateLocationModal } from "@/pages/admin/components/QuickCreateLocationModal"
import { CoordinatorAccessPicker } from "@/components/organization/CoordinatorAccessPicker"
import type { Location } from "@/types/inventory"
import type { Program, ProgramVariation } from "@/types/sessions"
import {
  createOrganizationMember,
  createOrganizationMemberResetLink,
  getAdminOrganizationDetail,
  getAdminOrganizationResetLink,
  memberOrgRoles,
  removeOrganizationMember,
  toggleOrganizationCoursePublish,
  updateAdminOrganizationAccount,
  updateOrganizationMember,
  type OrgCohortDetail,
  type OrgProgramDetail,
  type OrgSandboxRole,
  type OrgSharedProgram,
} from "@/api/websiteEvents"
import { OrgRolePickerGrid, OrgRoleToggleRow } from "@/components/organization/OrgRolePills"
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
  const [programViewMode, setProgramViewMode] = useState<"program" | "worklist">("program")
  const [programSearch, setProgramSearch] = useState("")
  const [programTypeFilter, setProgramTypeFilter] = useState("")
  const [cohortStatusFilter, setCohortStatusFilter] = useState("")
  const [expandedPastMap, setExpandedPastMap] = useState<Record<string, boolean>>({})
  const [studentQuery, setStudentQuery] = useState("")
  const [studentCohortFilter, setStudentCohortFilter] = useState("all")
  const [copiedKey, setCopiedKey] = useState<string | null>(null)
  const [inviteOpen, setInviteOpen] = useState(false)
  const [createProgramOpen, setCreateProgramOpen] = useState(false)
  const [createCohortOpen, setCreateCohortOpen] = useState(false)
  const [cohortDefaultProgramId, setCohortDefaultProgramId] = useState("")
  const [cohortDefaultMode, setCohortDefaultMode] = useState<"spacepoint" | "partner" | undefined>(undefined)

  const allOrgPrograms = useMemo(() => {
    const base = detail?.programs ?? []
    const seen = new Set(base.map((p) => p.id))
    const sharedExtras: OrgProgramDetail[] = (detail?.shared_programs ?? [])
      .filter((sp) => !seen.has(sp.id))
      .map((sp) => ({
        id: sp.id,
        code: sp.code,
        name: sp.name,
        program_type: sp.program_type,
        description: null,
        is_org_owned: false,
        active: sp.active,
        lms_program_id: null,
        checklist_name: null,
        certificate_required: false,
        cohorts_count: 0,
        checklist_items: [],
      }))
    return [...base, ...sharedExtras]
  }, [detail?.programs, detail?.shared_programs])

  const cohortsByProgramId = useMemo(() => {
    const map = new Map<string, typeof detail extends undefined ? never : NonNullable<typeof detail>["cohorts"]>()
    for (const c of detail?.cohorts ?? []) {
      const list = map.get(c.program_id) ?? []
      list.push(c)
      map.set(c.program_id, list)
    }
    return map
  }, [detail?.cohorts])

  const filteredOrgPrograms = useMemo(() => {
    const q = programSearch.trim().toLowerCase()
    return allOrgPrograms.filter((p) => {
      if (programTypeFilter && p.program_type !== programTypeFilter) return false
      if (!q) return true
      const matchesProgram =
        p.name.toLowerCase().includes(q) || (p.code ?? "").toLowerCase().includes(q)
      if (matchesProgram) return true
      const programCohorts = cohortsByProgramId.get(p.id) ?? []
      return programCohorts.some(
        (c) =>
          c.name.toLowerCase().includes(q) ||
          (c.location_name ?? "").toLowerCase().includes(q)
      )
    })
  }, [allOrgPrograms, cohortsByProgramId, programTypeFilter, programSearch])

  const filteredOrgWorklist = useMemo(() => {
    const q = programSearch.trim().toLowerCase()
    return (detail?.cohorts ?? []).filter((c) => {
      if (cohortStatusFilter && c.status !== cohortStatusFilter) return false
      if (!q) return true
      return (
        c.name.toLowerCase().includes(q) ||
        (c.program_name ?? "").toLowerCase().includes(q) ||
        (c.location_name ?? "").toLowerCase().includes(q)
      )
    })
  }, [detail?.cohorts, cohortStatusFilter, programSearch])

  const togglePast = (programId: string) => {
    setExpandedPastMap((prev) => ({
      ...prev,
      [programId]: !prev[programId],
    }))
  }

  const [coordCohortTarget, setCoordCohortTarget] = useState<OrgCohortDetail | null>(null)

  const openLaunchCohort = (programId?: string, isOrgOwned?: boolean) => {
    setCohortDefaultProgramId(programId ?? "")
    setCohortDefaultMode(
      programId === undefined ? undefined : isOrgOwned !== false ? "partner" : "spacepoint"
    )
    setCreateCohortOpen(true)
  }

  const invalidateOrgQueries = () => {
    void qc.invalidateQueries({ queryKey: ["admin-organization-detail", orgId] })
    void qc.invalidateQueries({ queryKey: ["admin-website-organizations"] })
    void qc.invalidateQueries({ queryKey: ["sessions-cohorts"] })
    void qc.invalidateQueries({ queryKey: ["org-programs-overview"] })
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
    mutationFn: ({ userId, orgRoles }: { userId: string; orgRoles: OrgSandboxRole[] }) =>
      updateOrganizationMember(orgId, userId, orgRoles),
    onSuccess: () => {
      invalidateOrgQueries()
      toast.success("Member roles updated")
    },
    onError: (err) => toast.error(getErrorMessage(err, "Could not update member roles")),
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
          <span className="rounded-[10px] border border-primary/25 bg-primary/10 px-2.5 py-1 text-xs font-semibold text-primary">
            Shared Programs:{" "}
            {org.program_scope === "all"
              ? "All Active SpacePoint"
              : org.program_scope === "selected"
                ? `${detail.shared_programs?.length ?? (org.allowed_program_ids ?? []).length} Selected`
                : "Org Programs Only"}
          </span>
          <span className="rounded-[10px] border border-primary/25 bg-primary/10 px-2.5 py-1 text-xs font-semibold text-primary">
            Program Pages:{" "}
            {org.program_page_access === "direct"
              ? "Publish Directly"
              : org.program_page_access === "review"
                ? "Submit for Review"
                : "Disabled"}
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
                  : "border-border bg-card text-muted-foreground hover:bg-muted/40 hover:text-foreground"
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
              <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-base font-bold text-foreground">Cohorts Snapshot</h2>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => openLaunchCohort()}
                    className="inline-flex items-center gap-1.5 h-8 px-3 rounded-[10px] bg-primary text-primary-foreground text-xs font-bold hover:opacity-90 transition-colors cursor-pointer"
                  >
                    <Plus size={13} /> Add Cohort
                  </button>
                  <button
                    type="button"
                    onClick={() => setActiveTab("programs")}
                    className="inline-flex items-center gap-1 h-8 px-3 rounded-[10px] border border-border bg-background text-xs font-bold text-foreground hover:bg-muted transition-colors cursor-pointer"
                  >
                    View All ({detail.cohorts.length}) <ArrowRight size={12} />
                  </button>
                </div>
              </div>
              {detail.cohorts.length === 0 ? (
                <div className="rounded-[10px] border border-dashed border-border bg-background p-6 text-center">
                  <p className="text-xs font-semibold text-muted-foreground">
                    No cohorts scheduled for this organization yet.
                  </p>
                  <button
                    type="button"
                    onClick={() => openLaunchCohort()}
                    className="mt-3 inline-flex items-center gap-1.5 h-8 px-3 rounded-[10px] bg-primary text-primary-foreground text-xs font-bold hover:opacity-90 transition-colors cursor-pointer"
                  >
                    <Plus size={13} /> Launch First Cohort
                  </button>
                </div>
              ) : (
                <div className="space-y-3">
                  {detail.cohorts.slice(0, 5).map((c) => (
                    <SubCard key={c.id}>
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div>
                          <div className="flex flex-wrap items-center gap-2">
                            <Link
                              to="/operations/cohorts/$cohortId"
                              params={{ cohortId: c.id }}
                              search={{ from: `/operations/organizations/${orgId}` } as never}
                              className="text-sm font-bold text-foreground hover:text-primary transition-colors"
                            >
                              {c.name}
                            </Link>
                            <OpsCohortStatusBadge status={c.status} />
                            <span
                              className={cn(
                                "rounded-full px-2 py-0.5 text-[10px] font-semibold border",
                                c.management_mode === "spacepoint"
                                  ? "border-violet-500/30 bg-violet-500/15 text-violet-700 dark:text-violet-300"
                                  : "border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                              )}
                            >
                              {c.management_mode === "spacepoint" ? "Delivered by SpacePoint" : "Partner-run"}
                            </span>
                          </div>
                          <div className="mt-1 text-xs text-muted-foreground">
                            {c.program_name}
                            {c.location_name ? ` · ${c.location_name}` : ""}
                          </div>
                        </div>

                        <Link
                          to="/operations/cohorts/$cohortId"
                          params={{ cohortId: c.id }}
                          search={{ from: `/operations/organizations/${orgId}` } as never}
                          className="inline-flex items-center gap-1 h-8 px-3 rounded-[10px] border border-border bg-background text-xs font-bold text-foreground hover:bg-muted transition-colors shrink-0"
                        >
                          Manage <ArrowRight size={12} />
                        </Link>
                      </div>
                      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground">
                        <span>
                          {c.enrolled_count}
                          {c.capacity ? ` / ${c.capacity}` : ""} Registered
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

            {/* Programs Snapshot */}
            <div className="rounded-[10px] border border-border bg-card p-5">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-base font-bold text-foreground">Programs</h2>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setCreateProgramOpen(true)}
                    className="inline-flex items-center gap-1.5 h-8 px-3 rounded-[10px] bg-primary text-primary-foreground text-xs font-bold hover:opacity-90 transition-colors cursor-pointer"
                  >
                    <Plus size={13} /> New Program
                  </button>
                  <button
                    type="button"
                    onClick={() => setActiveTab("programs")}
                    className="inline-flex items-center gap-1 h-8 px-3 rounded-[10px] border border-border bg-background text-xs font-bold text-foreground hover:bg-muted transition-colors cursor-pointer"
                  >
                    View All ({allOrgPrograms.length}) <ArrowRight size={12} />
                  </button>
                </div>
              </div>
              {allOrgPrograms.length === 0 ? (
                <div className="rounded-[10px] border border-dashed border-border bg-background p-6 text-center">
                  <p className="text-xs font-semibold text-muted-foreground">
                    No programs configured for this organization yet.
                  </p>
                  <button
                    type="button"
                    onClick={() => setCreateProgramOpen(true)}
                    className="mt-3 inline-flex items-center gap-1.5 h-8 px-3 rounded-[10px] bg-primary text-primary-foreground text-xs font-bold hover:opacity-90 transition-colors cursor-pointer"
                  >
                    <Plus size={13} /> New Program
                  </button>
                </div>
              ) : (
                <div className="space-y-3">
                  {allOrgPrograms.slice(0, 5).map((p) => {
                    const isOrgOwned = p.is_org_owned !== false
                    const cohortCount = (cohortsByProgramId.get(p.id) ?? []).length
                    return (
                      <SubCard key={p.id}>
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <Link
                                to="/operations/programs/$programId"
                                params={{ programId: p.id }}
                                className="text-sm font-bold text-foreground hover:text-primary transition-colors"
                              >
                                {p.name}
                              </Link>
                              <span className="text-xs font-bold px-2.5 py-0.5 rounded-[10px] bg-primary/10 text-primary border border-primary/20 capitalize">
                                {p.program_type}
                              </span>
                              {!isOrgOwned && (
                                <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-700 dark:text-amber-300 border border-amber-500/30">
                                  Shared by SpacePoint
                                </span>
                              )}
                            </div>
                            <div className="mt-1.5 text-xs text-muted-foreground">
                              {cohortCount} cohort{cohortCount === 1 ? "" : "s"}
                            </div>
                          </div>

                          <div className="flex items-center gap-2 shrink-0">
                            <button
                              type="button"
                              onClick={() => openLaunchCohort(p.id, isOrgOwned)}
                              className="inline-flex items-center gap-1 h-8 px-3 rounded-[10px] bg-primary text-primary-foreground text-xs font-bold hover:opacity-90 transition-colors cursor-pointer"
                            >
                              <Plus size={13} /> Add Cohort
                            </button>
                            <Link
                              to="/operations/programs/$programId"
                              params={{ programId: p.id }}
                              className="inline-flex items-center gap-1 h-8 px-3 rounded-[10px] border border-border bg-background text-xs font-bold text-foreground hover:bg-muted transition-colors"
                            >
                              Manage <ArrowRight size={12} />
                            </Link>
                          </div>
                        </div>
                      </SubCard>
                    )
                  })}
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

      {/* TAB 2: Programs & Cohorts (Identical layout & wording to Ops Programs.tsx) */}
      {activeTab === "programs" && (
        <div className="flex flex-col gap-6">
          {/* ── Page Header ───────────────────────────────────────────── */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <h2 className="text-2xl font-extrabold tracking-tight text-foreground">
                Programs
              </h2>
            </div>

            <div className="flex items-center gap-2 flex-wrap">
              <button
                type="button"
                onClick={() => setEditOpen(true)}
                className="inline-flex items-center gap-2 h-10 px-4 rounded-[10px] border border-border bg-card text-foreground text-sm font-semibold hover:bg-muted transition-colors cursor-pointer"
              >
                <SlidersHorizontal size={15} /> Shared Programs ({(detail.shared_programs ?? []).length})
              </button>
              <button
                type="button"
                onClick={() => setCreateProgramOpen(true)}
                className="inline-flex items-center gap-2 h-10 px-4 rounded-[10px] bg-primary text-primary-foreground text-sm font-semibold hover:opacity-90 transition-colors cursor-pointer"
              >
                <Plus size={16} /> New Program
              </button>
            </div>
          </div>

          {/* ── Filter & View Mode Controls ───────────────────────────── */}
          <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-center justify-between gap-3">
            <div className="flex flex-wrap flex-1 items-center gap-2 min-w-0">
              <div className="relative w-full sm:flex-1 sm:min-w-[200px]">
                <Search
                  size={15}
                  className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none"
                />
                <input
                  value={programSearch}
                  onChange={(e) => setProgramSearch(e.target.value)}
                  placeholder="Search program, cohort, or venue..."
                  className="w-full h-10 pl-10 pr-8 rounded-[10px] border border-border bg-card text-foreground text-sm font-medium focus:outline-none focus:border-primary transition-colors"
                />
                {programSearch && (
                  <button
                    type="button"
                    onClick={() => setProgramSearch("")}
                    aria-label="Clear search"
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground p-0.5 rounded-full transition-colors"
                  >
                    <X size={14} />
                  </button>
                )}
              </div>

              <select
                value={programTypeFilter}
                onChange={(e) => setProgramTypeFilter(e.target.value)}
                className="flex-1 sm:flex-none sm:w-44 shrink-0 h-10 px-3 rounded-[10px] border border-border bg-card text-foreground text-sm font-medium focus:outline-none focus:border-primary transition-colors cursor-pointer"
              >
                <option value="">All Types</option>
                <option value="workshop">Workshop</option>
                <option value="course">Course</option>
                <option value="info_session">Info session</option>
                <option value="competition">Competition</option>
              </select>

              {programViewMode === "worklist" && (
                <select
                  value={cohortStatusFilter}
                  onChange={(e) => setCohortStatusFilter(e.target.value)}
                  className="flex-1 sm:flex-none sm:w-44 shrink-0 h-10 px-3 rounded-[10px] border border-border bg-card text-foreground text-sm font-medium focus:outline-none focus:border-primary transition-colors cursor-pointer"
                >
                  <option value="">All Statuses</option>
                  <option value="running">Running</option>
                  <option value="registration_open">Registration open</option>
                  <option value="planned">Planned</option>
                  <option value="completed">Completed</option>
                  <option value="cancelled">Cancelled</option>
                </select>
              )}
            </div>

            <div className="inline-flex self-start sm:self-auto shrink-0 p-1 rounded-[10px] bg-muted/60 border border-border">
              <button
                type="button"
                onClick={() => setProgramViewMode("program")}
                className={`inline-flex items-center gap-1.5 h-8 px-3 rounded-[10px] text-xs font-bold transition-all cursor-pointer ${programViewMode === "program"
                    ? "bg-background text-foreground shadow-xs"
                    : "text-muted-foreground hover:text-foreground"
                  }`}
              >
                <Layers size={14} /> Program View
              </button>
              <button
                type="button"
                onClick={() => setProgramViewMode("worklist")}
                className={`inline-flex items-center gap-1.5 h-8 px-3 rounded-[10px] text-xs font-bold transition-all cursor-pointer ${programViewMode === "worklist"
                    ? "bg-background text-foreground shadow-xs"
                    : "text-muted-foreground hover:text-foreground"
                  }`}
              >
                <SlidersHorizontal size={14} /> Cohort View
              </button>
            </div>
          </div>

          {/* ── VIEW 1: PROGRAM-CENTRIC BLUEPRINT VIEW ─────────────────── */}
          {programViewMode === "program" && (
            <div className="space-y-6">
              {filteredOrgPrograms.length === 0 ? (
                <div className="p-12 text-center rounded-[10px] border border-border bg-card">
                  <p className="text-base font-bold text-foreground">No programs found</p>
                  <p className="text-sm text-muted-foreground mt-1">
                    Try clearing your search query or type filters.
                  </p>
                </div>
              ) : (
                filteredOrgPrograms.map((program) => {
                  const isOrgOwned = program.is_org_owned !== false
                  const programCohorts = cohortsByProgramId.get(program.id) ?? []
                  const runningCohorts = programCohorts.filter((c) => c.status === "running")
                  const openCohorts = programCohorts.filter(
                    (c) => c.status === "registration_open" || c.status === "planned"
                  )
                  const pastCohorts = programCohorts.filter(
                    (c) => c.status === "completed" || c.status === "cancelled"
                  )
                  const pastExpanded = !!expandedPastMap[program.id]

                  return (
                    <div
                      key={program.id}
                      className="rounded-[10px] border border-border bg-card overflow-hidden transition-colors"
                    >
                      {/* Clean Program Header with Interactive Arrow */}
                      <div className="p-5 sm:p-6 border-b border-border bg-muted/20 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2.5 flex-wrap">
                            <Link
                              to="/operations/programs/$programId"
                              params={{ programId: program.id }}
                              className="text-xl font-extrabold text-foreground tracking-tight hover:text-primary transition-colors"
                            >
                              {program.name}
                            </Link>
                            <span className="text-xs font-bold px-2.5 py-0.5 rounded-[10px] bg-primary/10 text-primary border border-primary/20 capitalize">
                              {program.program_type}
                            </span>
                            {!isOrgOwned && (
                              <span className="text-xs font-bold px-2.5 py-0.5 rounded-[10px] bg-amber-500/15 text-amber-700 dark:text-amber-300 border border-amber-500/30">
                                Shared by SpacePoint
                              </span>
                            )}
                          </div>

                          {program.description && (
                            <p className="text-sm text-muted-foreground mt-1 line-clamp-1">
                              {program.description}
                            </p>
                          )}
                        </div>

                        {/* Master Action & Navigatable Arrow */}
                        <div className="flex items-center gap-2 shrink-0">
                          <button
                            type="button"
                            onClick={() => openLaunchCohort(program.id, isOrgOwned)}
                            className="inline-flex items-center gap-1.5 h-10 px-4 rounded-[10px] bg-primary text-primary-foreground text-sm font-bold hover:opacity-90 transition-colors cursor-pointer"
                          >
                            <Plus size={15} /> Add Cohort
                          </button>

                          <Link
                            to="/operations/programs/$programId"
                            params={{ programId: program.id }}
                            className="inline-flex items-center justify-center h-10 w-10 rounded-[10px] border border-border bg-background text-foreground hover:bg-muted hover:border-primary/40 transition-colors group cursor-pointer"
                            title="Manage Program"
                            aria-label={`Manage ${program.name}`}
                          >
                            <ChevronRight
                              size={18}
                              className="group-hover:translate-x-0.5 transition-transform"
                            />
                          </Link>
                        </div>
                      </div>

                      {/* Child Cohorts Groups */}
                      <div className="p-5 sm:p-6 space-y-6">
                        {programCohorts.length === 0 ? (
                          <div className="py-8 text-center rounded-[10px] border border-dashed border-border bg-muted/10">
                            <p className="text-sm font-semibold text-muted-foreground">
                              No cohorts scheduled under this program yet.
                            </p>
                            <button
                              type="button"
                              onClick={() => openLaunchCohort(program.id, isOrgOwned)}
                              className="mt-3 inline-flex items-center gap-1.5 h-8 px-3 rounded-[10px] bg-primary text-primary-foreground text-xs font-bold hover:opacity-90 transition-colors cursor-pointer"
                            >
                              <Plus size={13} /> Launch First Cohort
                            </button>
                          </div>
                        ) : (
                          <>
                            {/* 1. Running Cohorts */}
                            {runningCohorts.length > 0 && (
                              <div>
                                <div className="flex items-center gap-2 mb-3">
                                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 inline-block" />
                                  <h3 className="text-xs font-extrabold uppercase tracking-wider text-muted-foreground">
                                    Running Now ({runningCohorts.length})
                                  </h3>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                                  {runningCohorts.map((c) => (
                                    <OpsOrgCohortCard
                                      key={c.id}
                                      cohort={c}
                                      orgId={orgId}
                                      onAssignCoordinators={() => setCoordCohortTarget(c)}
                                    />
                                  ))}
                                </div>
                              </div>
                            )}

                            {/* 2. Registration Open & Upcoming Cohorts */}
                            {openCohorts.length > 0 && (
                              <div>
                                <div className="flex items-center gap-2 mb-3">
                                  <span className="w-2.5 h-2.5 rounded-full bg-primary inline-block" />
                                  <h3 className="text-xs font-extrabold uppercase tracking-wider text-muted-foreground">
                                    Registration Open &amp; Upcoming ({openCohorts.length})
                                  </h3>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                                  {openCohorts.map((c) => (
                                    <OpsOrgCohortCard
                                      key={c.id}
                                      cohort={c}
                                      orgId={orgId}
                                      onAssignCoordinators={() => setCoordCohortTarget(c)}
                                    />
                                  ))}
                                </div>
                              </div>
                            )}

                            {/* 3. Past & Completed Cohorts */}
                            {pastCohorts.length > 0 && (
                              <div className="pt-2 border-t border-border">
                                <button
                                  type="button"
                                  onClick={() => togglePast(program.id)}
                                  className="inline-flex items-center gap-2 text-xs font-extrabold uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                                >
                                  <span className="w-2.5 h-2.5 rounded-full bg-muted-foreground/60 inline-block" />
                                  <span>Past &amp; Completed ({pastCohorts.length} Cohorts)</span>
                                  {pastExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                                </button>

                                {pastExpanded && (
                                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 mt-3">
                                    {pastCohorts.map((c) => (
                                      <OpsOrgCohortCard
                                        key={c.id}
                                        cohort={c}
                                        orgId={orgId}
                                        onAssignCoordinators={() => setCoordCohortTarget(c)}
                                      />
                                    ))}
                                  </div>
                                )}
                              </div>
                            )}
                          </>
                        )}
                      </div>
                    </div>
                  )
                })
              )}
            </div>
          )}

          {/* ── VIEW 2: GLOBAL OPERATIONAL WORKLIST (COHORT VIEW) ──────── */}
          {programViewMode === "worklist" && (
            <div className="rounded-[10px] border border-border bg-card overflow-hidden">
              <div className="hidden md:grid md:grid-cols-12 gap-3 p-4 border-b border-border bg-muted/20 text-xs font-bold uppercase tracking-wider text-muted-foreground">
                <div className="col-span-2">Status</div>
                <div className="col-span-3">Cohort &amp; Program</div>
                <div className="col-span-3">Dates &amp; Venue</div>
                <div className="col-span-2">Staffing &amp; Capacity</div>
                <div className="col-span-2 text-right">Actions</div>
              </div>

              <div className="divide-y divide-border">
                {filteredOrgWorklist.length === 0 ? (
                  <div className="p-12 text-center text-sm font-semibold text-muted-foreground">
                    No cohorts match the selected filters.
                  </div>
                ) : (
                  filteredOrgWorklist.map((c) => (
                    <div
                      key={c.id}
                      className="flex flex-col md:grid md:grid-cols-12 gap-3 p-4 md:items-center hover:bg-muted/30 transition-colors"
                    >
                      <div className="md:col-span-2 flex items-center gap-1.5 flex-wrap">
                        <OpsCohortStatusBadge status={c.status} />
                      </div>

                      <div className="md:col-span-3 min-w-0">
                        <Link
                          to="/operations/cohorts/$cohortId"
                          params={{ cohortId: c.id }}
                          search={{ from: `/operations/organizations/${orgId}` } as never}
                          className="text-sm font-bold text-foreground hover:text-primary transition-colors block md:truncate"
                        >
                          {c.name}
                        </Link>
                        <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                          <span className="text-xs text-muted-foreground md:truncate">
                            {c.program_name ?? "—"}
                          </span>
                          <span
                            className={cn(
                              "rounded-full px-2 py-0.5 text-[10px] font-semibold border",
                              c.management_mode === "spacepoint"
                                ? "border-violet-500/30 bg-violet-500/15 text-violet-700 dark:text-violet-300"
                                : "border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                            )}
                          >
                            {c.management_mode === "spacepoint" ? "Delivered by SpacePoint" : "Partner-run"}
                          </span>
                        </div>
                      </div>

                      <div className="md:col-span-3 text-xs text-muted-foreground min-w-0">
                        <div className="md:truncate">
                          {c.starts_on
                            ? `${c.starts_on}${c.ends_on && c.ends_on !== c.starts_on ? ` – ${c.ends_on}` : ""}`
                            : "Dates unassigned"}
                        </div>
                        <div className="md:truncate text-foreground font-medium mt-0.5">
                          {c.location_name || "Venue unassigned"}
                        </div>
                      </div>

                      <div className="md:col-span-2 flex md:block items-center justify-between gap-2 text-xs text-muted-foreground">
                        <div className="font-bold text-foreground">
                          {c.enrolled_count}
                          {c.capacity ? ` / ${c.capacity}` : ""} Seats
                        </div>
                        <div className="md:truncate md:mt-0.5">
                          {c.sessions_count != null ? `${c.sessions_count} sessions` : ""}
                        </div>
                      </div>

                      <div className="md:col-span-2 flex items-center justify-end gap-1.5 pt-2 md:pt-0 border-t border-border/50 md:border-t-0">
                        <button
                          type="button"
                          onClick={() => setCoordCohortTarget(c)}
                          className="inline-flex items-center gap-1 h-8 px-2.5 rounded-[10px] border border-border bg-background text-xs font-semibold text-foreground hover:bg-muted transition-colors cursor-pointer"
                          title="Assign coordinators"
                        >
                          <Users size={12} />
                          {c.coordinator_access_mode === "assigned"
                            ? `Assigned (${c.coordinators?.length ?? 0})`
                            : "Coordinators"}
                        </button>
                        <Link
                          to="/operations/cohorts/$cohortId"
                          params={{ cohortId: c.id }}
                          search={{ from: `/operations/organizations/${orgId}` } as never}
                          className="inline-flex items-center gap-1 h-8 px-3 rounded-[10px] border border-border bg-background text-xs font-bold text-foreground hover:bg-muted transition-colors"
                        >
                          Manage <ArrowRight size={12} />
                        </Link>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
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
                            search={{ from: `/operations/organizations/${org.id}` } as never}
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
                  {detail.team.map((m) => {
                    const isPrimaryOwner = Boolean(m.is_owner ?? m.role === "Owner")
                    return (
                      <tr key={m.user_id} className="hover:bg-muted/40">
                        <td className="py-3.5 pr-4 font-bold text-foreground">{m.full_name}</td>
                        <td className="py-3.5 pr-4">
                          <OrgRoleToggleRow
                            isOwner={isPrimaryOwner}
                            roles={memberOrgRoles({ ...m, is_owner: isPrimaryOwner })}
                            compact
                            disabled={memberRoleMut.isPending}
                            onChange={(orgRoles) =>
                              memberRoleMut.mutate({ userId: m.user_id, orgRoles })
                            }
                          />
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
                            {!isPrimaryOwner && (
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
                    )
                  })}
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

      {createProgramOpen && (
        <OpsCreateOrgProgramModal
          orgId={orgId}
          orgName={org.name_latin}
          onClose={() => setCreateProgramOpen(false)}
          onSuccess={() => {
            setCreateProgramOpen(false)
            invalidateOrgQueries()
          }}
        />
      )}

      {createCohortOpen && (
        <OpsCreateOrgCohortModal
          orgId={orgId}
          orgName={org.name_latin}
          orgPrograms={detail.programs}
          sharedPrograms={detail.shared_programs ?? []}
          defaultProgramId={cohortDefaultProgramId}
          defaultMode={cohortDefaultMode}
          onClose={() => setCreateCohortOpen(false)}
          onSuccess={() => {
            setCreateCohortOpen(false)
            invalidateOrgQueries()
          }}
        />
      )}

      {coordCohortTarget && (
        <OpsCohortCoordinatorsModal
          orgId={orgId}
          cohort={coordCohortTarget}
          onClose={() => setCoordCohortTarget(null)}
          onSuccess={() => {
            setCoordCohortTarget(null)
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
  const [orgRoles, setOrgRoles] = useState<Exclude<OrgSandboxRole, "owner">[]>(["coordinator"])

  const mut = useMutation({
    mutationFn: () =>
      createOrganizationMember(orgId, {
        full_name: fullName.trim(),
        email: email.trim(),
        phone: phone.trim() || null,
        org_role: orgRoles[0],
        org_roles: orgRoles,
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
          <div className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold text-muted-foreground">Organization Roles</span>
            <OrgRolePickerGrid value={orgRoles} onChange={setOrgRoles} />
          </div>
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

function OpsCreateOrgProgramModal({
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
  const [name, setName] = useState("")
  const [code, setCode] = useState("")
  const [programType, setProgramType] = useState("competition")
  const [defaultCapacity, setDefaultCapacity] = useState("30")
  const [durationHours, setDurationHours] = useState("2")
  const [description, setDescription] = useState("")
  const [keepAccess, setKeepAccess] = useState(true)

  const mut = useMutation({
    mutationFn: () =>
      createOrgProgramApi(
        {
          name: name.trim(),
          code: code.trim().toUpperCase() || undefined,
          program_type: programType,
          default_capacity: defaultCapacity.trim() ? Number(defaultCapacity) : undefined,
          duration_hours: durationHours.trim() ? Number(durationHours) : undefined,
          keep_course_access_after_completion: keepAccess,
          description: description.trim() || undefined,
        },
        orgId,
      ),
    onSuccess: (created) => {
      toast.success(`Program "${created.name}" created for ${orgName}`)
      onSuccess()
    },
    onError: (err) => toast.error(getErrorMessage(err, "Could not create organization program")),
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="w-full max-w-lg space-y-4 rounded-[12px] border border-border bg-card p-6 shadow-xl">
        <div>
          <h2 className="text-base font-bold text-foreground">New Program for {orgName}</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Creates an organization-owned program and its companion LMS curriculum checklist.
          </p>
        </div>

        <div className="space-y-3">
          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-muted-foreground">Program Name *</span>
            <input
              type="text"
              value={name}
              onChange={(e) => {
                setName(e.target.value)
                if (!code) {
                  setCode(
                    e.target.value
                      .replace(/[^a-zA-Z0-9]/g, "")
                      .slice(0, 8)
                      .toUpperCase(),
                  )
                }
              }}
              placeholder="e.g. UAE CubeSat Challenge"
              className="h-9 rounded-[10px] border border-border bg-background px-3 text-sm focus:border-primary focus:outline-none"
            />
          </label>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">Code (optional)</span>
              <input
                type="text"
                value={code}
                onChange={(e) => setCode(e.target.value.toUpperCase())}
                placeholder="Auto-generated if blank"
                className="h-9 rounded-[10px] border border-border bg-background px-3 font-mono text-sm focus:border-primary focus:outline-none"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">Type</span>
              <select
                value={programType}
                onChange={(e) => setProgramType(e.target.value)}
                className="h-9 rounded-[10px] border border-border bg-background px-3 text-sm focus:border-primary focus:outline-none"
              >
                <option value="competition">Competition</option>
                <option value="course">Course</option>
                <option value="workshop">Workshop</option>
                <option value="info_session">Info Session</option>
              </select>
            </label>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">Default Capacity</span>
              <input
                type="number"
                min={1}
                value={defaultCapacity}
                onChange={(e) => setDefaultCapacity(e.target.value)}
                className="h-9 rounded-[10px] border border-border bg-background px-3 text-sm focus:border-primary focus:outline-none"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">Session Duration (hrs)</span>
              <input
                type="number"
                step="0.5"
                min="0.5"
                value={durationHours}
                onChange={(e) => setDurationHours(e.target.value)}
                className="h-9 rounded-[10px] border border-border bg-background px-3 text-sm focus:border-primary focus:outline-none"
              />
            </label>
          </div>

          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-muted-foreground">Description</span>
            <textarea
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="rounded-[10px] border border-border bg-background p-3 text-sm focus:border-primary focus:outline-none resize-none"
            />
          </label>

          <label className="flex items-center gap-2 text-xs font-medium text-foreground cursor-pointer">
            <input
              type="checkbox"
              checked={keepAccess}
              onChange={(e) => setKeepAccess(e.target.checked)}
              className="rounded border-border"
            />
            Keep course access after program completion
          </label>
        </div>

        <div className="flex items-center justify-end gap-2 pt-2">
          <Button type="button" variant="outline" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="button"
            size="sm"
            disabled={!name.trim() || mut.isPending}
            onClick={() => mut.mutate()}
          >
            {mut.isPending ? "Creating…" : "Create Program"}
          </Button>
        </div>
      </div>
    </div>
  )
}

function OpsCreateOrgCohortModal({
  orgId,
  orgName,
  orgPrograms,
  sharedPrograms,
  defaultProgramId,
  defaultMode,
  onClose,
  onSuccess,
}: {
  orgId: string
  orgName: string
  orgPrograms: OrgProgramDetail[]
  sharedPrograms: OrgSharedProgram[]
  defaultProgramId: string
  defaultMode?: "spacepoint" | "partner"
  onClose: () => void
  onSuccess: () => void
}) {
  const qc = useQueryClient()
  const toast = useToast()

  const { data: platformPrograms = [] } = useQuery<Program[]>({
    queryKey: ["admin-programs-catalog"],
    queryFn: () => getFilteredProgramsApi({ include_org_programs: false }),
  })

  const { data: locations = [] } = useQuery<Location[]>({
    queryKey: ["locations"],
    queryFn: () => getLocationsApi(),
  })

  const ownPrograms = useMemo(
    () => orgPrograms.filter((p) => p.is_org_owned !== false),
    [orgPrograms],
  )
  const spPrograms = useMemo(
    () => platformPrograms.filter((p) => !p.organization_id),
    [platformPrograms],
  )

  const initialProgId =
    defaultProgramId ||
    ownPrograms[0]?.id ||
    sharedPrograms[0]?.id ||
    spPrograms[0]?.id ||
    ""

  const [programId, setProgramId] = useState(initialProgId)
  const [managementMode, setManagementMode] = useState<"spacepoint" | "partner">(() => {
    if (defaultMode) return defaultMode
    return ownPrograms.some((p) => p.id === initialProgId) ? "partner" : "spacepoint"
  })
  const [variationId, setVariationId] = useState("")
  const [name, setName] = useState("")
  const [startsOn, setStartsOn] = useState("")
  const [endsOn, setEndsOn] = useState("")
  const [locationId, setLocationId] = useState("")
  const [warehouseId, setWarehouseId] = useState("")
  const [capacity, setCapacity] = useState("")
  const [durationHours, setDurationHours] = useState("")
  const [visibility, setVisibility] = useState<"public" | "private">("private")
  const [coordinatorAccessMode, setCoordinatorAccessMode] = useState<"general" | "assigned">("general")
  const [coordinatorUserIds, setCoordinatorUserIds] = useState<string[]>([])
  const [createLocOpen, setCreateLocOpen] = useState(false)

  const effectiveProgramId = programId || ownPrograms[0]?.id || spPrograms[0]?.id || ""

  const { data: variations = [] } = useQuery<ProgramVariation[]>({
    queryKey: ["program-variations-ops-modal", effectiveProgramId],
    queryFn: () => listProgramVariationsApi(effectiveProgramId, true),
    enabled: Boolean(effectiveProgramId),
  })

  const { data: warehouses = [] } = useQuery({
    queryKey: ["inv-warehouses"],
    queryFn: () => getWarehousesApi(),
    enabled: managementMode === "spacepoint",
  })

  const selectedVariationId =
    variationId && variations.some((v) => v.id === variationId)
      ? variationId
      : variations.find((v) => v.is_default)?.id ?? variations[0]?.id ?? ""

  const mut = useMutation({
    mutationFn: () =>
      createCohortApi({
        program_id: effectiveProgramId,
        variation_id: selectedVariationId || null,
        name: name.trim(),
        starts_on: startsOn || undefined,
        ends_on: endsOn || undefined,
        location_id: locationId || undefined,
        warehouse_id: managementMode === "spacepoint" && warehouseId ? warehouseId : undefined,
        capacity: capacity.trim() ? Number(capacity) : undefined,
        duration_hours: durationHours.trim() ? Number(durationHours) : undefined,
        visibility,
        organization_id: orgId,
        management_mode: managementMode,
        coordinator_access_mode: coordinatorAccessMode,
        coordinator_user_ids: coordinatorAccessMode === "assigned" ? coordinatorUserIds : [],
      }),
    onSuccess: (created) => {
      toast.success(`Cohort "${created.name}" created for ${orgName}`)
      onSuccess()
    },
    onError: (err) => toast.error(getErrorMessage(err, "Could not create cohort")),
  })

  return (
    <>
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
        <div className="w-full max-w-xl max-h-[90vh] overflow-y-auto space-y-4 rounded-[12px] border border-border bg-card p-6 shadow-xl">
          <div>
            <h2 className="text-base font-bold text-foreground">Launch Cohort for {orgName}</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Choose whether SpacePoint delivers with SpacePoint instructors or the partner handles delivery.
            </p>
          </div>

          <div className="space-y-3.5">
            <div>
              <span className="text-xs font-semibold text-muted-foreground block mb-1.5">
                Delivery Mode
              </span>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setManagementMode("spacepoint")}
                  className={cn(
                    "p-3 rounded-[10px] border text-left transition cursor-pointer",
                    managementMode === "spacepoint"
                      ? "border-primary bg-primary/10"
                      : "border-border bg-background hover:bg-muted/40",
                  )}
                >
                  <div className="flex items-center gap-1.5 text-xs font-bold text-foreground">
                    <Layers className="h-3.5 w-3.5 text-primary" />
                    Delivered by SpacePoint
                  </div>
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    SpacePoint staffs instructors, warehouses, and payouts. Partner tracks progress &amp; students.
                  </p>
                </button>

                <button
                  type="button"
                  onClick={() => setManagementMode("partner")}
                  className={cn(
                    "p-3 rounded-[10px] border text-left transition cursor-pointer",
                    managementMode === "partner"
                      ? "border-primary bg-primary/10"
                      : "border-border bg-background hover:bg-muted/40",
                  )}
                >
                  <div className="flex items-center gap-1.5 text-xs font-bold text-foreground">
                    <Users className="h-3.5 w-3.5 text-primary" />
                    Partner-run
                  </div>
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    Partner staffs their own team and handles delivery.
                  </p>
                </button>
              </div>
            </div>

            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">Program *</span>
              <select
                value={effectiveProgramId}
                onChange={(e) => {
                  const nextId = e.target.value
                  setProgramId(nextId)
                  setVariationId("")
                  setManagementMode(ownPrograms.some((p) => p.id === nextId) ? "partner" : "spacepoint")
                }}
                className="h-9 rounded-[10px] border border-border bg-background px-3 text-sm focus:border-primary focus:outline-none"
              >
                {ownPrograms.length > 0 && (
                  <optgroup label={`${orgName} Programs`}>
                    {ownPrograms.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name} ({p.code || p.program_type})
                      </option>
                    ))}
                  </optgroup>
                )}
                {spPrograms.length > 0 && (
                  <optgroup label="SpacePoint Programs">
                    {spPrograms.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name} ({p.code})
                      </option>
                    ))}
                  </optgroup>
                )}
              </select>
            </label>

            {variations.length > 0 && (
              <label className="flex flex-col gap-1">
                <span className="text-xs font-semibold text-muted-foreground">Program Variation</span>
                <select
                  value={selectedVariationId}
                  onChange={(e) => setVariationId(e.target.value)}
                  className="h-9 rounded-[10px] border border-border bg-background px-3 text-sm focus:border-primary focus:outline-none"
                >
                  {variations.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.name}
                      {v.is_default ? " (Default)" : ""}
                    </option>
                  ))}
                </select>
              </label>
            )}

            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">Cohort Name *</span>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Spring 2026 — Cohort 1"
                className="h-9 rounded-[10px] border border-border bg-background px-3 text-sm focus:border-primary focus:outline-none"
              />
            </label>

            <div className="grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1">
                <span className="text-xs font-semibold text-muted-foreground">Start Date</span>
                <input
                  type="date"
                  value={startsOn}
                  onChange={(e) => setStartsOn(e.target.value)}
                  className="h-9 rounded-[10px] border border-border bg-background px-3 text-sm focus:border-primary focus:outline-none"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs font-semibold text-muted-foreground">End Date</span>
                <input
                  type="date"
                  value={endsOn}
                  min={startsOn || undefined}
                  onChange={(e) => setEndsOn(e.target.value)}
                  className="h-9 rounded-[10px] border border-border bg-background px-3 text-sm focus:border-primary focus:outline-none"
                />
              </label>
            </div>

            <div className="flex flex-col gap-1">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-semibold text-muted-foreground flex items-center gap-1">
                  <MapPin className="h-3.5 w-3.5" /> Venue / Location
                </span>
                <button
                  type="button"
                  onClick={() => setCreateLocOpen(true)}
                  className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline cursor-pointer"
                >
                  <Plus className="h-3 w-3" /> New Location
                </button>
              </div>
              <select
                value={locationId}
                onChange={(e) => setLocationId(e.target.value)}
                className="h-9 rounded-[10px] border border-border bg-background px-3 text-sm focus:border-primary focus:outline-none"
              >
                <option value="">Select venue (optional)</option>
                {locations.map((loc) => (
                  <option key={loc.id} value={loc.id}>
                    {loc.name}
                    {loc.city_name ? ` — ${loc.city_name}` : ""}
                  </option>
                ))}
              </select>
            </div>

            {managementMode === "spacepoint" && (
              <label className="flex flex-col gap-1">
                <span className="text-xs font-semibold text-muted-foreground flex items-center gap-1">
                  <WarehouseIcon className="h-3.5 w-3.5" /> Warehouse (optional)
                </span>
                <select
                  value={warehouseId}
                  onChange={(e) => setWarehouseId(e.target.value)}
                  className="h-9 rounded-[10px] border border-border bg-background px-3 text-sm focus:border-primary focus:outline-none"
                >
                  <option value="">Select SpacePoint warehouse (optional)</option>
                  {warehouses.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.name}
                    </option>
                  ))}
                </select>
              </label>
            )}

            <div className="grid grid-cols-3 gap-3">
              <label className="flex flex-col gap-1">
                <span className="text-xs font-semibold text-muted-foreground">Capacity</span>
                <input
                  type="number"
                  min={1}
                  value={capacity}
                  onChange={(e) => setCapacity(e.target.value)}
                  placeholder="Inherit"
                  className="h-9 rounded-[10px] border border-border bg-background px-3 text-sm focus:border-primary focus:outline-none"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs font-semibold text-muted-foreground">Duration (hrs)</span>
                <input
                  type="number"
                  step="0.5"
                  min="0.5"
                  value={durationHours}
                  onChange={(e) => setDurationHours(e.target.value)}
                  placeholder="Inherit"
                  className="h-9 rounded-[10px] border border-border bg-background px-3 text-sm focus:border-primary focus:outline-none"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs font-semibold text-muted-foreground">Visibility</span>
                <select
                  value={visibility}
                  onChange={(e) => setVisibility(e.target.value as "public" | "private")}
                  className="h-9 rounded-[10px] border border-border bg-background px-3 text-sm focus:border-primary focus:outline-none"
                >
                  <option value="public">Public</option>
                  <option value="private">Private</option>
                </select>
              </label>
            </div>

            <CoordinatorAccessPicker
              organizationId={orgId}
              mode={coordinatorAccessMode}
              onModeChange={setCoordinatorAccessMode}
              selectedUserIds={coordinatorUserIds}
              onSelectedUserIdsChange={setCoordinatorUserIds}
            />
          </div>

          <div className="flex items-center justify-end gap-2 pt-2 border-t border-border">
            <Button type="button" variant="outline" size="sm" onClick={onClose}>
              Cancel
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={!effectiveProgramId || !name.trim() || mut.isPending}
              onClick={() => mut.mutate()}
            >
              {mut.isPending ? "Launching…" : "Launch Cohort"}
            </Button>
          </div>
        </div>
      </div>

      {createLocOpen && (
        <QuickCreateLocationModal
          onClose={() => setCreateLocOpen(false)}
          onCreated={(loc) => {
            setLocationId(loc.id)
            void qc.invalidateQueries({ queryKey: ["locations"] })
          }}
        />
      )}
    </>
  )
}

function OpsOrgCohortCard({
  cohort: c,
  orgId,
  onAssignCoordinators,
}: {
  cohort: OrgCohortDetail
  orgId: string
  onAssignCoordinators: () => void
}) {
  const registered = c.enrolled_count ?? 0
  const fillPct = c.capacity ? Math.min(100, Math.round((registered / c.capacity) * 100)) : null

  return (
    <div className="rounded-[var(--sp-control-radius)] border-[length:var(--sp-control-border-width)] border-[var(--sp-control-border-color)] bg-transparent p-4 flex flex-col justify-between gap-3 hover:border-primary/60 transition-colors">
      <div>
        <div className="flex items-start justify-between gap-2 mb-2">
          <Link
            to="/operations/cohorts/$cohortId"
            params={{ cohortId: c.id }}
            search={{ from: `/operations/organizations/${orgId}` } as never}
            className="text-sm font-bold text-foreground hover:text-primary transition-colors truncate block"
          >
            {c.name}
          </Link>
          <div className="flex items-center gap-1 shrink-0">
            <OpsCohortStatusBadge status={c.status} />
          </div>
        </div>

        <div className="mb-2.5 flex items-center gap-1.5 flex-wrap">
          <span
            className={cn(
              "text-[11px] font-bold px-2 py-0.5 rounded-full border",
              c.management_mode === "spacepoint"
                ? "bg-violet-500/15 text-violet-600 dark:text-violet-400 border-violet-500/30"
                : "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/20"
            )}
          >
            {c.management_mode === "spacepoint" ? "Delivered by SpacePoint" : "Partner-run"}
          </span>
          {c.coordinator_access_mode === "assigned" ? (
            <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full border border-indigo-500/25 bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">
              Assigned ({c.coordinators?.length ?? 0})
            </span>
          ) : (
            <span className="text-[11px] font-medium px-2 py-0.5 rounded-full border border-border bg-muted/40 text-muted-foreground">
              All coordinators
            </span>
          )}
        </div>

        <div className="space-y-1.5 text-xs text-muted-foreground mt-2">
          <div className="flex items-center gap-1.5 truncate">
            <Calendar size={13} className="shrink-0 text-muted-foreground" />
            <span className="truncate">
              {c.starts_on
                ? `${c.starts_on}${c.ends_on && c.ends_on !== c.starts_on ? ` – ${c.ends_on}` : ""}`
                : "Dates unassigned"}
            </span>
          </div>

          <div className="flex items-center gap-1.5 truncate">
            <MapPin size={13} className="shrink-0 text-muted-foreground" />
            <span className="truncate">{c.location_name || "Venue unassigned"}</span>
          </div>

          <div className="flex items-center gap-1.5 truncate">
            <Users size={13} className="shrink-0 text-muted-foreground" />
            <span className="truncate">
              {registered}
              {c.capacity != null ? ` / ${c.capacity}` : ""} Registered
            </span>
          </div>
        </div>

        {fillPct != null && (
          <div className="mt-2.5">
            <div className="h-1.5 w-full rounded-[10px] bg-muted overflow-hidden">
              <div
                className={`h-full rounded-[10px] ${fillPct >= 100 ? "bg-rose-500" : "bg-primary"
                  }`}
                style={{ width: `${fillPct}%` }}
              />
            </div>
          </div>
        )}
      </div>

      <div className="pt-3 border-t border-border flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={onAssignCoordinators}
          className="inline-flex items-center gap-1 text-xs font-semibold text-muted-foreground hover:text-foreground cursor-pointer"
        >
          <Users size={12} /> Coordinators
        </button>
        <Link
          to="/operations/cohorts/$cohortId"
          params={{ cohortId: c.id }}
          search={{ from: `/operations/organizations/${orgId}` } as never}
          className="text-xs font-bold text-primary hover:underline inline-flex items-center gap-1"
        >
          Manage <ArrowRight size={12} />
        </Link>
      </div>
    </div>
  )
}

function OpsCohortCoordinatorsModal({
  orgId,
  cohort,
  onClose,
  onSuccess,
}: {
  orgId: string
  cohort: OrgCohortDetail
  onClose: () => void
  onSuccess: () => void
}) {
  const toast = useToast()
  const [mode, setMode] = useState<"general" | "assigned">(cohort.coordinator_access_mode ?? "general")
  const [userIds, setUserIds] = useState<string[]>((cohort.coordinators ?? []).map((c) => c.id))

  const mut = useMutation({
    mutationFn: () =>
      updateCohortApi(cohort.id, {
        coordinator_access_mode: mode,
        coordinator_user_ids: mode === "assigned" ? userIds : [],
      }),
    onSuccess: () => {
      toast.success(`Updated coordinator access for "${cohort.name}"`)
      onSuccess()
    },
    onError: (err) => toast.error(getErrorMessage(err, "Failed to update coordinators")),
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="w-full max-w-lg space-y-4 rounded-[12px] border border-border bg-card p-6 shadow-xl">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-bold text-foreground">Assign Coordinators</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">{cohort.name}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted cursor-pointer"
          >
            <X size={16} />
          </button>
        </div>

        <CoordinatorAccessPicker
          organizationId={orgId}
          mode={mode}
          onModeChange={setMode}
          selectedUserIds={userIds}
          onSelectedUserIdsChange={setUserIds}
        />

        <div className="flex items-center justify-end gap-2 pt-2 border-t border-border">
          <Button type="button" variant="outline" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="button"
            size="sm"
            disabled={mut.isPending}
            onClick={() => mut.mutate()}
          >
            {mut.isPending ? "Saving..." : "Save Coordinators"}
          </Button>
        </div>
      </div>
    </div>
  )
}

function OpsCohortStatusBadge({ status }: { status?: string | null }) {
  const s = (status || "planned").toLowerCase()
  if (s === "running") {
    return (
      <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30">
        Running
      </span>
    )
  }
  if (s === "registration_open") {
    return (
      <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">
        Registration Open
      </span>
    )
  }
  if (s === "planned") {
    return (
      <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-muted text-muted-foreground border border-border">
        Planned
      </span>
    )
  }
  if (s === "completed") {
    return (
      <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-foreground text-background border border-foreground">
        Completed
      </span>
    )
  }
  return (
    <span className="text-[11px] font-bold px-2 py-0.5 rounded-[10px] bg-rose-500/15 text-rose-600 dark:text-rose-400 border border-rose-500/30">
      Cancelled
    </span>
  )
}

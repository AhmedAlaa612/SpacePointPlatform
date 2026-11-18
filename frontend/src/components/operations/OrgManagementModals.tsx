import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Check, Copy, KeyRound, Save, Trash2 } from "lucide-react"
import {
  createAdminOrganizationAccount,
  deleteAdminOrganizationAccount,
  getAdminOrganizationResetLink,
  updateAdminOrganizationAccount,
  type OrganizationAccountSummary,
} from "@/api/websiteEvents"
import {
  OrgGrantsAndQuotasForm,
  type OrgGrantsAndQuotasData,
} from "@/components/organization/OrgGrantsAndQuotasForm"
import { CountrySelect } from "@/components/ui/CountrySelect"
import { CityNameSelect } from "@/components/ui/CitySelect"
import { Button } from "@/components/ui/button"
import { useToast } from "@/components/ui/toast"
import { Modal } from "@/pages/admin/components/common"
import { getErrorMessage } from "@/lib/utils"

export const WEBSITE_BASE_URL =
  (import.meta.env.VITE_WEBSITE_URL as string | undefined)?.replace(/\/$/, "") ||
  (typeof window !== "undefined" &&
  window.location.hostname !== "localhost" &&
  window.location.hostname !== "127.0.0.1"
    ? "https://spacepoint.ae"
    : "http://localhost:4321")

export const ORG_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: "university", label: "University" },
  { value: "school", label: "School" },
  { value: "company", label: "Company" },
  { value: "government", label: "Government Entity" },
  { value: "ngo", label: "NGO / Club" },
  { value: "other", label: "Other" },
]

export function formatOrgType(orgType?: string | null): string {
  const found = ORG_TYPE_OPTIONS.find((opt) => opt.value === orgType)
  return found ? found.label : orgType || "Organization"
}

export function quotaPct(used: number, limit?: number | null): number {
  if (limit == null || limit <= 0) return 0
  return Math.min(100, Math.round((used / limit) * 100))
}

export function buildOrgApprovePayload(org: OrganizationAccountSummary, nextApproved: boolean) {
  return {
    org_name_latin: org.name_latin,
    org_name_arabic: org.name_arabic ?? "",
    org_type: org.org_type || "university",
    country: org.country || "uae",
    city: org.city ?? "",
    full_name: org.owner_name ?? "",
    email: org.owner_email ?? undefined,
    phone: org.owner_phone ?? "",
    is_approved: nextApproved,
    can_publish_events: org.can_publish_events,
    can_author_courses: org.can_author_courses,
    can_publish_courses: org.can_publish_courses,
    course_scope_all: org.course_scope_all,
    allowed_course_ids: org.allowed_course_ids ?? [],
    quiz_scope: (org.quiz_scope as "all" | "selected" | "own" | undefined) ?? "own",
    allowed_quiz_template_ids: org.allowed_quiz_template_ids ?? [],
    readiness_scope: (org.readiness_scope as "all" | "selected" | "own" | undefined) ?? "own",
    allowed_readiness_preset_ids: org.allowed_readiness_preset_ids ?? [],
    max_events: org.max_events ?? null,
    max_programs: org.max_programs ?? null,
    max_cohorts: org.max_cohorts ?? null,
    max_students_per_cohort: org.max_students_per_cohort ?? null,
    max_observers_per_cohort: org.max_observers_per_cohort ?? null,
  }
}

interface OrgFormState extends OrgGrantsAndQuotasData {
  org_name_latin: string
  org_name_arabic: string
  org_type: string
  country: string
  city: string
  full_name: string
  email: string
  phone: string
  password: string
}

function initialFormState(org: OrganizationAccountSummary | null): OrgFormState {
  if (!org) {
    return {
      org_name_latin: "",
      org_name_arabic: "",
      org_type: "university",
      country: "uae",
      city: "Abu Dhabi",
      full_name: "",
      email: "",
      phone: "",
      password: "",
      is_approved: true,
      can_publish_events: false,
      can_author_courses: false,
      can_publish_courses: false,
      course_scope_all: false,
      allowed_course_ids: [],
      quiz_scope: "own",
      allowed_quiz_template_ids: [],
      readiness_scope: "own",
      allowed_readiness_preset_ids: [],
      max_events: null,
      max_programs: null,
      max_cohorts: null,
      max_students_per_cohort: null,
      max_observers_per_cohort: null,
    }
  }
  return {
    org_name_latin: org.name_latin || "",
    org_name_arabic: org.name_arabic || "",
    org_type: org.org_type || "university",
    country: org.country || "uae",
    city: org.city || "",
    full_name: org.owner_name || "",
    email: org.owner_email || "",
    phone: org.owner_phone || "",
    password: "",
    is_approved: org.is_approved ?? true,
    can_publish_events: org.can_publish_events ?? false,
    can_author_courses: org.can_author_courses ?? false,
    can_publish_courses: org.can_publish_courses ?? false,
    course_scope_all: org.course_scope_all ?? false,
    allowed_course_ids: org.allowed_course_ids ?? [],
    quiz_scope: (org.quiz_scope as "all" | "selected" | "own" | undefined) ?? "own",
    allowed_quiz_template_ids: org.allowed_quiz_template_ids ?? [],
    readiness_scope: (org.readiness_scope as "all" | "selected" | "own" | undefined) ?? "own",
    allowed_readiness_preset_ids: org.allowed_readiness_preset_ids ?? [],
    max_events: org.max_events ?? null,
    max_programs: org.max_programs ?? null,
    max_cohorts: org.max_cohorts ?? null,
    max_students_per_cohort: org.max_students_per_cohort ?? null,
    max_observers_per_cohort: org.max_observers_per_cohort ?? null,
  }
}

const fieldInputCls =
  "h-10 rounded-[10px] border border-border bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary"

export function OrgAccountModal({
  org,
  onClose,
  onSaved,
  onDeleted,
}: {
  org: OrganizationAccountSummary | null
  onClose: () => void
  onSaved: (updated: OrganizationAccountSummary) => void
  onDeleted?: () => void
}) {
  const qc = useQueryClient()
  const toast = useToast()
  const isEditing = org !== null
  const [form, setForm] = useState<OrgFormState>(() => initialFormState(org))
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [resetUrl, setResetUrl] = useState<string | null>(null)
  const [copiedReset, setCopiedReset] = useState(false)

  const saveMut = useMutation({
    mutationFn: () => {
      if (isEditing && org) {
        return updateAdminOrganizationAccount(org.id, {
          org_name_latin: form.org_name_latin.trim(),
          org_name_arabic: form.org_name_arabic.trim() || null,
          org_type: form.org_type,
          country: form.country,
          city: form.city.trim() || null,
          full_name: form.full_name.trim(),
          email: form.email.trim() || undefined,
          phone: form.phone.trim() || null,
          password: form.password || undefined,
          is_approved: form.is_approved,
          can_publish_events: form.can_publish_events,
          can_author_courses: form.can_author_courses,
          can_publish_courses: form.can_publish_courses,
          course_scope_all: form.course_scope_all,
          allowed_course_ids: form.allowed_course_ids,
          quiz_scope: form.quiz_scope,
          allowed_quiz_template_ids: form.allowed_quiz_template_ids,
          readiness_scope: form.readiness_scope,
          allowed_readiness_preset_ids: form.allowed_readiness_preset_ids,
          max_events: form.max_events,
          max_programs: form.max_programs,
          max_cohorts: form.max_cohorts,
          max_students_per_cohort: form.max_students_per_cohort,
          max_observers_per_cohort: form.max_observers_per_cohort,
        })
      }
      return createAdminOrganizationAccount({
        org_name_latin: form.org_name_latin.trim(),
        org_name_arabic: form.org_name_arabic.trim() || null,
        org_type: form.org_type,
        country: form.country,
        city: form.city.trim() || null,
        full_name: form.full_name.trim(),
        email: form.email.trim(),
        phone: form.phone.trim() || null,
        password: form.password,
        is_approved: form.is_approved,
        can_publish_events: form.can_publish_events,
        can_author_courses: form.can_author_courses,
        can_publish_courses: form.can_publish_courses,
        course_scope_all: form.course_scope_all,
        allowed_course_ids: form.allowed_course_ids,
        quiz_scope: form.quiz_scope,
        allowed_quiz_template_ids: form.allowed_quiz_template_ids,
        readiness_scope: form.readiness_scope,
        allowed_readiness_preset_ids: form.allowed_readiness_preset_ids,
        max_events: form.max_events,
        max_programs: form.max_programs,
        max_cohorts: form.max_cohorts,
        max_students_per_cohort: form.max_students_per_cohort,
        max_observers_per_cohort: form.max_observers_per_cohort,
      })
    },
    onSuccess: (updated) => {
      void qc.invalidateQueries({ queryKey: ["admin-website-organizations"] })
      if (org) {
        void qc.invalidateQueries({ queryKey: ["admin-organization-detail", org.id] })
      }
      toast.success(isEditing ? "Organization updated" : "Organization account created")
      onSaved(updated)
    },
    onError: (err) => toast.error(getErrorMessage(err, "Could not save organization")),
  })

  const deleteMut = useMutation({
    mutationFn: () => {
      if (!org) throw new Error("No organization selected")
      return deleteAdminOrganizationAccount(org.id)
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["admin-website-organizations"] })
      toast.success("Organization removed")
      onDeleted?.()
      onClose()
    },
    onError: (err) => toast.error(getErrorMessage(err, "Could not remove organization")),
  })

  const resetLinkMut = useMutation({
    mutationFn: () => {
      if (!org) throw new Error("No organization selected")
      return getAdminOrganizationResetLink(org.id)
    },
    onSuccess: async (res) => {
      setResetUrl(res.reset_url)
      try {
        await navigator.clipboard.writeText(res.reset_url)
        setCopiedReset(true)
        toast.success(`Reset link copied for ${res.email}`)
      } catch {
        toast.success("Reset link generated")
      }
    },
    onError: (err) => toast.error(getErrorMessage(err, "Could not generate reset link")),
  })

  const canSubmit =
    form.org_name_latin.trim().length > 0 &&
    form.full_name.trim().length > 0 &&
    (isEditing || (form.email.trim().length > 0 && form.password.length >= 6))

  return (
    <Modal
      title={isEditing ? `Manage Organization: ${org.name_latin}` : "New Partner Organization"}
      onClose={onClose}
      maxWidth="sm:max-w-3xl max-w-3xl"
    >
      <div className="space-y-5">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Organization Name
            </span>
            <input
              type="text"
              value={form.org_name_latin}
              onChange={(e) => setForm((p) => ({ ...p, org_name_latin: e.target.value }))}
              placeholder="Abu Dhabi University"
              className={fieldInputCls}
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Arabic Name
            </span>
            <input
              type="text"
              dir="rtl"
              value={form.org_name_arabic}
              onChange={(e) => setForm((p) => ({ ...p, org_name_arabic: e.target.value }))}
              placeholder="جامعة أبوظبي"
              className={fieldInputCls}
            />
          </label>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Organization Type
            </span>
            <select
              value={form.org_type}
              onChange={(e) => setForm((p) => ({ ...p, org_type: e.target.value }))}
              className={fieldInputCls}
            >
              {ORG_TYPE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Country
            </span>
            <CountrySelect
              value={form.country}
              onChange={(v) => setForm((p) => ({ ...p, country: v }))}
              valueType="code"
              className={fieldInputCls}
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              City
            </span>
            <CityNameSelect
              country={form.country}
              value={form.city}
              onChange={(v) => setForm((p) => ({ ...p, city: v }))}
              className={fieldInputCls}
            />
          </label>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Primary Contact Name
            </span>
            <input
              type="text"
              value={form.full_name}
              onChange={(e) => setForm((p) => ({ ...p, full_name: e.target.value }))}
              placeholder="Dr. Jawad Yousaf"
              className={fieldInputCls}
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Contact Phone
            </span>
            <input
              type="text"
              value={form.phone}
              onChange={(e) => setForm((p) => ({ ...p, phone: e.target.value }))}
              placeholder="+971 50 000 0000"
              className={fieldInputCls}
            />
          </label>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Login Email
            </span>
            <input
              type="email"
              value={form.email}
              onChange={(e) => setForm((p) => ({ ...p, email: e.target.value }))}
              placeholder="partner@university.ac.ae"
              className={fieldInputCls}
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {isEditing ? "Reset Password (optional)" : "Initial Password (min 6 chars)"}
            </span>
            <input
              type="password"
              value={form.password}
              onChange={(e) => setForm((p) => ({ ...p, password: e.target.value }))}
              placeholder={isEditing ? "Leave empty to keep current" : "Minimum 6 characters"}
              className={fieldInputCls}
            />
          </label>
        </div>

        {resetUrl && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-[10px] border border-primary/30 bg-primary/10 p-3.5">
            <span className="break-all font-mono text-xs text-primary">{resetUrl}</span>
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="rounded-[10px]"
              onClick={async () => {
                await navigator.clipboard.writeText(resetUrl)
                setCopiedReset(true)
                toast.success("Copied reset URL")
              }}
            >
              {copiedReset ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
              {copiedReset ? "Copied" : "Copy"}
            </Button>
          </div>
        )}

        <div className="border-t border-border pt-4">
          <OrgGrantsAndQuotasForm
            data={form}
            onChange={(updatedGrants) => setForm((p) => ({ ...p, ...updatedGrants }))}
          />
        </div>

        {confirmDelete && isEditing && org && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-[10px] border border-destructive/30 bg-destructive/10 p-4">
            <span className="text-xs font-semibold text-destructive">
              Remove {org.name_latin} permanently? This unlinks its owner account if not used elsewhere.
            </span>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="rounded-[10px]"
                onClick={() => setConfirmDelete(false)}
              >
                Cancel
              </Button>
              <Button
                type="button"
                size="sm"
                variant="destructive"
                className="rounded-[10px]"
                disabled={deleteMut.isPending}
                onClick={() => deleteMut.mutate()}
              >
                {deleteMut.isPending ? "Removing" : "Confirm Delete"}
              </Button>
            </div>
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
          <div className="flex flex-wrap items-center gap-2">
            {isEditing && org?.owner_user_id && (
              <Button
                type="button"
                variant="outline"
                className="h-9 rounded-[10px] px-3.5 text-xs font-semibold"
                disabled={resetLinkMut.isPending}
                onClick={() => resetLinkMut.mutate()}
              >
                <KeyRound className="h-3.5 w-3.5" />
                {resetLinkMut.isPending ? "Generating" : "Copy Owner Reset Link"}
              </Button>
            )}
            {isEditing && !confirmDelete && (
              <Button
                type="button"
                variant="destructive"
                className="h-9 rounded-[10px] px-3.5 text-xs font-semibold"
                onClick={() => setConfirmDelete(true)}
              >
                <Trash2 className="h-3.5 w-3.5" />
                Delete Organization
              </Button>
            )}
          </div>

          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              className="h-9 rounded-[10px] px-4 text-xs font-semibold"
              onClick={onClose}
            >
              Cancel
            </Button>
            <Button
              type="button"
              className="h-9 rounded-[10px] px-5 text-xs font-semibold"
              disabled={!canSubmit || saveMut.isPending}
              onClick={() => saveMut.mutate()}
            >
              <Save className="h-3.5 w-3.5" />
              {saveMut.isPending ? "Saving" : isEditing ? "Save Changes" : "Create Organization"}
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  )
}

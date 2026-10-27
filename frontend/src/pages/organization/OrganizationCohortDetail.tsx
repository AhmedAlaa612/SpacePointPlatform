import { useState, useRef } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useParams, useNavigate, Link } from "@tanstack/react-router"
import * as XLSX from "xlsx"
import {
  ArrowLeft,
  Calendar,
  Users,
  Plus,
  Upload,
  Download,
  Trash2,
  ExternalLink,
  Layers,
  Clock,
  MapPin,
  CheckCircle2,
  Trophy,
  Key,
  FileSpreadsheet,
  Eye,
  X,
  Pencil,
} from "lucide-react"
import { useToast } from "@/components/ui/toast"
import { downloadCompetitionRosterTemplateApi } from "@/api/competitions"
import { getOrganizationTeamApi } from "@/api/websiteEvents"
import {
  getOrgCohortDetailApi,
  getOrgCohortRegistrationsApi,
  getOrgCohortObserversApi,
  addOrgCohortObserverApi,
  removeOrgCohortObserverApi,
  registerOrgStudentApi,
  bulkImportOrgStudentsApi,
  cancelOrgRegistrationApi,
  createOrgSessionApi,
  deleteOrgSessionApi,
  updateOrgCohortApi,
  type OrgCohortDetail,
  type OrgDeskRegisterInput,
  type OrgBulkImportRow,
  type OrgCohortObserver,
} from "@/api/organizationPrograms"
import { LmsCohortSection } from "@/pages/lms-authoring/components/LmsCohortSection"

type TabKey = "milestones" | "students" | "sessions"

export default function OrganizationCohortDetail() {
  const { cohortId } = useParams({ strict: false }) as { cohortId: string }
  const navigate = useNavigate()
  const toast = useToast()
  const qc = useQueryClient()

  const [activeTab, setActiveTab] = useState<TabKey>("milestones")
  const [studentsSubTab, setStudentsSubTab] = useState<"students" | "observers">("students")
  const [registerStudentOpen, setRegisterStudentOpen] = useState(false)
  const [bulkImportOpen, setBulkImportOpen] = useState(false)
  const [addObserverOpen, setAddObserverOpen] = useState(false)
  const [createSessionOpen, setCreateSessionOpen] = useState(false)
  const [editCohortOpen, setEditCohortOpen] = useState(false)

  const { data: cohort, isLoading: cohortLoading } = useQuery({
    queryKey: ["org-cohort-detail", cohortId],
    queryFn: () => getOrgCohortDetailApi(cohortId),
    enabled: Boolean(cohortId),
  })

  const { data: registrations = [], isLoading: regLoading } = useQuery({
    queryKey: ["org-cohort-registrations", cohortId],
    queryFn: () => getOrgCohortRegistrationsApi(cohortId),
    enabled: Boolean(cohortId) && activeTab === "students",
  })

  const { data: observers = [], isLoading: observersLoading } = useQuery<OrgCohortObserver[]>({
    queryKey: ["org-cohort-observers", cohortId],
    queryFn: () => getOrgCohortObserversApi(cohortId),
    enabled: Boolean(cohortId) && activeTab === "students",
  })

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["org-cohort-detail", cohortId] })
    void qc.invalidateQueries({ queryKey: ["org-cohort-registrations", cohortId] })
    void qc.invalidateQueries({ queryKey: ["org-cohort-observers", cohortId] })
  }

  const removeObserverMut = useMutation({
    mutationFn: (userId: string) => removeOrgCohortObserverApi(cohortId, userId),
    onSuccess: () => {
      toast.success("Observer unassigned")
      invalidate()
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail ?? "Failed to unassign observer")
    },
  })

  const cancelRegMut = useMutation({
    mutationFn: (regId: string) => cancelOrgRegistrationApi(cohortId, regId),
    onSuccess: () => {
      toast.success("Student registration cancelled")
      invalidate()
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail ?? "Failed to cancel registration")
    },
  })

  const deleteSessionMut = useMutation({
    mutationFn: (sessionId: string) => deleteOrgSessionApi(cohortId, sessionId),
    onSuccess: () => {
      toast.success("Session deleted")
      invalidate()
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail ?? "Failed to delete session")
    },
  })

  if (cohortLoading) {
    return (
      <div className="flex items-center justify-center p-12 text-sm text-muted-foreground">
        Loading cohort details…
      </div>
    )
  }

  if (!cohort) {
    return (
      <div className="p-6 rounded-2xl border border-destructive/20 bg-destructive/5 text-destructive text-sm">
        Cohort not found or you do not have permission to view it.
      </div>
    )
  }

  const isCompetition = Boolean(
    (cohort.program_type || "").toLowerCase() === "competition" ||
    (cohort.program_type || "").toLowerCase() === "hackathon" ||
    (cohort.program_name || "").toLowerCase().includes("compet") ||
    (cohort.name || "").toLowerCase().includes("compet")
  )

  return (
    <div className="flex flex-col gap-6 max-w-6xl mx-auto pb-12">
      {/* ── Top Bar ────────────────────────────────────────────────────────── */}
      <div className="flex flex-col gap-4">
        <button
          type="button"
          onClick={() => void navigate({ to: "/organization/programs" })}
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-muted-foreground hover:text-foreground transition w-fit"
        >
          <ArrowLeft className="w-4 h-4" /> Back to Programs
        </button>

        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-5 rounded-2xl border border-border bg-card shadow-sm">
          <div className="space-y-1">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs font-semibold px-2 py-0.5 rounded-md bg-primary/10 text-primary">
                {cohort.program_name}
              </span>
              <h1 className="text-xl font-bold text-foreground">{cohort.name}</h1>
              <span className="text-xs font-mono px-2 py-0.5 rounded bg-muted text-muted-foreground">
                {cohort.code || cohort.name}
              </span>
              {cohort.is_public && (
                <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-600 dark:text-emerald-400">
                  Public
                </span>
              )}
              <button
                type="button"
                onClick={() => setEditCohortOpen(true)}
                title="Edit Cohort Details"
                className="p-1 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition"
              >
                <Pencil className="w-3.5 h-3.5" />
              </button>
            </div>

            <div className="flex items-center gap-4 text-xs text-muted-foreground flex-wrap pt-1">
              <span className="inline-flex items-center gap-1">
                <Calendar className="w-3.5 h-3.5" /> {cohort.start_date} – {cohort.end_date}
              </span>
              {cohort.location && (
                <span className="inline-flex items-center gap-1">
                  <MapPin className="w-3.5 h-3.5" /> {cohort.location}
                </span>
              )}
              <span className="inline-flex items-center gap-1">
                <Users className="w-3.5 h-3.5" /> {cohort.active_students_count || 0} / {cohort.capacity || "—"}{" "}
                students
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0 flex-wrap">
            <button
              type="button"
              onClick={() => setEditCohortOpen(true)}
              className="inline-flex items-center gap-1.5 h-9 px-3.5 rounded-xl border border-border bg-background text-xs font-semibold text-foreground hover:bg-muted transition shadow-sm"
              title="Edit Cohort Details"
            >
              <Pencil className="w-3.5 h-3.5 text-primary" /> Edit Cohort
            </button>

            {isCompetition && (
              <Link
                to="/organization/programs/$cohortId/judging"
                params={{ cohortId: cohort.id }}
                className="inline-flex items-center gap-1.5 h-9 px-3.5 rounded-xl bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition shadow-sm"
              >
                <Trophy className="w-3.5 h-3.5" /> Judging & Roster
              </Link>
            )}

            <Link
              to="/lms-authoring/invite-codes"
              className="inline-flex items-center gap-1.5 h-9 px-3 rounded-xl border border-border bg-background text-xs font-semibold text-foreground hover:bg-muted transition"
              title="Manage LMS Invite Codes"
            >
              <Key className="w-3.5 h-3.5 text-primary" /> Invite Codes
            </Link>

            {cohort.linked_events && cohort.linked_events.length > 0 && (
              <a
                href={`/events/uae/${cohort.linked_events[0].slug}`}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 h-9 px-3.5 rounded-xl border border-border bg-background text-xs font-semibold text-foreground hover:bg-muted transition"
              >
                <ExternalLink className="w-3.5 h-3.5" /> Landing Page
              </a>
            )}
          </div>
        </div>
      </div>

      {/* ── Navigation Tabs ─────────────────────────────────────────────────── */}
      <div className="flex gap-1 border-b border-border overflow-x-auto scrollbar-none no-scrollbar">
        {[
          { key: "milestones", label: "Milestones & Modules", icon: Layers },
          {
            key: "students",
            label: `Students (${cohort.active_students_count || 0})`,
            icon: Users,
          },
          {
            key: "sessions",
            label: `Sessions (${cohort.sessions?.length || 0})`,
            icon: Clock,
          },
        ].map((t) => {
          const Icon = t.icon
          const isActive = activeTab === t.key
          return (
            <button
              key={t.key}
              type="button"
              onClick={() => setActiveTab(t.key as TabKey)}
              className={`flex items-center gap-2 px-4 py-2.5 text-xs font-semibold border-b-2 -mb-px transition whitespace-nowrap ${
                isActive
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              {t.label}
            </button>
          )
        })}
      </div>

      {/* ── Tab Content ─────────────────────────────────────────────────────── */}

      {/* 1. MILESTONES & LMS WORKSPACE */}
      {activeTab === "milestones" && (
        <div className="space-y-4">
          <LmsCohortSection cohortId={cohort.id} cohortName={cohort.name} />
        </div>
      )}

      {/* 2. STUDENTS & ENROLLMENT */}
      {activeTab === "students" && (
        <div className="space-y-4">
          {/* Sub-tab switcher: Students vs Team Observers */}
          <div className="flex items-center gap-2 border-b border-border pb-2">
            <button
              type="button"
              onClick={() => setStudentsSubTab("students")}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition ${
                studentsSubTab === "students"
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted"
              }`}
            >
              Enrolled Students ({registrations?.length || 0})
            </button>
            <button
              type="button"
              onClick={() => setStudentsSubTab("observers")}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition ${
                studentsSubTab === "observers"
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted"
              }`}
            >
              Team Observers ({observers?.length || 0})
            </button>
          </div>

          {studentsSubTab === "students" ? (
            <>
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-xl border border-border bg-card">
                <div>
                  <h3 className="text-sm font-bold text-foreground">Enrolled Students</h3>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Manage student registrations, activate LMS accounts, and monitor capacity.
                  </p>
                </div>

                <div className="flex items-center gap-2 shrink-0 flex-wrap">
                  <Link
                    to="/lms-authoring/invite-codes"
                    className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg border border-border bg-background text-xs font-semibold text-foreground hover:bg-muted transition"
                  >
                    <Key className="w-3.5 h-3.5 text-primary" /> Invite Codes
                  </Link>
                  <Link
                    to="/lms-authoring/students"
                    search={{ invite_code: undefined }}
                    className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg border border-border bg-background text-xs font-semibold text-foreground hover:bg-muted transition"
                  >
                    <Users className="w-3.5 h-3.5 text-primary" /> Student Directory
                  </Link>
                  <button
                    type="button"
                    onClick={() => setBulkImportOpen(true)}
                    className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg border border-border bg-background text-xs font-semibold text-foreground hover:bg-muted transition"
                  >
                    <Upload className="w-3.5 h-3.5" /> Import
                  </button>
                  <button
                    type="button"
                    onClick={() => setRegisterStudentOpen(true)}
                    className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition"
                  >
                    <Plus className="w-3.5 h-3.5" /> Register Student
                  </button>
                </div>
              </div>

              {isCompetition && (
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5 rounded-xl border border-primary/20 bg-primary/5">
                  <div className="flex items-center gap-2.5">
                    <Trophy className="w-4 h-4 text-primary shrink-0" />
                    <span className="text-xs text-foreground font-medium">
                      Competition mode: Upload complete team rosters via Excel with the template, and assign members to teams.
                    </span>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      type="button"
                      onClick={() => void downloadCompetitionRosterTemplateApi()}
                      className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline"
                    >
                      <Download className="w-3 h-3" /> Download Template (.xlsx)
                    </button>
                    <span>·</span>
                    <Link
                      to="/organization/programs/$cohortId/judging"
                      params={{ cohortId: cohort.id }}
                      className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline"
                    >
                      Open Roster & Assign <ExternalLink className="w-3 h-3" />
                    </Link>
                  </div>
                </div>
              )}

              {regLoading ? (
                <div className="p-8 text-center text-xs text-muted-foreground">
                  Loading student roster…
                </div>
              ) : (!registrations || registrations.length === 0) ? (
                <div className="rounded-2xl border border-dashed border-border p-10 text-center flex flex-col items-center gap-2">
                  <Users className="w-8 h-8 text-muted-foreground" />
                  <h4 className="text-sm font-bold text-foreground">No students enrolled yet</h4>
                  <p className="text-xs text-muted-foreground max-w-sm">
                    Register students individually or import a student list using CSV format.
                  </p>
                </div>
              ) : (
                <div className="rounded-2xl border border-border bg-card overflow-hidden">
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-muted/40 text-muted-foreground uppercase text-[10px] tracking-wider border-b border-border">
                        <tr>
                          <th className="py-3 px-4">Student</th>
                          <th className="py-3 px-4">Contact</th>
                          <th className="py-3 px-4">City / School</th>
                          <th className="py-3 px-4">LMS Status</th>
                          <th className="py-3 px-4">Enrolled On</th>
                          <th className="py-3 px-4 text-right">Actions</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border">
                        {(registrations || []).map((r) => (
                          <tr key={r.id} className="hover:bg-muted/20 transition">
                            <td className="py-3 px-4">
                              <span className="font-semibold text-foreground block">
                                {r.student_name}
                              </span>
                              {r.grade && (
                                <span className="text-[11px] text-muted-foreground">
                                  Grade {r.grade}
                                </span>
                              )}
                            </td>
                            <td className="py-3 px-4">
                              <span className="text-foreground block">{r.student_email || "—"}</span>
                              <span className="text-[11px] text-muted-foreground">
                                {r.student_phone || ""}
                              </span>
                            </td>
                            <td className="py-3 px-4">
                              <span className="text-foreground block">{r.school_name || "—"}</span>
                              <span className="text-[11px] text-muted-foreground">{r.city || ""}</span>
                            </td>
                            <td className="py-3 px-4">
                              {r.has_lms_account ? (
                                <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-600 dark:text-emerald-400">
                                  <CheckCircle2 className="w-2.5 h-2.5" /> Active
                                </span>
                              ) : (
                                <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
                                  No Account
                                </span>
                              )}
                            </td>
                            <td className="py-3 px-4 text-muted-foreground">
                              {r.created_at ? new Date(r.created_at).toLocaleDateString() : "—"}
                            </td>
                            <td className="py-3 px-4 text-right">
                              <button
                                type="button"
                                onClick={() => {
                                  if (window.confirm(`Cancel registration for "${r.student_name}"?`)) {
                                    cancelRegMut.mutate(r.id)
                                  }
                                }}
                                className="inline-flex items-center justify-center h-7 w-7 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition"
                                title="Cancel Registration"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          ) : (
            <>
              {/* Team Observers Sub-tab */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-xl border border-border bg-card">
                <div>
                  <h3 className="text-sm font-bold text-foreground">Cohort Team Observers</h3>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Assign members of your organization team to observe cohort activities and student submissions.
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setAddObserverOpen(true)}
                    className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition"
                  >
                    <Plus className="w-3.5 h-3.5" /> Add Observer
                  </button>
                </div>
              </div>

              {observersLoading ? (
                <div className="p-8 text-center text-xs text-muted-foreground">
                  Loading observers…
                </div>
              ) : (!observers || observers.length === 0) ? (
                <div className="rounded-2xl border border-dashed border-border p-10 text-center flex flex-col items-center gap-2">
                  <Eye className="w-8 h-8 text-muted-foreground" />
                  <h4 className="text-sm font-bold text-foreground">No observers assigned yet</h4>
                  <p className="text-xs text-muted-foreground max-w-sm">
                    Assign staff from your organization team to monitor progress and deliverables in observer mode.
                  </p>
                  <button
                    type="button"
                    onClick={() => setAddObserverOpen(true)}
                    className="mt-2 inline-flex items-center gap-1.5 h-8 px-3 rounded-lg bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition"
                  >
                    <Plus className="w-3.5 h-3.5" /> Add Observer
                  </button>
                </div>
              ) : (
                <div className="rounded-2xl border border-border bg-card overflow-hidden">
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-muted/40 text-muted-foreground uppercase text-[10px] tracking-wider border-b border-border">
                        <tr>
                          <th className="py-3 px-4">Observer</th>
                          <th className="py-3 px-4">Email</th>
                          <th className="py-3 px-4">Phone</th>
                          <th className="py-3 px-4">Assigned On</th>
                          <th className="py-3 px-4 text-right">Actions</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border">
                        {observers.map((obs) => (
                          <tr key={obs.id} className="hover:bg-muted/20 transition">
                            <td className="py-3 px-4">
                              <span className="font-semibold text-foreground block">{obs.full_name}</span>
                              <span className="text-[10px] text-primary bg-primary/10 px-1.5 py-0.5 rounded font-medium inline-block mt-0.5">
                                Observer
                              </span>
                            </td>
                            <td className="py-3 px-4 text-muted-foreground">{obs.email}</td>
                            <td className="py-3 px-4 text-muted-foreground">{obs.phone || "—"}</td>
                            <td className="py-3 px-4 text-muted-foreground">
                              {obs.assigned_at ? new Date(obs.assigned_at).toLocaleDateString() : "—"}
                            </td>
                            <td className="py-3 px-4 text-right">
                              <button
                                type="button"
                                onClick={() => {
                                  if (window.confirm(`Remove ${obs.full_name} from cohort observers?`)) {
                                    removeObserverMut.mutate(obs.user_id)
                                  }
                                }}
                                className="inline-flex items-center gap-1 text-xs text-destructive hover:underline"
                              >
                                <Trash2 className="w-3.5 h-3.5" /> Unassign
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* 3. SESSIONS */}
      {activeTab === "sessions" && (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-xl border border-border bg-card">
            <div>
              <h3 className="text-sm font-bold text-foreground">Cohort Sessions & Workshops</h3>
              <p className="text-xs text-muted-foreground mt-0.5">
                Schedule webinars, workshops, or milestone review sessions for this cohort.
              </p>
            </div>

            <button
              type="button"
              onClick={() => setCreateSessionOpen(true)}
              className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition shrink-0"
            >
              <Plus className="w-3.5 h-3.5" /> Add Session
            </button>
          </div>

          {(!cohort.sessions || cohort.sessions.length === 0) ? (
            <div className="rounded-2xl border border-dashed border-border p-10 text-center flex flex-col items-center gap-2">
              <Clock className="w-8 h-8 text-muted-foreground" />
              <h4 className="text-sm font-bold text-foreground">No sessions scheduled</h4>
              <p className="text-xs text-muted-foreground max-w-sm">
                Add live dates, webinars, or judging sessions to the cohort timeline.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {(cohort.sessions || []).map((s) => (
                <div
                  key={s.id}
                  className="rounded-xl border border-border bg-card p-4 flex flex-col justify-between gap-3"
                >
                  <div>
                    <div className="flex items-start justify-between gap-2">
                      <h4 className="text-sm font-bold text-foreground">{s.title}</h4>
                      <span className="text-[10px] font-semibold uppercase px-2 py-0.5 rounded bg-muted text-muted-foreground">
                        {s.session_type}
                      </span>
                    </div>

                    <div className="mt-2 space-y-1 text-xs text-muted-foreground">
                      <div className="flex items-center gap-1.5">
                        <Calendar className="w-3.5 h-3.5" />
                        <span>
                          {s.date} • {s.start_time} – {s.end_time}
                        </span>
                      </div>
                      {s.location && (
                        <div className="flex items-center gap-1.5">
                          <MapPin className="w-3.5 h-3.5" />
                          <span>{s.location}</span>
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center justify-end pt-2 border-t border-border">
                    <button
                      type="button"
                      onClick={() => {
                        if (window.confirm(`Delete session "${s.title}"?`)) {
                          deleteSessionMut.mutate(s.id)
                        }
                      }}
                      className="inline-flex items-center gap-1 h-7 px-2 text-xs text-muted-foreground hover:text-destructive transition"
                    >
                      <Trash2 className="w-3 h-3" /> Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Edit Cohort Modal ─────────────────────────────────────────────── */}
      {editCohortOpen && (
        <EditCohortModal
          cohort={cohort}
          onClose={() => setEditCohortOpen(false)}
          onSaved={invalidate}
        />
      )}

      {/* ── Desk Register Modal ────────────────────────────────────────────── */}
      {registerStudentOpen && (
        <DeskRegisterModal
          cohortId={cohort.id}
          onClose={() => setRegisterStudentOpen(false)}
          onSuccess={() => {
            setRegisterStudentOpen(false)
            invalidate()
          }}
        />
      )}

      {/* ── Bulk Import CSV Modal ───────────────────────────────────────────── */}
      {bulkImportOpen && (
        <BulkImportModal
          cohortId={cohort.id}
          isCompetition={isCompetition}
          onClose={() => setBulkImportOpen(false)}
          onSuccess={() => {
            setBulkImportOpen(false)
            invalidate()
          }}
        />
      )}

      {/* ── Create Session Modal ────────────────────────────────────────────── */}
      {createSessionOpen && (
        <CreateSessionModal
          cohortId={cohort.id}
          onClose={() => setCreateSessionOpen(false)}
          onSuccess={() => {
            setCreateSessionOpen(false)
            invalidate()
          }}
        />
      )}

      {/* ── Add Observer Modal ──────────────────────────────────────────────── */}
      {addObserverOpen && (
        <AddObserverModal
          cohortId={cohort.id}
          open={addObserverOpen}
          existingObserverUserIds={new Set((observers || []).map((o) => o.user_id))}
          onClose={() => setAddObserverOpen(false)}
          onSuccess={() => {
            setAddObserverOpen(false)
            invalidate()
          }}
        />
      )}
    </div>
  )
}

// ── Modals & Sub-components ──────────────────────────────────────────────────

function AddObserverModal({
  cohortId,
  open,
  onClose,
  onSuccess,
  existingObserverUserIds,
}: {
  cohortId: string
  open: boolean
  onClose: () => void
  onSuccess: () => void
  existingObserverUserIds: Set<string>
}) {
  const toast = useToast()
  const [selectedUserId, setSelectedUserId] = useState("")

  const { data: team = [], isLoading } = useQuery({
    queryKey: ["org-team-members"],
    queryFn: getOrganizationTeamApi,
    enabled: open,
  })

  // Filter out members who are already observers
  const eligibleTeam = team.filter((m) => !existingObserverUserIds.has(m.id))

  const addMut = useMutation({
    mutationFn: () => addOrgCohortObserverApi(cohortId, selectedUserId),
    onSuccess: () => {
      toast.success("Team member assigned as cohort observer!")
      onSuccess()
      onClose()
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail ?? "Failed to assign observer")
    },
  })

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl border border-border bg-card p-6 shadow-2xl flex flex-col gap-4">
        <div className="flex items-center justify-between border-b border-border pb-3">
          <div>
            <h3 className="text-base font-bold text-foreground">Add Team Observer</h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              Select a member of your organization team to observe this cohort.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-lg text-muted-foreground hover:bg-muted transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {isLoading ? (
          <div className="py-8 text-center text-xs text-muted-foreground">Loading organization team…</div>
        ) : eligibleTeam.length === 0 ? (
          <div className="py-6 text-center space-y-2">
            <p className="text-xs text-muted-foreground">
              {team.length === 0
                ? "No team members found. Go to the Team tab to invite organization staff first."
                : "All organization team members are already assigned as observers."}
            </p>
            <Link
              to="/organization/team"
              className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline"
            >
              Manage Team Members <ExternalLink className="w-3 h-3" />
            </Link>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-foreground">Select Team Member</label>
              <select
                value={selectedUserId}
                onChange={(e) => setSelectedUserId(e.target.value)}
                className="w-full h-9 px-3 rounded-xl border border-border bg-background text-xs text-foreground focus:outline-none focus:border-primary"
              >
                <option value="">-- Choose a team member --</option>
                {eligibleTeam.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.full_name} ({m.email}) {m.is_owner ? "• Owner" : ""}
                  </option>
                ))}
              </select>
            </div>

            <div className="p-3 rounded-xl border border-primary/20 bg-primary/5 text-[11px] text-muted-foreground leading-relaxed">
              Observers can access the student portal to inspect checklists, assignments, and submissions in observer mode without being ranked or counted as competitor students.
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-border">
              <button
                type="button"
                onClick={onClose}
                className="h-9 px-4 rounded-xl border border-border text-xs font-semibold hover:bg-muted transition"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={!selectedUserId || addMut.isPending}
                onClick={() => addMut.mutate()}
                className="h-9 px-4 rounded-xl bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition disabled:opacity-50"
              >
                {addMut.isPending ? "Assigning..." : "Assign as Observer"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function DeskRegisterModal({
  cohortId,
  onClose,
  onSuccess,
}: {
  cohortId: string
  onClose: () => void
  onSuccess: () => void
}) {
  const toast = useToast()
  const [form, setForm] = useState<OrgDeskRegisterInput>({
    student_name: "",
    email: "",
    phone: "",
    city: "",
    grade: "",
    school_name: "",
    create_lms_account: true,
    send_welcome_email: true,
  })

  const mut = useMutation({
    mutationFn: () => registerOrgStudentApi(cohortId, form),
    onSuccess: (res) => {
      toast.success(`Registered ${res.student_name}!`)
      onSuccess()
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail ?? "Failed to register student")
    },
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl border border-border bg-card p-6 shadow-xl space-y-4">
        <h2 className="text-base font-bold text-foreground">Register Student</h2>

        <div className="space-y-3">
          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-muted-foreground">Full Name *</span>
            <input
              type="text"
              value={form.student_name}
              onChange={(e) => setForm((p) => ({ ...p, student_name: e.target.value }))}
              placeholder="Student full name"
              className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
            />
          </label>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">Email</span>
              <input
                type="email"
                value={form.email}
                onChange={(e) => setForm((p) => ({ ...p, email: e.target.value }))}
                placeholder="student@example.com"
                className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">Phone</span>
              <input
                type="text"
                value={form.phone}
                onChange={(e) => setForm((p) => ({ ...p, phone: e.target.value }))}
                placeholder="+971 50 000 0000"
                className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
              />
            </label>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">City</span>
              <input
                type="text"
                value={form.city}
                onChange={(e) => setForm((p) => ({ ...p, city: e.target.value }))}
                placeholder="City"
                className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">Grade / Year</span>
              <input
                type="text"
                value={form.grade}
                onChange={(e) => setForm((p) => ({ ...p, grade: e.target.value }))}
                placeholder="e.g. 11 or University"
                className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
              />
            </label>
          </div>

          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-muted-foreground">School / Institution</span>
            <input
              type="text"
              value={form.school_name}
              onChange={(e) => setForm((p) => ({ ...p, school_name: e.target.value }))}
              placeholder="e.g. Academy of Sciences"
              className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
            />
          </label>

          <div className="pt-2 border-t border-border space-y-2">
            <label className="flex items-center gap-2 cursor-pointer text-xs font-medium text-foreground">
              <input
                type="checkbox"
                checked={form.create_lms_account}
                onChange={(e) => setForm((p) => ({ ...p, create_lms_account: e.target.checked }))}
                className="h-4 w-4 rounded text-primary focus:ring-primary border-border"
              />
              Create student LMS portal account
            </label>

            {form.create_lms_account && form.email && (
              <label className="flex items-center gap-2 cursor-pointer text-xs font-medium text-foreground">
                <input
                  type="checkbox"
                  checked={form.send_welcome_email}
                  onChange={(e) =>
                    setForm((p) => ({ ...p, send_welcome_email: e.target.checked }))
                  }
                  className="h-4 w-4 rounded text-primary focus:ring-primary border-border"
                />
                Send welcome email with access link
              </label>
            )}
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="h-9 px-4 rounded-xl border border-border text-xs font-medium hover:bg-muted transition"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!(form.student_name || "").trim() || mut.isPending}
            onClick={() => mut.mutate()}
            className="h-9 px-4 rounded-xl bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition disabled:opacity-50"
          >
            {mut.isPending ? "Registering..." : "Register Student"}
          </button>
        </div>
      </div>
    </div>
  )
}

function BulkImportModal({
  cohortId,
  isCompetition,
  onClose,
  onSuccess,
}: {
  cohortId: string
  isCompetition?: boolean
  onClose: () => void
  onSuccess: () => void
}) {
  const toast = useToast()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [tab, setTab] = useState<"file" | "paste">("file")
  const [csvText, setCsvText] = useState("")
  const [fileRows, setFileRows] = useState<OrgBulkImportRow[]>([])
  const [fileName, setFileName] = useState<string>("")
  const [isParsing, setIsParsing] = useState(false)

  const parseCsvText = (text: string): OrgBulkImportRow[] => {
    const lines = text
      .split(/\r?\n/)
      .map((l) => (l || "").trim())
      .filter(Boolean)
    if (lines.length === 0) return []

    const firstLine = lines[0].toLowerCase()
    const startIndex =
      firstLine.includes("name") || firstLine.includes("email") ? 1 : 0

    const rows: OrgBulkImportRow[] = []
    for (let i = startIndex; i < lines.length; i++) {
      const parts = lines[i].split(",").map((p) => (p || "").trim())
      if (parts.length > 0 && parts[0]) {
        rows.push({
          student_name: parts[0],
          email: parts[1] || undefined,
          phone: parts[2] || undefined,
          city: parts[3] || undefined,
          grade: parts[4] || undefined,
          school_name: parts[5] || undefined,
        })
      }
    }
    return rows
  }

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setFileName(file.name)
    setIsParsing(true)

    try {
      if (file.name.endsWith(".csv")) {
        const text = await file.text()
        const parsed = parseCsvText(text)
        setFileRows(parsed)
      } else {
        const buffer = await file.arrayBuffer()
        const wb = XLSX.read(buffer, { type: "array" })
        const sheetName = wb.SheetNames[0]
        const sheet = wb.Sheets[sheetName]
        const rawJson: Record<string, any>[] = XLSX.utils.sheet_to_json(sheet, { defval: "" })

        const mapped: OrgBulkImportRow[] = []
        for (const row of rawJson) {
          // Normalize column headers
          let name = ""
          let email = ""
          let phone = ""
          let school = ""
          let city = ""
          let grade = ""

          for (const [k, v] of Object.entries(row)) {
            const lk = k.toLowerCase().replace(/[^a-z0-9]/g, "")
            const val = String(v ?? "").trim()
            if (!val) continue

            if (lk.includes("name") || lk.includes("member") || lk.includes("student")) {
              if (!name) name = val
            } else if (lk.includes("email") || lk.includes("mail")) {
              if (!email) email = val
            } else if (lk.includes("phone") || lk.includes("tel") || lk.includes("mobile")) {
              if (!phone) phone = val
            } else if (lk.includes("school") || lk.includes("univ") || lk.includes("institution") || lk.includes("organization")) {
              if (!school) school = val
            } else if (lk.includes("city") || lk.includes("emirate")) {
              if (!city) city = val
            } else if (lk.includes("grade") || lk.includes("year")) {
              if (!grade) grade = val
            }
          }

          if (name) {
            mapped.push({
              student_name: name,
              email: email || undefined,
              phone: phone || undefined,
              school_name: school || undefined,
              city: city || undefined,
              grade: grade || undefined,
            })
          }
        }
        setFileRows(mapped)
      }
    } catch (err: any) {
      toast.error("Failed to parse spreadsheet file: " + (err?.message || "Invalid format"))
    } finally {
      setIsParsing(false)
    }
  }

  const activeRows = tab === "file" ? fileRows : parseCsvText(csvText)

  const mut = useMutation({
    mutationFn: () => bulkImportOrgStudentsApi(cohortId, activeRows),
    onSuccess: (res) => {
      toast.success(`Imported ${res.imported ?? activeRows.length} students!`)
      if (res.failed > 0) {
        toast.error(`${res.failed} entries could not be imported.`)
      }
      onSuccess()
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail ?? "Failed to bulk import students")
    },
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-xl rounded-2xl border border-border bg-card p-6 shadow-xl space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-bold text-foreground">Import Student Roster</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Upload an Excel (.xlsx) roster or paste CSV lines.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void downloadCompetitionRosterTemplateApi()}
            className="inline-flex items-center gap-1.5 h-8 px-2.5 rounded-lg border border-border bg-background text-xs font-semibold text-primary hover:bg-muted transition shrink-0"
            title="Download Excel Roster Template"
          >
            <Download className="w-3.5 h-3.5" /> Download Template (.xlsx)
          </button>
        </div>

        {isCompetition && (
          <div className="p-3 rounded-xl border border-primary/20 bg-primary/5 flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 text-xs">
            <div className="flex items-center gap-2">
              <Trophy className="w-4 h-4 text-primary shrink-0" />
              <span className="text-foreground">
                Competition cohort: Assign team members, inspect diagnostics & configure live rubric.
              </span>
            </div>
            <Link
              to="/organization/programs/$cohortId/judging"
              params={{ cohortId }}
              className="inline-flex items-center gap-1 font-semibold text-primary hover:underline shrink-0"
            >
              Open Competition Judging <ExternalLink className="w-3 h-3" />
            </Link>
          </div>
        )}

        {/* Mode Selector */}
        <div className="flex rounded-xl bg-muted/40 p-1 border border-border">
          <button
            type="button"
            onClick={() => setTab("file")}
            className={`flex-1 py-1.5 text-xs font-semibold rounded-lg transition ${
              tab === "file" ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            Upload Spreadsheet (.xlsx / .csv)
          </button>
          <button
            type="button"
            onClick={() => setTab("paste")}
            className={`flex-1 py-1.5 text-xs font-semibold rounded-lg transition ${
              tab === "paste" ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            Paste CSV Text
          </button>
        </div>

        {tab === "file" ? (
          <div className="space-y-3">
            <input
              type="file"
              ref={fileInputRef}
              onChange={(e) => void handleFileUpload(e)}
              accept=".xlsx,.xls,.csv"
              className="hidden"
            />
            <div
              onClick={() => fileInputRef.current?.click()}
              className="border-2 border-dashed border-border hover:border-primary/50 rounded-2xl p-6 text-center cursor-pointer bg-muted/10 transition flex flex-col items-center gap-2"
            >
              <div className="w-10 h-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center">
                <FileSpreadsheet className="w-5 h-5" />
              </div>
              <div>
                <p className="text-xs font-semibold text-foreground">
                  {fileName ? fileName : "Click to select .xlsx or .csv roster spreadsheet"}
                </p>
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  Supports columns: Team ID, Student Name, Email, Phone, School / University, City, Grade
                </p>
              </div>
            </div>

            {isParsing && (
              <p className="text-xs text-center text-muted-foreground">Parsing spreadsheet rows…</p>
            )}

            {fileRows.length > 0 && (
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span className="font-semibold text-foreground">{fileRows.length} students detected</span>
                  <button
                    type="button"
                    onClick={() => { setFileRows([]); setFileName("") }}
                    className="text-destructive hover:underline text-[11px]"
                  >
                    Clear File
                  </button>
                </div>
                <div className="rounded-xl border border-border bg-background overflow-hidden max-h-44 overflow-y-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-muted/40 text-[10px] uppercase text-muted-foreground tracking-wider border-b border-border">
                      <tr>
                        <th className="py-1.5 px-3">Name</th>
                        <th className="py-1.5 px-3">Email</th>
                        <th className="py-1.5 px-3">School</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {fileRows.slice(0, 5).map((r, i) => (
                        <tr key={i} className="hover:bg-muted/10">
                          <td className="py-1 px-3 font-medium text-foreground">{r.student_name}</td>
                          <td className="py-1 px-3 text-muted-foreground">{r.email || "—"}</td>
                          <td className="py-1 px-3 text-muted-foreground">{r.school_name || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {fileRows.length > 5 && (
                    <div className="p-2 text-center text-[11px] text-muted-foreground border-t border-border bg-muted/10">
                      + {fileRows.length - 5} more students in file
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-2">
            <textarea
              rows={6}
              value={csvText}
              onChange={(e) => setCsvText(e.target.value)}
              placeholder={`Fatima Al Mazrouei,fatima@example.com,+971500000001,Abu Dhabi,11,Applied Technology High School\nRashid Al Nuaimi,rashid@example.com,+971500000002,Dubai,12,Dubai National School`}
              className="w-full p-3 rounded-xl border border-border bg-background font-mono text-xs focus:outline-none focus:border-primary resize-none"
            />
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>{activeRows.length} valid students detected</span>
              <button
                type="button"
                onClick={() =>
                  setCsvText(
                    "Name,Email,Phone,City,Grade,School\nStudent One,student1@example.com,+971501111111,Dubai,10,National School\nStudent Two,student2@example.com,+971502222222,Sharjah,11,Innovation Academy"
                  )
                }
                className="text-primary hover:underline text-[11px]"
              >
                Insert Sample Template
              </button>
            </div>
          </div>
        )}

        <div className="flex items-center justify-end gap-2 pt-2 border-t border-border">
          <button
            type="button"
            onClick={onClose}
            className="h-9 px-4 rounded-xl border border-border text-xs font-medium hover:bg-muted transition"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={activeRows.length === 0 || mut.isPending}
            onClick={() => mut.mutate()}
            className="h-9 px-4 rounded-xl bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition disabled:opacity-50"
          >
            {mut.isPending ? "Importing..." : `Import ${activeRows.length} Students`}
          </button>
        </div>
      </div>
    </div>
  )
}

function CreateSessionModal({
  cohortId,
  onClose,
  onSuccess,
}: {
  cohortId: string
  onClose: () => void
  onSuccess: () => void
}) {
  const toast = useToast()
  const today = new Date().toISOString().split("T")[0]

  const [title, setTitle] = useState("")
  const [sessionType, setSessionType] = useState("workshop")
  const [date, setDate] = useState(today)
  const [startTime, setStartTime] = useState("10:00")
  const [endTime, setEndTime] = useState("12:00")
  const [location, setLocation] = useState("")

  const mut = useMutation({
    mutationFn: () =>
      createOrgSessionApi(cohortId, {
        title: (title || "").trim(),
        session_type: sessionType,
        date,
        start_time: startTime,
        end_time: endTime,
        location: (location || "").trim() || undefined,
      }),
    onSuccess: () => {
      toast.success("Session scheduled!")
      onSuccess()
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail ?? "Failed to create session")
    },
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl border border-border bg-card p-6 shadow-xl space-y-4">
        <h2 className="text-base font-bold text-foreground">Schedule Session</h2>

        <div className="space-y-3">
          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-muted-foreground">Title *</span>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Kickoff & Orientation"
              className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-muted-foreground">Type</span>
            <select
              value={sessionType}
              onChange={(e) => setSessionType(e.target.value)}
              className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
            >
              <option value="workshop">Workshop</option>
              <option value="lecture">Lecture / Webinar</option>
              <option value="mentoring">Mentoring</option>
              <option value="judging">Judging / Showcase</option>
              <option value="other">Other</option>
            </select>
          </label>

          <div className="grid grid-cols-3 gap-2">
            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">Date</span>
              <input
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                className="h-9 px-2 rounded-xl border border-border bg-background text-xs focus:outline-none focus:border-primary"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">Start</span>
              <input
                type="time"
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
                className="h-9 px-2 rounded-xl border border-border bg-background text-xs focus:outline-none focus:border-primary"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">End</span>
              <input
                type="time"
                value={endTime}
                onChange={(e) => setEndTime(e.target.value)}
                className="h-9 px-2 rounded-xl border border-border bg-background text-xs focus:outline-none focus:border-primary"
              />
            </label>
          </div>

          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-muted-foreground">Location / Meeting Link</span>
            <input
              type="text"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="e.g. Zoom Link or Room 204"
              className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
            />
          </label>
        </div>

        <div className="flex items-center justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="h-9 px-4 rounded-xl border border-border text-xs font-medium hover:bg-muted transition"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!(title || "").trim() || mut.isPending}
            onClick={() => mut.mutate()}
            className="h-9 px-4 rounded-xl bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition disabled:opacity-50"
          >
            {mut.isPending ? "Scheduling..." : "Schedule Session"}
          </button>
        </div>
      </div>
    </div>
  )
}

function EditCohortModal({
  cohort,
  onClose,
  onSaved,
}: {
  cohort: OrgCohortDetail
  onClose: () => void
  onSaved: () => void
}) {
  const toast = useToast()
  const [name, setName] = useState(cohort.name || "")
  const [code, setCode] = useState(cohort.code || cohort.name || "")
  const [startDate, setStartDate] = useState(cohort.start_date || "")
  const [endDate, setEndDate] = useState(cohort.end_date || "")
  const [location, setLocation] = useState(cohort.location || "")
  const [capacity, setCapacity] = useState(String(cohort.capacity ?? 50))
  const [isPublic, setIsPublic] = useState(Boolean(cohort.is_public))
  const [checklistTitleOverride, setChecklistTitleOverride] = useState(
    cohort.checklist_title_override || ""
  )

  const capacityNum = parseInt(capacity, 10) || 0
  const capacityQuotaExceeded =
    cohort.org_capacity_limit !== null &&
    cohort.org_capacity_limit !== undefined &&
    capacityNum > cohort.org_capacity_limit

  const mut = useMutation({
    mutationFn: () =>
      updateOrgCohortApi(cohort.id, {
        name: (name || "").trim(),
        code: (code || "").trim().toUpperCase(),
        start_date: startDate,
        end_date: endDate,
        location: (location || "").trim() || undefined,
        capacity: capacityNum || cohort.capacity,
        is_public: isPublic,
        checklist_title_override: (checklistTitleOverride || "").trim() || null,
      }),
    onSuccess: () => {
      toast.success("Cohort details updated!")
      onSaved()
      onClose()
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail ?? "Failed to update cohort")
    },
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-2xl border border-border bg-card p-6 shadow-xl space-y-4">
        <div className="flex items-center justify-between border-b border-border pb-3">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
              <Pencil className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-base font-bold text-foreground">Edit Cohort Details</h2>
              <p className="text-xs text-muted-foreground">Update cohort timing, capacity, and catalog settings</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">Cohort Name *</span>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">Cohort Code *</span>
              <input
                type="text"
                value={code}
                onChange={(e) => setCode(e.target.value.toUpperCase())}
                className="h-9 px-3 rounded-xl border border-border bg-background text-sm font-mono focus:outline-none focus:border-primary"
              />
            </label>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">Start Date</span>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">End Date</span>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
              />
            </label>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">Location</span>
              <input
                type="text"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                placeholder="e.g. Innovation Center, Lab 3"
                className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">Capacity (Students)</span>
              <input
                type="number"
                min={1}
                value={capacity}
                onChange={(e) => setCapacity(e.target.value)}
                className={`h-9 px-3 rounded-xl border bg-background text-sm focus:outline-none ${
                  capacityQuotaExceeded ? "border-amber-500 focus:border-amber-500" : "border-border focus:border-primary"
                }`}
              />
              {capacityQuotaExceeded && (
                <span className="text-[11px] text-amber-600 dark:text-amber-400 font-medium">
                  Your organization limit is {cohort.org_capacity_limit} students per cohort.
                </span>
              )}
            </label>
          </div>

          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-muted-foreground">
              Custom Milestones Tab Label (Optional)
            </span>
            <input
              type="text"
              value={checklistTitleOverride}
              onChange={(e) => setChecklistTitleOverride(e.target.value)}
              placeholder="e.g. Competition Stages or Course Pathway"
              className="h-9 px-3 rounded-xl border border-border bg-background text-sm focus:outline-none focus:border-primary"
            />
          </label>

          <label className="flex items-start gap-2.5 p-3 rounded-xl border border-border bg-muted/20 cursor-pointer">
            <input
              type="checkbox"
              checked={isPublic}
              onChange={(e) => setIsPublic(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded text-primary focus:ring-primary border-border"
            />
            <div>
              <span className="text-xs font-semibold text-foreground block">
                List on Public Learning Catalog
              </span>
              <span className="text-[11px] text-muted-foreground block">
                Public cohorts appear on the public courses & learning catalog.
              </span>
            </div>
          </label>
        </div>

        <div className="flex items-center justify-end gap-2 pt-3 border-t border-border">
          <button
            type="button"
            onClick={onClose}
            className="h-9 px-4 rounded-xl border border-border text-xs font-medium hover:bg-muted transition"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!(name || "").trim() || !(code || "").trim() || capacityQuotaExceeded || mut.isPending}
            onClick={() => mut.mutate()}
            className="h-9 px-4 rounded-xl bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition disabled:opacity-50"
          >
            {mut.isPending ? "Saving..." : "Save Changes"}
          </button>
        </div>
      </div>
    </div>
  )
}

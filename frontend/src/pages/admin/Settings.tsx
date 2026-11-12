import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Save, Upload, CheckCircle2, Bot, Ban, GraduationCap, Briefcase } from "lucide-react"
import { getSettingsApi, upsertSettingApi, uploadAdminSignatureApi } from "@/api/admin/settings"
import { Spinner } from "@/pages/admin/components/common"
import { useToast } from "@/components/ui/toast"
import { Button } from "@/components/ui/button"

export default function Settings() {
  const qc = useQueryClient()
  const toast = useToast()
  const { data: settings, isLoading } = useQuery({ queryKey: ["admin-settings"], queryFn: getSettingsApi })
  
  const [signatoryName, setSignatoryName] = useState("")
  const [signatoryTitle, setSignatoryTitle] = useState("")
  const [minAge, setMinAge] = useState("18")
  const [phase1Days, setPhase1Days] = useState("7")
  const [presDays, setPresDays] = useState("3")
  const [assessDays, setAssessDays] = useState("3")
  const [revDays, setRevDays] = useState("3")
  const [extDays, setExtDays] = useState("1")
  const [timeoutDays, setTimeoutDays] = useState("10")
  const [internMinAge, setInternMinAge] = useState("18")
  const [loaded, setLoaded] = useState(false)
  const [savedName, setSavedName] = useState(false)
  const [savedTitle, setSavedTitle] = useState(false)

  if (settings && !loaded) {
    setSignatoryName(settings.admin_signatory_name ?? "")
    setSignatoryTitle(settings.admin_signatory_title ?? "")
    setMinAge(settings.instructor_intake_min_age ?? "18")
    setInternMinAge(settings.internship_intake_min_age ?? "18")
    setPhase1Days(settings.instructor_deadline_phase1_days ?? "7")
    setPresDays(settings.instructor_deadline_presentation_days ?? "3")
    setAssessDays(settings.instructor_deadline_assessment_days ?? "3")
    setRevDays(settings.instructor_deadline_revision_days ?? "3")
    setExtDays(settings.instructor_extension_days ?? "1")
    setTimeoutDays(settings.instructor_hard_timeout_days ?? "10")
    setLoaded(true)
  }

  const isFinEnabled = settings?.fin_support_enabled !== "false"
  const isIntakeEnabled = settings?.instructor_intake_enabled !== "false"
  const isRequireUniv = settings?.instructor_intake_require_university === "true"
  const isInternIntakeEnabled = settings?.internship_intake_enabled !== "false"
  const isInternRequireUniv = settings?.internship_intake_require_university !== "false"

  const toggleInternIntake = useMutation({
    mutationFn: (enabled: boolean) =>
      upsertSettingApi("internship_intake_enabled", enabled ? "true" : "false"),
    onSuccess: (_, enabled) => {
      qc.invalidateQueries({ queryKey: ["admin-settings"] })
      toast.success(enabled ? "Student internship intake enabled" : "Student internship intake disabled")
    },
    onError: () => toast.error("Failed to update internship intake toggle"),
  })

  const toggleInternRequireUniv = useMutation({
    mutationFn: (enabled: boolean) =>
      upsertSettingApi("internship_intake_require_university", enabled ? "true" : "false"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-settings"] })
      toast.success("Internship university requirement updated")
    },
    onError: () => toast.error("Failed to update setting"),
  })

  const saveInternMinAge = useMutation({
    mutationFn: () => upsertSettingApi("internship_intake_min_age", internMinAge),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-settings"] })
      toast.success("Internship minimum age saved")
    },
    onError: () => toast.error("Failed to save minimum age"),
  })

  const toggleIntake = useMutation({
    mutationFn: (enabled: boolean) =>
      upsertSettingApi("instructor_intake_enabled", enabled ? "true" : "false"),
    onSuccess: (_, enabled) => {
      qc.invalidateQueries({ queryKey: ["admin-settings"] })
      toast.success(enabled ? "Student instructor intake enabled" : "Student instructor intake disabled")
    },
    onError: () => toast.error("Failed to update intake toggle"),
  })

  const toggleRequireUniv = useMutation({
    mutationFn: (enabled: boolean) =>
      upsertSettingApi("instructor_intake_require_university", enabled ? "true" : "false"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-settings"] })
      toast.success("University requirement setting updated")
    },
    onError: () => toast.error("Failed to update setting"),
  })

  const saveDeadlines = useMutation({
    mutationFn: async () => {
      await upsertSettingApi("instructor_intake_min_age", minAge)
      await upsertSettingApi("instructor_deadline_phase1_days", phase1Days)
      await upsertSettingApi("instructor_deadline_presentation_days", presDays)
      await upsertSettingApi("instructor_deadline_assessment_days", assessDays)
      await upsertSettingApi("instructor_deadline_revision_days", revDays)
      await upsertSettingApi("instructor_extension_days", extDays)
      await upsertSettingApi("instructor_hard_timeout_days", timeoutDays)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-settings"] })
      toast.success("Instructor intake & deadlines saved successfully")
    },
    onError: () => toast.error("Failed to save deadline settings"),
  })

  const toggleFin = useMutation({
    mutationFn: (enabled: boolean) =>
      upsertSettingApi("fin_support_enabled", enabled ? "true" : "false"),
    onSuccess: (_, enabled) => {
      qc.invalidateQueries({ queryKey: ["admin-settings"] })
      qc.invalidateQueries({ queryKey: ["lms-support-config"] })
      toast.success(enabled ? "Fin support messenger enabled for students" : "Fin support messenger disabled for students")
    },
    onError: () => {
      toast.error("Failed to update Fin support setting")
    },
  })

  const saveSignatoryName = useMutation({
    mutationFn: () => upsertSettingApi("admin_signatory_name", signatoryName),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-settings"] })
      setSavedName(true)
      setTimeout(() => setSavedName(false), 2000)
    },
  })

  const saveSignatoryTitle = useMutation({
    mutationFn: () => upsertSettingApi("admin_signatory_title", signatoryTitle),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-settings"] })
      setSavedTitle(true)
      setTimeout(() => setSavedTitle(false), 2000)
    },
  })

  const uploadSignature = useMutation({
    mutationFn: (file: File) => uploadAdminSignatureApi(file),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-settings"] }),
    onError: (err: any) => {
      alert(err?.response?.data?.detail || "Failed to upload signature image")
    }
  })

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-6 max-w-xl">
      <div>
        <h1 className="text-xl font-bold text-foreground tracking-tight">System Settings</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Manage system-wide defaults, Fin student support assistant, and signatory configuration.
        </p>
      </div>

      <div className="flex flex-col gap-6">
        {/* Fin Student Support Assistant Card */}
        <div className="bg-card border border-border rounded-2xl p-6 shadow-sm flex flex-col gap-4">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary shrink-0 mt-0.5">
                <Bot size={20} />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-base font-semibold text-foreground">Fin Support Assistant (Intercom)</h2>
                  <span
                    className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold tracking-wide uppercase ${
                      isFinEnabled
                        ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20"
                        : "bg-muted text-muted-foreground border border-border"
                    }`}
                  >
                    {isFinEnabled ? "Active" : "Disabled"}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  Control whether Fin (the Intercom AI student support assistant) is visible to students on the learning platform (<code className="text-[11px] bg-muted px-1 py-0.5 rounded">/learn/*</code>).
                </p>
              </div>
            </div>

            <button
              type="button"
              disabled={toggleFin.isPending}
              onClick={() => toggleFin.mutate(!isFinEnabled)}
              className={`relative w-12 h-6 rounded-full transition-colors shrink-0 cursor-pointer ${
                isFinEnabled ? "bg-primary" : "bg-muted-foreground/30"
              }`}
              aria-label="Toggle Fin support assistant for students"
              aria-pressed={isFinEnabled}
            >
              <span
                className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${
                  isFinEnabled ? "translate-x-6" : ""
                }`}
              />
            </button>
          </div>

          <div className="text-[11px] text-muted-foreground bg-muted/40 rounded-xl p-3 border border-border/50">
            {isFinEnabled ? (
              <p className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400 font-medium">
                <CheckCircle2 size={13} />
                Students currently see the floating Fin launcher and can ask questions about missions, cohorts, and competitions.
              </p>
            ) : (
              <p className="flex items-center gap-1.5 text-muted-foreground font-medium">
                <Ban size={13} />
                Fin is completely turned off for students. No floating messenger or launcher widget is loaded on student pages.
              </p>
            )}
          </div>
        </div>

        {/* Instructor Intake & Pipeline Deadlines Card */}
        <div className="bg-card border border-border rounded-2xl p-6 shadow-sm flex flex-col gap-5">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary shrink-0 mt-0.5">
                <GraduationCap size={20} />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-base font-semibold text-foreground">Instructor Intake & Pipeline Deadlines</h2>
                  <span
                    className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold tracking-wide uppercase ${
                      isIntakeEnabled
                        ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20"
                        : "bg-muted text-muted-foreground border border-border"
                    }`}
                  >
                    {isIntakeEnabled ? "Intake Active" : "Intake Closed"}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  Configure eligibility criteria for student instructor applications, stage deadlines, and inactivity timeouts.
                </p>
              </div>
            </div>

            <button
              type="button"
              disabled={toggleIntake.isPending}
              onClick={() => toggleIntake.mutate(!isIntakeEnabled)}
              className={`relative w-12 h-6 rounded-full transition-colors shrink-0 cursor-pointer ${
                isIntakeEnabled ? "bg-primary" : "bg-muted-foreground/30"
              }`}
              aria-label="Toggle student instructor intake"
              aria-pressed={isIntakeEnabled}
            >
              <span
                className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${
                  isIntakeEnabled ? "translate-x-6" : ""
                }`}
              />
            </button>
          </div>

          <div className="flex flex-col gap-4 border-t border-border pt-4">
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              Student Eligibility Criteria
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="text-xs font-medium text-foreground block mb-1">
                  Minimum Age Requirement (Years)
                </label>
                <input
                  type="number"
                  min="16"
                  max="99"
                  className="input w-full"
                  value={minAge}
                  onChange={(e) => setMinAge(e.target.value)}
                />
                <p className="text-[11px] text-muted-foreground mt-1">
                  Students with no birthdate or under this age cannot see or access the application.
                </p>
              </div>

              <div className="flex flex-col justify-center">
                <div className="flex items-center justify-between gap-3 p-3 rounded-xl border border-border bg-muted/20">
                  <div>
                    <p className="text-xs font-medium text-foreground">Require University Affiliation</p>
                    <p className="text-[11px] text-muted-foreground">Only students with university / student ID can apply</p>
                  </div>
                  <button
                    type="button"
                    disabled={toggleRequireUniv.isPending}
                    onClick={() => toggleRequireUniv.mutate(!isRequireUniv)}
                    className={`relative w-10 h-5 rounded-full transition-colors shrink-0 cursor-pointer ${
                      isRequireUniv ? "bg-primary" : "bg-muted-foreground/30"
                    }`}
                  >
                    <span
                      className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${
                        isRequireUniv ? "translate-x-5" : ""
                      }`}
                    />
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div className="flex flex-col gap-4 border-t border-border pt-4">
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              Pipeline Stage Deadlines (Days)
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label className="text-xs font-medium text-foreground block mb-1">
                  Phase 1: Research (Videos & Modules)
                </label>
                <input
                  type="number"
                  min="1"
                  className="input w-full"
                  value={phase1Days}
                  onChange={(e) => setPhase1Days(e.target.value)}
                />
              </div>

              <div>
                <label className="text-xs font-medium text-foreground block mb-1">
                  Phase 2: Presentation Upload
                </label>
                <input
                  type="number"
                  min="1"
                  className="input w-full"
                  value={presDays}
                  onChange={(e) => setPresDays(e.target.value)}
                />
              </div>

              <div>
                <label className="text-xs font-medium text-foreground block mb-1">
                  Phase 2: 10-Question Test
                </label>
                <input
                  type="number"
                  min="1"
                  className="input w-full"
                  value={assessDays}
                  onChange={(e) => setAssessDays(e.target.value)}
                />
              </div>

              <div>
                <label className="text-xs font-medium text-foreground block mb-1">
                  Revisions / Fixes Requested
                </label>
                <input
                  type="number"
                  min="1"
                  className="input w-full"
                  value={revDays}
                  onChange={(e) => setRevDays(e.target.value)}
                />
              </div>

              <div>
                <label className="text-xs font-medium text-foreground block mb-1">
                  Self-Service Extension
                </label>
                <input
                  type="number"
                  min="1"
                  className="input w-full"
                  value={extDays}
                  onChange={(e) => setExtDays(e.target.value)}
                />
              </div>

              <div>
                <label className="text-xs font-medium text-foreground block mb-1">
                  Inactivity Auto-Reject Limit
                </label>
                <input
                  type="number"
                  min="1"
                  className="input w-full"
                  value={timeoutDays}
                  onChange={(e) => setTimeoutDays(e.target.value)}
                />
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <Button
                size="sm"
                onClick={() => saveDeadlines.mutate()}
                disabled={saveDeadlines.isPending}
                className="gap-1.5"
              >
                <Save size={14} />
                {saveDeadlines.isPending ? "Saving..." : "Save Intake & Deadlines"}
              </Button>
            </div>
          </div>
        </div>

        {/* Student Internship Intake Card */}
        <div className="bg-card border border-border rounded-2xl p-6 shadow-sm flex flex-col gap-5">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary shrink-0 mt-0.5">
                <Briefcase size={20} />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-base font-semibold text-foreground">Student Internship Intake</h2>
                  <span
                    className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold tracking-wide uppercase ${
                      isInternIntakeEnabled
                        ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20"
                        : "bg-muted text-muted-foreground border border-border"
                    }`}
                  >
                    {isInternIntakeEnabled ? "Intake Active" : "Intake Closed"}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  Control whether university students can apply for an internship directly from their LMS profile.
                </p>
              </div>
            </div>

            <button
              type="button"
              disabled={toggleInternIntake.isPending}
              onClick={() => toggleInternIntake.mutate(!isInternIntakeEnabled)}
              className={`relative w-12 h-6 rounded-full transition-colors shrink-0 cursor-pointer ${
                isInternIntakeEnabled ? "bg-primary" : "bg-muted-foreground/30"
              }`}
              aria-label="Toggle student internship intake"
              aria-pressed={isInternIntakeEnabled}
            >
              <span
                className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${
                  isInternIntakeEnabled ? "translate-x-6" : ""
                }`}
              />
            </button>
          </div>

          <div className="flex flex-col gap-4 border-t border-border pt-4">
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              Student Eligibility Criteria
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="text-xs font-medium text-foreground block mb-1">
                  Minimum Age Requirement (Years)
                </label>
                <div className="flex gap-2">
                  <input
                    type="number"
                    min="16"
                    max="99"
                    className="input w-full"
                    value={internMinAge}
                    onChange={(e) => setInternMinAge(e.target.value)}
                  />
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => saveInternMinAge.mutate()}
                    disabled={saveInternMinAge.isPending}
                    className="shrink-0 gap-1.5"
                  >
                    <Save size={14} />
                    {saveInternMinAge.isPending ? "Saving..." : "Save"}
                  </Button>
                </div>
                <p className="text-[11px] text-muted-foreground mt-1">
                  Students with no birthdate or under this age cannot see or access the internship application button.
                </p>
              </div>

              <div className="flex flex-col justify-center">
                <div className="flex items-center justify-between gap-3 p-3 rounded-xl border border-border bg-muted/20">
                  <div>
                    <p className="text-xs font-medium text-foreground">Require University Affiliation</p>
                    <p className="text-[11px] text-muted-foreground">Require university name and student ID in the application</p>
                  </div>
                  <button
                    type="button"
                    disabled={toggleInternRequireUniv.isPending}
                    onClick={() => toggleInternRequireUniv.mutate(!isInternRequireUniv)}
                    className={`relative w-10 h-5 rounded-full transition-colors shrink-0 cursor-pointer ${
                      isInternRequireUniv ? "bg-primary" : "bg-muted-foreground/30"
                    }`}
                  >
                    <span
                      className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${
                        isInternRequireUniv ? "translate-x-5" : ""
                      }`}
                    />
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Signatory Defaults Card */}
        <div className="bg-card border border-border rounded-2xl p-6 shadow-sm flex flex-col gap-5">
          <div>
            <h2 className="text-base font-semibold text-foreground">Signatory Defaults</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              These details are used as signatory information for certificates and letters across the platform.
            </p>
          </div>

          <div className="flex flex-col gap-4 border-b border-border pb-5">
            <div>
              <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1.5 block">
                Signatory Name
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={signatoryName}
                  onChange={(e) => setSignatoryName(e.target.value)}
                  placeholder="e.g. John Doe"
                  className="flex-1 h-10 px-3 bg-background border border-border rounded-xl text-sm focus:outline-none focus:border-primary text-foreground"
                />
                <button
                  onClick={() => saveSignatoryName.mutate()}
                  disabled={saveSignatoryName.isPending}
                  className="h-10 px-4 bg-primary text-primary-foreground font-semibold text-sm rounded-xl hover:opacity-90 transition-opacity flex items-center gap-1.5"
                >
                  <Save size={14} />
                  Save
                </button>
              </div>
              {savedName && (
                <p className="text-xs text-emerald-600 dark:text-emerald-400 mt-1 flex items-center gap-1">
                  <CheckCircle2 size={12} /> Signatory name saved
                </p>
              )}
            </div>

            <div>
              <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1.5 block">
                Signatory Title
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={signatoryTitle}
                  onChange={(e) => setSignatoryTitle(e.target.value)}
                  placeholder="e.g. Managing Director"
                  className="flex-1 h-10 px-3 bg-background border border-border rounded-xl text-sm focus:outline-none focus:border-primary text-foreground"
                />
                <button
                  onClick={() => saveSignatoryTitle.mutate()}
                  disabled={saveSignatoryTitle.isPending}
                  className="h-10 px-4 bg-primary text-primary-foreground font-semibold text-sm rounded-xl hover:opacity-90 transition-opacity flex items-center gap-1.5"
                >
                  <Save size={14} />
                  Save
                </button>
              </div>
              {savedTitle && (
                <p className="text-xs text-emerald-600 dark:text-emerald-400 mt-1 flex items-center gap-1">
                  <CheckCircle2 size={12} /> Signatory title saved
                </p>
              )}
            </div>
          </div>

          <div>
            <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2 block">
              Signature Image
            </label>
            <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
              <div className="relative overflow-hidden rounded-xl border border-border bg-muted/30 p-2 flex items-center justify-center min-h-[64px] min-w-[128px]">
                {settings?.admin_signature_url ? (
                  <img
                    src={settings.admin_signature_url}
                    alt="Current signature"
                    className="max-h-12 max-w-[200px] object-contain dark:invert"
                  />
                ) : (
                  <span className="text-xs text-muted-foreground italic">No signature uploaded</span>
                )}
              </div>
              
              <div className="flex flex-col gap-1.5">
                <label className="relative cursor-pointer h-9 px-4 bg-secondary text-secondary-foreground font-semibold text-xs rounded-xl hover:opacity-90 transition-opacity flex items-center gap-1.5 w-fit">
                  <Upload size={14} />
                  {uploadSignature.isPending ? "Uploading..." : "Upload Image"}
                  <input
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={(e) => {
                      const file = e.target.files?.[0]
                      if (file) uploadSignature.mutate(file)
                    }}
                  />
                </label>
                <p className="text-[10px] text-muted-foreground">
                  Supported formats: PNG, JPG, SVG. Transparent background recommended.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

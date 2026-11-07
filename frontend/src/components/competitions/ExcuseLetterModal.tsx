import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { FileText, Download, Check, Save, Eye } from "lucide-react"
import {
  getCohortExcuseLetterTemplateApi,
  updateCohortExcuseLetterTemplateApi,
  downloadCustomTeamExcuseLetterApi,
  downloadExcuseLetterPreviewApi,
  type ExcuseLetterConfig,
} from "@/api/competitions"
import { getCohortApi } from "@/api/sessions/cohorts"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { useToast } from "@/components/ui/toast"

const DEFAULT_DESCRIPTION =
  "The student has been selected as part of the finalist teams representing top talent across the region. This hands-on experience includes presenting their prototype, engaging with industry experts, and attending key technical sessions, offering an unparalleled educational and professional development opportunity in aerospace engineering and innovation."

interface ExcuseLetterModalProps {
  cohortId: string
  open: boolean
  onClose: () => void
  // If provided, we are downloading for a specific team
  team?: { id: string; name: string } | null
  // If provided, we are confirming advance of multiple teams
  advanceContext?: {
    toCohortId: string
    toCohortName: string
    teamCount: number
    onConfirm: (options: {
      mode: "team" | "individual" | "both"
      overrides: ExcuseLetterConfig
      saveAsDefault: boolean
    }) => void
    isPending?: boolean
  } | null
}

export function ExcuseLetterModal({
  cohortId,
  open,
  onClose,
  team,
  advanceContext,
}: ExcuseLetterModalProps) {
  const toast = useToast()
  const queryClient = useQueryClient()

  // Fetch resolved defaults for the cohort
  const effectiveCohortId = advanceContext?.toCohortId || cohortId
  const { data: template, isLoading: isTemplateLoading } = useQuery({
    queryKey: ["competitions-excuse-template", effectiveCohortId],
    queryFn: () => getCohortExcuseLetterTemplateApi(effectiveCohortId),
    enabled: open && !!effectiveCohortId,
  })

  const { data: cohortData, isLoading: isCohortLoading } = useQuery({
    queryKey: ["cohort-detail", effectiveCohortId],
    queryFn: () => getCohortApi(effectiveCohortId),
    enabled: open && !!effectiveCohortId,
  })

  const isLoading = isTemplateLoading && isCohortLoading

  const [enabled, setEnabled] = useState(false)
  const [eventName, setEventName] = useState("")
  const [organizer, setOrganizer] = useState("SpacePoint")
  const [datesText, setDatesText] = useState("")
  const [locationText, setLocationText] = useState("")
  const [studentRole, setStudentRole] = useState("Finalist — Technical Demonstration & Presentation")
  const [participationMode, setParticipationMode] = useState("On-site Exhibition & Technical Demonstration")
  const [descriptionText, setDescriptionText] = useState(DEFAULT_DESCRIPTION)
  const [committeeName, setCommitteeName] = useState("SpacePoint")
  const [contactEmail, setContactEmail] = useState("info@spacepoint.ae")
  const [contactPhone, setContactPhone] = useState("+971562987005")
  const [contactWebsite, setContactWebsite] = useState("www.spacepoint.ae")

  // Generation / Attachment version mode
  const [letterVersion, setLetterVersion] = useState<"team" | "individual" | "both">(
    advanceContext ? "team" : "team"
  )
  const [saveAsDefault, setSaveAsDefault] = useState(false)
  const [isDownloading, setIsDownloading] = useState(false)
  const [isPreviewing, setIsPreviewing] = useState(false)

  useEffect(() => {
    let defDates = ""
    if (cohortData?.starts_on && cohortData?.ends_on) {
      const s = new Date(cohortData.starts_on)
      const e = new Date(cohortData.ends_on)
      const days = Math.round((e.getTime() - s.getTime()) / (1000 * 60 * 60 * 24)) + 1
      defDates = `${cohortData.starts_on} – ${cohortData.ends_on} (all ${days} days)`
    } else if (cohortData?.starts_on) {
      defDates = `${cohortData.starts_on}`
    } else {
      defDates = "Competition On-site Showcase Period"
    }

    const resolvedEventName = template?.event_name || cohortData?.name || ""
    const resolvedDates = template?.dates_text || defDates
    const resolvedLocation = template?.location_text || cohortData?.location || "Dubai, United Arab Emirates"
    const resolvedDesc = template?.description_text || DEFAULT_DESCRIPTION

    if (template?.enabled !== undefined) {
      setEnabled(template.enabled)
    } else {
      // Default to enabled if template exists or when admin configures it
      setEnabled(true)
    }

    if (resolvedEventName) setEventName(resolvedEventName)
    if (template?.organizer) setOrganizer(template.organizer)
    if (resolvedDates) setDatesText(resolvedDates)
    if (resolvedLocation) setLocationText(resolvedLocation)
    if (template?.student_role) setStudentRole(template.student_role)
    if (template?.participation_mode) setParticipationMode(template.participation_mode)
    if (resolvedDesc) setDescriptionText(resolvedDesc)
    if (template?.committee_name) setCommitteeName(template.committee_name)
    if (template?.contact_email) setContactEmail(template.contact_email)
    if (template?.contact_phone) setContactPhone(template.contact_phone)
    if (template?.contact_website) setContactWebsite(template.contact_website)
  }, [template, cohortData])

  const saveMutation = useMutation({
    mutationFn: (data: ExcuseLetterConfig) => updateCohortExcuseLetterTemplateApi(effectiveCohortId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["competitions-excuse-template", effectiveCohortId] })
      toast.success("Excuse letter template saved as cohort default")
    },
    onError: () => {
      toast.error("Failed to save template defaults")
    },
  })

  if (!open) return null

  const getPayload = (): ExcuseLetterConfig => ({
    enabled,
    event_name: eventName.trim() || undefined,
    organizer: organizer.trim() || "SpacePoint",
    dates_text: datesText.trim() || undefined,
    location_text: locationText.trim() || undefined,
    student_role: studentRole.trim() || undefined,
    participation_mode: participationMode.trim() || undefined,
    description_text: descriptionText.trim() || undefined,
    committee_name: committeeName.trim() || "SpacePoint",
    contact_email: contactEmail.trim() || undefined,
    contact_phone: contactPhone.trim() || undefined,
    contact_website: contactWebsite.trim() || undefined,
  })

  const handleDownload = async () => {
    if (!team) return
    setIsDownloading(true)
    try {
      const payload = getPayload()
      const blob = await downloadCustomTeamExcuseLetterApi(
        cohortId,
        team.id,
        payload,
        undefined,
        saveAsDefault
      )
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      const cleanName = team.name.replace(/[^a-zA-Z0-9_-]/g, "_")
      a.download = `${cleanName}_University_Excuse_Letter.pdf`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      toast.success("Letter downloaded successfully")
      onClose()
    } catch {
      toast.error("Failed to generate and download excuse letter")
    } finally {
      setIsDownloading(false)
    }
  }

  const handleAdvanceConfirm = () => {
    if (!advanceContext) return
    advanceContext.onConfirm({
      mode: letterVersion,
      overrides: getPayload(),
      saveAsDefault,
    })
  }

  const handleSaveDefaultsOnly = () => {
    saveMutation.mutate(getPayload())
  }

  const handleDownloadPreview = async () => {
    setIsPreviewing(true)
    try {
      const payload = getPayload()
      const blob = await downloadExcuseLetterPreviewApi(
        effectiveCohortId,
        payload,
        team?.id,
      )
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = "Excuse_Letter_Preview.pdf"
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      toast.success("Preview PDF downloaded")
    } catch {
      toast.error("Failed to generate preview PDF")
    } finally {
      setIsPreviewing(false)
    }
  }

  const isAdvance = !!advanceContext

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-lg">
            <FileText className="text-primary" size={20} />
            <span>
              {isAdvance
                ? `Attach Excuse Letter — Advance ${advanceContext.teamCount} Team(s)`
                : team
                ? `University Excuse Letter — ${team.name}`
                : "Configure Excuse Letter Template"}
            </span>
          </DialogTitle>
          <p className="text-xs text-muted-foreground">
            {isAdvance
              ? `Review the invitation and excuse letter wording before attaching it to the congratulations email for the ${advanceContext.teamCount} team(s) advancing to ${advanceContext.toCohortName}.`
              : "Review and customize the letter text below before downloading. Wording can be tailored and saved as the cohort default."}
          </p>
        </DialogHeader>

        {isLoading ? (
          <div className="py-8 text-center text-sm text-muted-foreground">Loading template defaults…</div>
        ) : (
          <div className="space-y-4 pt-2">
            {/* Cohort Letter Enabled Status */}
            <div className="flex items-center justify-between p-3 rounded-xl border border-border bg-card">
              <div>
                <div className="text-xs font-semibold text-foreground">
                  Enable Invitation Letters for this Cohort
                </div>
                <div className="text-[11px] text-muted-foreground">
                  When active, students in this cohort can download individual & team invitation letters from their LMS checklist.
                </div>
              </div>
              <label className="relative inline-flex items-center cursor-pointer shrink-0 ml-3">
                <input
                  type="checkbox"
                  checked={enabled}
                  onChange={(e) => setEnabled(e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-9 h-5 bg-muted peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-primary"></div>
              </label>
            </div>

            {/* Version selection if advancing */}
            {isAdvance && (
              <div className="p-3 bg-muted/40 rounded-xl border border-border space-y-2">
                <label className="text-xs font-semibold text-foreground block">
                  Letter Version(s) to Attach to Student Email:
                </label>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                  <button
                    type="button"
                    onClick={() => setLetterVersion("team")}
                    className={`flex items-center gap-2 p-2.5 rounded-lg border text-xs font-medium text-left transition cursor-pointer ${
                      letterVersion === "team"
                        ? "bg-primary/10 border-primary text-primary"
                        : "bg-card border-border text-foreground hover:bg-muted"
                    }`}
                  >
                    <input
                      type="radio"
                      checked={letterVersion === "team"}
                      onChange={() => setLetterVersion("team")}
                      className="cursor-pointer"
                    />
                    <div>
                      <div className="font-semibold">Team Roster</div>
                      <div className="text-[11px] text-muted-foreground">One letter with all team members</div>
                    </div>
                  </button>

                  <button
                    type="button"
                    onClick={() => setLetterVersion("individual")}
                    className={`flex items-center gap-2 p-2.5 rounded-lg border text-xs font-medium text-left transition cursor-pointer ${
                      letterVersion === "individual"
                        ? "bg-primary/10 border-primary text-primary"
                        : "bg-card border-border text-foreground hover:bg-muted"
                    }`}
                  >
                    <input
                      type="radio"
                      checked={letterVersion === "individual"}
                      onChange={() => setLetterVersion("individual")}
                      className="cursor-pointer"
                    />
                    <div>
                      <div className="font-semibold">Individual</div>
                      <div className="text-[11px] text-muted-foreground">Personalized to each student</div>
                    </div>
                  </button>

                  <button
                    type="button"
                    onClick={() => setLetterVersion("both")}
                    className={`flex items-center gap-2 p-2.5 rounded-lg border text-xs font-medium text-left transition cursor-pointer ${
                      letterVersion === "both"
                        ? "bg-primary/10 border-primary text-primary"
                        : "bg-card border-border text-foreground hover:bg-muted"
                    }`}
                  >
                    <input
                      type="radio"
                      checked={letterVersion === "both"}
                      onChange={() => setLetterVersion("both")}
                      className="cursor-pointer"
                    />
                    <div>
                      <div className="font-semibold">Both (Team + Indiv.)</div>
                      <div className="text-[11px] text-muted-foreground">Attaches both PDF copies</div>
                    </div>
                  </button>
                </div>
              </div>
            )}

            {/* Core Event & Letter Details */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1">
                  Event / Challenge Name
                </label>
                <input
                  type="text"
                  value={eventName}
                  onChange={(e) => setEventName(e.target.value)}
                  placeholder="e.g. PlanetX Aerospace Challenge"
                  className="w-full h-9 px-3 rounded-lg border border-border bg-card text-foreground text-xs focus:outline-none focus:border-primary"
                />
              </div>

              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1">
                  Organizer (Add partner if applicable)
                </label>
                <input
                  type="text"
                  value={organizer}
                  onChange={(e) => setOrganizer(e.target.value)}
                  placeholder="SpacePoint (or SpacePoint in collaboration with...)"
                  className="w-full h-9 px-3 rounded-lg border border-border bg-card text-foreground text-xs focus:outline-none focus:border-primary"
                />
              </div>

              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1">
                  Dates & Duration
                </label>
                <input
                  type="text"
                  value={datesText}
                  onChange={(e) => setDatesText(e.target.value)}
                  placeholder="e.g. 15 November 2026 – 19 November 2026 (all 5 days)"
                  className="w-full h-9 px-3 rounded-lg border border-border bg-card text-foreground text-xs focus:outline-none focus:border-primary"
                />
              </div>

              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1">
                  Location / Venue
                </label>
                <input
                  type="text"
                  value={locationText}
                  onChange={(e) => setLocationText(e.target.value)}
                  placeholder="e.g. Dubai Airshow Site, Dubai, UAE"
                  className="w-full h-9 px-3 rounded-lg border border-border bg-card text-foreground text-xs focus:outline-none focus:border-primary"
                />
              </div>

              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1">
                  Student Role
                </label>
                <input
                  type="text"
                  value={studentRole}
                  onChange={(e) => setStudentRole(e.target.value)}
                  placeholder="e.g. Finalist — Technical Demonstration & Presentation"
                  className="w-full h-9 px-3 rounded-lg border border-border bg-card text-foreground text-xs focus:outline-none focus:border-primary"
                />
              </div>

              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1">
                  Participation Mode
                </label>
                <input
                  type="text"
                  value={participationMode}
                  onChange={(e) => setParticipationMode(e.target.value)}
                  placeholder="e.g. On-site Exhibition & Technical Demonstration"
                  className="w-full h-9 px-3 rounded-lg border border-border bg-card text-foreground text-xs focus:outline-none focus:border-primary"
                />
              </div>
            </div>

            <div>
              <label className="text-xs font-medium text-muted-foreground block mb-1">
                Context / Educational Description
              </label>
              <textarea
                value={descriptionText}
                onChange={(e) => setDescriptionText(e.target.value)}
                rows={3}
                placeholder="The student has been selected as part of the finalist teams representing top talent across the region. This hands-on experience includes presenting their prototype..."
                className="w-full p-2.5 rounded-lg border border-border bg-card text-foreground text-xs focus:outline-none focus:border-primary resize-none"
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1">
                  Sign-off / Committee Name
                </label>
                <input
                  type="text"
                  value={committeeName}
                  onChange={(e) => setCommitteeName(e.target.value)}
                  placeholder="SpacePoint"
                  className="w-full h-9 px-3 rounded-lg border border-border bg-card text-foreground text-xs focus:outline-none focus:border-primary"
                />
              </div>

              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1">
                  Contact Email
                </label>
                <input
                  type="email"
                  value={contactEmail}
                  onChange={(e) => setContactEmail(e.target.value)}
                  placeholder="info@spacepoint.ae"
                  className="w-full h-9 px-3 rounded-lg border border-border bg-card text-foreground text-xs focus:outline-none focus:border-primary"
                />
              </div>

              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1">
                  Contact Phone
                </label>
                <input
                  type="text"
                  value={contactPhone}
                  onChange={(e) => setContactPhone(e.target.value)}
                  placeholder="+971562987005"
                  className="w-full h-9 px-3 rounded-lg border border-border bg-card text-foreground text-xs focus:outline-none focus:border-primary"
                />
              </div>

              <div>
                <label className="text-xs font-medium text-muted-foreground block mb-1">
                  Website
                </label>
                <input
                  type="text"
                  value={contactWebsite}
                  onChange={(e) => setContactWebsite(e.target.value)}
                  placeholder="www.spacepoint.ae"
                  className="w-full h-9 px-3 rounded-lg border border-border bg-card text-foreground text-xs focus:outline-none focus:border-primary"
                />
              </div>
            </div>

            {/* If downloading for a team or advancing, optional checkbox to also update default template */}
            {(team || isAdvance) && (
              <div className="pt-2 border-t border-border">
                <label className="flex items-center gap-2 text-xs text-foreground cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={saveAsDefault}
                    onChange={(e) => setSaveAsDefault(e.target.checked)}
                    className="rounded border-border text-primary cursor-pointer"
                  />
                  <span>Save these changes as default template for this cohort</span>
                </label>
              </div>
            )}

            {/* Action buttons */}
            <div className="flex items-center justify-between gap-2 pt-3 border-t border-border">
              <button
                type="button"
                onClick={handleDownloadPreview}
                disabled={isPreviewing}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-medium border border-border bg-card hover:bg-muted text-foreground transition cursor-pointer disabled:opacity-50"
                title="Download a PDF preview with current settings"
              >
                <Eye size={14} className="text-primary" />
                <span>{isPreviewing ? "Generating…" : "Download Preview"}</span>
              </button>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2 rounded-xl text-xs font-medium border border-border text-muted-foreground hover:text-foreground hover:bg-muted transition cursor-pointer"
                >
                  Cancel
                </button>

                {isAdvance ? (
                  <button
                    type="button"
                    onClick={handleAdvanceConfirm}
                    disabled={advanceContext.isPending}
                    className="inline-flex items-center gap-1.5 px-5 py-2 bg-primary text-primary-foreground rounded-xl text-xs font-semibold hover:opacity-90 transition cursor-pointer disabled:opacity-50"
                  >
                    <Check size={14} />
                    <span>
                      {advanceContext.isPending
                        ? "Advancing & Sending…"
                        : `Confirm & Advance (${advanceContext.teamCount} Teams)`}
                    </span>
                  </button>
                ) : team ? (
                  <button
                    type="button"
                    onClick={handleDownload}
                    disabled={isDownloading}
                    className="inline-flex items-center gap-1.5 px-5 py-2 bg-primary text-primary-foreground rounded-xl text-xs font-semibold hover:opacity-90 transition cursor-pointer disabled:opacity-50"
                  >
                    <Download size={14} />
                    <span>{isDownloading ? "Generating PDF…" : "Download Letter PDF"}</span>
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={handleSaveDefaultsOnly}
                    disabled={saveMutation.isPending}
                    className="inline-flex items-center gap-1.5 px-5 py-2 bg-primary text-primary-foreground rounded-xl text-xs font-semibold hover:opacity-90 transition cursor-pointer disabled:opacity-50"
                  >
                    <Save size={14} />
                    <span>{saveMutation.isPending ? "Saving…" : "Save Template Defaults"}</span>
                  </button>
                )}
              </div>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

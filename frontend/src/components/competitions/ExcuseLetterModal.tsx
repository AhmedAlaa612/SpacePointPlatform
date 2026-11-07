import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { FileText, Download, Check, Save, Eye, Plus, Trash2, ArrowUp, ArrowDown } from "lucide-react"
import {
  getCohortExcuseLetterTemplateApi,
  updateCohortExcuseLetterTemplateApi,
  downloadCustomTeamExcuseLetterApi,
  downloadExcuseLetterPreviewApi,
  type ExcuseLetterConfig,
  type SignoffEntity,
} from "@/api/competitions"
import { getCohortApi } from "@/api/sessions/cohorts"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { useToast } from "@/components/ui/toast"

const DEFAULT_INVITATION_TEXT =
  "We are pleased to formally invite {student_name} {institution} to represent their team ({team_name}) as finalists in the {event_name}, organized by {organizer}. This prestigious competition will culminate in a live showcase at {location_text}."

const DEFAULT_SIGNOFF_ENTITIES: SignoffEntity[] = [
  {
    name: "SpacePoint",
    contacts: "info@spacepoint.ae | +971562987005",
    website: "www.spacepoint.ae",
  },
]

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
  const [invitationText, setInvitationText] = useState(DEFAULT_INVITATION_TEXT)
  const [eventName, setEventName] = useState("")
  const [organizer, setOrganizer] = useState("SpacePoint")
  const [datesText, setDatesText] = useState("")
  const [locationText, setLocationText] = useState("")
  const [studentRole, setStudentRole] = useState("Finalist — Technical Demonstration & Presentation")
  const [participationMode, setParticipationMode] = useState("On-site Exhibition & Technical Demonstration")
  const [descriptionText, setDescriptionText] = useState(DEFAULT_DESCRIPTION)
  const [signoffEntities, setSignoffEntities] = useState<SignoffEntity[]>(DEFAULT_SIGNOFF_ENTITIES)
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
    const resolvedInvitation = template?.invitation_text || DEFAULT_INVITATION_TEXT

    if (template?.enabled !== undefined) {
      setEnabled(template.enabled)
    } else {
      // Default to enabled if template exists or when admin configures it
      setEnabled(true)
    }

    if (resolvedInvitation) setInvitationText(resolvedInvitation)
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

    if (template?.signoff_entities && template.signoff_entities.length > 0) {
      setSignoffEntities(template.signoff_entities)
    } else if (template?.committee_name) {
      const parts = [template.contact_email, template.contact_phone].filter(Boolean)
      setSignoffEntities([
        {
          name: template.committee_name || "SpacePoint",
          contacts: parts.join(" | ") || "info@spacepoint.ae | +971562987005",
          website: template.contact_website || "www.spacepoint.ae",
        },
      ])
    } else {
      setSignoffEntities(DEFAULT_SIGNOFF_ENTITIES)
    }
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

  const handleAddEntity = () => {
    setSignoffEntities((prev) => [
      ...prev,
      { name: "", contacts: "", website: "" },
    ])
  }

  const handleUpdateEntity = (index: number, field: keyof SignoffEntity, val: string) => {
    setSignoffEntities((prev) =>
      prev.map((ent, i) => (i === index ? { ...ent, [field]: val } : ent))
    )
  }

  const handleRemoveEntity = (index: number) => {
    setSignoffEntities((prev) => prev.filter((_, i) => i !== index))
  }

  const handleMoveUp = (index: number) => {
    if (index === 0) return
    setSignoffEntities((prev) => {
      const copy = [...prev]
      const temp = copy[index - 1]
      copy[index - 1] = copy[index]
      copy[index] = temp
      return copy
    })
  }

  const handleMoveDown = (index: number) => {
    setSignoffEntities((prev) => {
      if (index >= prev.length - 1) return prev
      const copy = [...prev]
      const temp = copy[index + 1]
      copy[index + 1] = copy[index]
      copy[index] = temp
      return copy
    })
  }

  const handleAddSpacePoint = () => {
    setSignoffEntities((prev) => [
      ...prev,
      {
        name: "SpacePoint",
        contacts: "info@spacepoint.ae | +971562987005",
        website: "www.spacepoint.ae",
      },
    ])
  }

  const getPayload = (): ExcuseLetterConfig => {
    const validEntities = signoffEntities
      .map((e) => ({
        name: e.name.trim(),
        contacts: e.contacts?.trim() || undefined,
        website: e.website?.trim() || undefined,
      }))
      .filter((e) => e.name !== "")

    const finalEntities = validEntities.length > 0 ? validEntities : DEFAULT_SIGNOFF_ENTITIES

    return {
      enabled,
      invitation_text: invitationText.trim() || undefined,
      event_name: eventName.trim() || undefined,
      organizer: organizer.trim() || "SpacePoint",
      dates_text: datesText.trim() || undefined,
      location_text: locationText.trim() || undefined,
      student_role: studentRole.trim() || undefined,
      participation_mode: participationMode.trim() || undefined,
      description_text: descriptionText.trim() || undefined,
      signoff_entities: finalEntities,
      committee_name: finalEntities[0]?.name || "SpacePoint",
      contact_email: contactEmail.trim() || undefined,
      contact_phone: contactPhone.trim() || undefined,
      contact_website: contactWebsite.trim() || undefined,
    }
  }

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

            {/* Opening Invitation Paragraph (Above Roster Table) */}
            <div className="p-3.5 rounded-xl border border-border bg-card/60 space-y-2">
              <div className="flex items-center justify-between">
                <div>
                  <label className="text-xs font-semibold text-foreground block">
                    Invitation Opening Text (Above Table)
                  </label>
                  <p className="text-[11px] text-muted-foreground">
                    This text introduces the team/student directly above the roster table. Variables below will replace the placeholders.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setInvitationText(DEFAULT_INVITATION_TEXT)}
                  className="text-[11px] text-primary hover:underline font-medium cursor-pointer shrink-0 ml-2"
                >
                  Reset Text
                </button>
              </div>

              <textarea
                value={invitationText}
                onChange={(e) => setInvitationText(e.target.value)}
                rows={3}
                className="w-full p-2.5 rounded-lg border border-border bg-card text-foreground text-xs leading-relaxed focus:outline-none focus:border-primary resize-y"
                placeholder="e.g. We are pleased to formally invite {student_name} {institution} to represent their team ({team_name})..."
              />

              <div className="flex flex-wrap items-center gap-1.5 pt-1">
                <span className="text-[10px] text-muted-foreground font-medium mr-1">Insert Placeholders:</span>
                {[
                  { tag: "{student_name}", desc: "Student Name or 'the below-mentioned student(s)'" },
                  { tag: "{team_name}", desc: "Team Name" },
                  { tag: "{event_name}", desc: "Event Name" },
                  { tag: "{organizer}", desc: "Organizer" },
                  { tag: "{location_text}", desc: "Location / Venue" },
                  { tag: "{institution}", desc: "from [University] / from your esteemed institution" },
                  { tag: "{dates_text}", desc: "Dates & Duration" },
                ].map((item) => (
                  <button
                    key={item.tag}
                    type="button"
                    title={item.desc}
                    onClick={() =>
                      setInvitationText((prev) => (prev ? `${prev} ${item.tag}` : item.tag))
                    }
                    className="inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-mono font-medium bg-primary/10 text-primary border border-primary/20 hover:bg-primary/20 transition cursor-pointer"
                  >
                    {item.tag}
                  </button>
                ))}
              </div>
            </div>

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

            {/* Sign-off & Contact Entities (Footer) */}
            <div className="p-3.5 rounded-xl border border-border bg-card/60 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <label className="text-xs font-semibold text-foreground block">
                    Sign-off Entities (Letter Footer)
                  </label>
                  <p className="text-[11px] text-muted-foreground">
                    Add one or more organizing bodies. Each entity can have its own contact line and website. SpacePoint is included by default.
                  </p>
                </div>
                <div className="flex items-center gap-1.5 shrink-0 ml-2">
                  <button
                    type="button"
                    onClick={handleAddEntity}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-primary/30 bg-primary/10 text-primary text-xs font-medium hover:bg-primary/20 transition cursor-pointer"
                  >
                    <Plus size={13} />
                    <span>Add Entity</span>
                  </button>
                </div>
              </div>

              <div className="space-y-3">
                {signoffEntities.map((entity, idx) => (
                  <div
                    key={idx}
                    className="p-3 rounded-lg border border-border/80 bg-background/50 space-y-2.5 relative group"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                        Entity #{idx + 1} {entity.name === "SpacePoint" && "(Default)"}
                      </span>
                      <div className="flex items-center gap-1">
                        {idx > 0 && (
                          <button
                            type="button"
                            onClick={() => handleMoveUp(idx)}
                            className="text-muted-foreground hover:text-foreground transition p-1 cursor-pointer"
                            title="Move Up"
                          >
                            <ArrowUp size={13} />
                          </button>
                        )}
                        {idx < signoffEntities.length - 1 && (
                          <button
                            type="button"
                            onClick={() => handleMoveDown(idx)}
                            className="text-muted-foreground hover:text-foreground transition p-1 cursor-pointer"
                            title="Move Down"
                          >
                            <ArrowDown size={13} />
                          </button>
                        )}
                        {signoffEntities.length > 1 && (
                          <button
                            type="button"
                            onClick={() => handleRemoveEntity(idx)}
                            className="text-muted-foreground hover:text-destructive transition p-1 cursor-pointer"
                            title="Remove this entity"
                          >
                            <Trash2 size={13} />
                          </button>
                        )}
                      </div>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                      <div>
                        <label className="text-[11px] font-medium text-muted-foreground block mb-1">
                          Entity / Organizing Body Name
                        </label>
                        <input
                          type="text"
                          value={entity.name}
                          onChange={(e) => handleUpdateEntity(idx, "name", e.target.value)}
                          placeholder="e.g. PlanetX Organizing Committee"
                          className="w-full h-8 px-2.5 rounded-md border border-border bg-card text-foreground text-xs focus:outline-none focus:border-primary"
                        />
                      </div>

                      <div>
                        <label className="text-[11px] font-medium text-muted-foreground block mb-1">
                          Contacts Line <span className="text-[10px] text-muted-foreground/80">(Email | Phone)</span>
                        </label>
                        <input
                          type="text"
                          value={entity.contacts || ""}
                          onChange={(e) => handleUpdateEntity(idx, "contacts", e.target.value)}
                          placeholder="info@spacepoint.ae | +971562987005"
                          className="w-full h-8 px-2.5 rounded-md border border-border bg-card text-foreground text-xs focus:outline-none focus:border-primary"
                        />
                      </div>

                      <div>
                        <label className="text-[11px] font-medium text-muted-foreground block mb-1">
                          Website Line
                        </label>
                        <input
                          type="text"
                          value={entity.website || ""}
                          onChange={(e) => handleUpdateEntity(idx, "website", e.target.value)}
                          placeholder="www.spacepoint.ae"
                          className="w-full h-8 px-2.5 rounded-md border border-border bg-card text-foreground text-xs focus:outline-none focus:border-primary"
                        />
                      </div>
                    </div>
                  </div>
                ))}
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

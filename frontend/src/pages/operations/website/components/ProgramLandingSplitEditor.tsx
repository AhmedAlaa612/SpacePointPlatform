import { useEffect, useMemo, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  ArrowLeft,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Eye,
  EyeOff,
  Globe,
  GripVertical,
  Link2,
  Pencil,
  Plus,
  RotateCcw,
  Save,
  Send,
  Trash2,
} from "lucide-react"
import {
  createAdminWebsiteEvent,
  regenerateAdminWebsiteEventToken,
  togglePublishWebsiteEvent,
  updateAdminWebsiteEvent,
  type MegaEvent,
  type OrganizationAccountSummary,
  type WebsiteEvent,
} from "@/api/websiteEvents"
import {
  createProgramLandingPageApi,
  getProgramLandingPageApi,
  publishProgramLandingPageApi,
  regenerateProgramLandingTokenApi,
  resetProgramLandingFieldApi,
  unpublishProgramLandingPageApi,
  updateProgramLandingPageApi,
  type ProgramLandingPage,
} from "@/api/programWebPages"
import { WEBSITE_BASE_URL } from "@/components/operations/OrgManagementModals"
import { SharePagePopover } from "@/pages/operations/website/components/SharePagePopover"
import {
  EventBannerUploader,
  HeroBackgroundUploader,
} from "@/pages/operations/website/WebsiteEventsPanel"
import { Spinner } from "@/pages/admin/components/common"
import { useToast } from "@/components/ui/toast"
import { cn, getErrorMessage } from "@/lib/utils"

function FieldSourceBadge({
  source,
  onReset,
  resetting,
}: {
  source?: "live" | "override" | "manual"
  onReset?: () => void
  resetting?: boolean
}) {
  if (!source) return null
  if (source === "override") {
    return (
      <span className="inline-flex items-center gap-1.5">
        <span className="text-[10px] font-bold px-2 py-0.5 rounded-[10px] bg-primary/15 text-primary inline-flex items-center gap-1">
          <Pencil size={9} /> Overridden
        </span>
        {onReset && (
          <button
            type="button"
            disabled={resetting}
            onClick={onReset}
            className="text-[10px] font-semibold text-primary hover:underline inline-flex items-center gap-0.5 cursor-pointer"
            title="Reset to live portal value"
          >
            <RotateCcw size={9} /> Reset
          </button>
        )}
      </span>
    )
  }
  return (
    <span className="text-[10px] font-bold px-2 py-0.5 rounded-[10px] bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 inline-flex items-center gap-1">
      <Link2 size={9} /> Live
    </span>
  )
}

function OrderNumberInput({
  value,
  totalCount,
  disabled,
  onCommit,
}: {
  value: number
  totalCount: number
  disabled?: boolean
  onCommit: (pos: number) => void
}) {
  const [text, setText] = useState(String(value))
  useEffect(() => {
    setText(String(value))
  }, [value])
  const commit = () => {
    const parsed = Number.parseInt(text, 10)
    if (!Number.isFinite(parsed) || parsed === value) {
      setText(String(value))
      return
    }
    onCommit(Math.max(1, Math.min(totalCount, parsed)))
    setText(String(value))
  }
  return (
    <input
      type="number"
      aria-label="Order number"
      value={text}
      min={1}
      max={totalCount}
      inputMode="numeric"
      disabled={disabled}
      onChange={(e) => setText(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur()
        if (e.key === "Escape") {
          setText(String(value))
          ;(e.target as HTMLInputElement).blur()
        }
      }}
      onClick={(e) => e.stopPropagation()}
      className="w-11 h-7 px-1 border border-border bg-card text-foreground rounded-[10px] text-xs font-semibold text-center focus:outline-none focus:border-primary transition-colors disabled:opacity-50 shrink-0"
    />
  )
}

function SectionCard({
  title,
  badge,
  defaultOpen = false,
  children,
}: {
  title: string
  badge?: string
  defaultOpen?: boolean
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="rounded-[10px] border border-border bg-card overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full px-4 py-3 flex items-center justify-between gap-2 text-left hover:bg-muted/30 transition-colors cursor-pointer"
      >
        <div className="flex items-center gap-2">
          {open ? <ChevronDown size={14} className="text-primary" /> : <ChevronRight size={14} className="text-muted-foreground" />}
          <span className="text-xs font-extrabold uppercase tracking-wider text-foreground">
            {title}
          </span>
        </div>
        {badge && (
          <span className="text-[11px] font-semibold text-muted-foreground">{badge}</span>
        )}
      </button>
      {open && <div className="px-4 pb-4 pt-1 space-y-3 border-t border-border/60">{children}</div>}
    </div>
  )
}

export function ProgramLandingSplitEditor({
  programId,
  standaloneEvent,
  megaEvents = [],
  organizations = [],
  onBack,
  onCreated,
  readOnly = false,
}: {
  programId?: string
  standaloneEvent?: WebsiteEvent | "new"
  megaEvents?: MegaEvent[]
  organizations?: OrganizationAccountSummary[]
  onBack?: () => void
  onCreated?: (created: WebsiteEvent) => void
  readOnly?: boolean
}) {
  const qc = useQueryClient()
  const toast = useToast()
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const [iframeReady, setIframeReady] = useState(false)

  const isStandalone = !programId && standaloneEvent !== undefined
  const [localStandalone, setLocalStandalone] = useState<WebsiteEvent | null>(() =>
    standaloneEvent && standaloneEvent !== "new" ? standaloneEvent : null,
  )
  useEffect(() => {
    if (standaloneEvent === "new") setLocalStandalone(null)
    else if (standaloneEvent) setLocalStandalone(standaloneEvent)
  }, [standaloneEvent])

  const isCreatingStandalone = isStandalone && !localStandalone

  const { data: programPage, isLoading, isError, error } = useQuery<ProgramLandingPage | null>({
    queryKey: ["program-landing-page", programId],
    queryFn: () => getProgramLandingPageApi(programId!),
    enabled: Boolean(programId),
    retry: false,
  })

  const page: ProgramLandingPage | null = isStandalone
    ? (localStandalone as ProgramLandingPage | null)
    : (programPage ?? null)

  const [langTab, setLangTab] = useState<"en" | "ar">("en")

  // Standalone event organizational links
  const [megaEventId, setMegaEventId] = useState("")
  const [organizationId, setOrganizationId] = useState("")
  const [defaultLanguage, setDefaultLanguage] = useState<"en" | "ar">("en")

  // Core + Hero
  const [slug, setSlug] = useState("")
  const [country, setCountry] = useState("uae")
  const [city, setCity] = useState("")
  const [eventType, setEventType] = useState("workshop")
  const [audience, setAudience] = useState("")
  const [venueType, setVenueType] = useState("onsite")
  const [title, setTitle] = useState("")
  const [subtitle, setSubtitle] = useState("")
  const [tagline, setTagline] = useState("")
  const [bannerUrl, setBannerUrl] = useState<string | null>(null)
  const [topBannerUrl, setTopBannerUrl] = useState<string | null>(null)
  const [hostOrgName, setHostOrgName] = useState("")
  const [dateLabel, setDateLabel] = useState("")
  const [location, setLocation] = useState("")
  const [guidelinesUrl, setGuidelinesUrl] = useState("")

  // About & Benefits
  const [aboutText, setAboutText] = useState("")
  const [benefits, setBenefits] = useState<{ title: string; description: string }[]>([])

  // At a Glance
  const [atAGlance, setAtAGlance] = useState<{ highlight: string; details: string }[]>([])

  // Eligibility (How / Who Can Participate)
  const [eligibilityIntro, setEligibilityIntro] = useState("")
  const [eligibilityRows, setEligibilityRows] = useState<{ label: string; requirement: string }[]>([])
  const [eligibilityNote, setEligibilityNote] = useState("")

  // Journey & Timeline
  const [journeyStages, setJourneyStages] = useState<{ stage: string; title: string; description: string }[]>([])
  const [timeline, setTimeline] = useState<{ date: string; milestone: string }[]>([])
  const [timelineNote, setTimelineNote] = useState("")

  // Deliverables & Awards
  const [deliverables, setDeliverables] = useState<{ phase: string; deadline: string; items: string[] }[]>([])
  const [deliverablesNote, setDeliverablesNote] = useState("")
  const [awardsText, setAwardsText] = useState("")

  // Registration
  const [registrationUrl, setRegistrationUrl] = useState("")
  const [registrationText, setRegistrationText] = useState("")
  const [registrationDeadline, setRegistrationDeadline] = useState("")
  const [whatsappUrl, setWhatsappUrl] = useState("")
  const [registrationNote, setRegistrationNote] = useState("")

  // FAQs, Partners, Contacts
  const [faqs, setFaqs] = useState<{ question: string; answer: string }[]>([])
  const [partners, setPartners] = useState<{ name: string; role: string; logo_url: string }[]>([])
  const [contacts, setContacts] = useState<{ name: string; role: string; organization: string; email: string }[]>([])

  // Program Steps (Live Cohorts + Custom Steps) Order, Descriptions & Visibility
  const [stepOrder, setStepOrder] = useState<string[]>([])
  const [stepDescriptions, setStepDescriptions] = useState<Record<string, string>>({})
  const [customSteps, setCustomSteps] = useState<
    { id: string; name: string; description: string; date_label: string; venue: string; status: string }[]
  >([])
  const [dragCohortId, setDragCohortId] = useState<string | null>(null)
  const [hiddenCohortIds, setHiddenCohortIds] = useState<string[]>([])
  const [hiddenSections, setHiddenSections] = useState<string[]>([])

  // Arabic (full mirror of all EN sections)
  const [arEnabled, setArEnabled] = useState(false)
  const [arContent, setArContent] = useState<Record<string, any>>({})

  const setArField = (key: string, val: any) =>
    setArContent((prev) => ({ ...prev, [key]: val }))

  const setArStepField = (stepId: string, field: string, val: string) =>
    setArContent((prev) => ({
      ...prev,
      steps: {
        ...(prev.steps || {}),
        [stepId]: { ...((prev.steps || {})[stepId] || {}), [field]: val },
      },
    }))

  const setArListItem = (key: string, idx: number, enList: any[], patch: Record<string, any>) =>
    setArContent((prev) => {
      const base = Array.isArray(prev[key]) ? [...prev[key]] : []
      while (base.length < enList.length) base.push({})
      base[idx] = { ...(base[idx] || {}), ...patch }
      return { ...prev, [key]: base }
    })

  useEffect(() => {
    if (!page) return
    setMegaEventId(page.mega_event_id || "")
    setOrganizationId(page.organization_id || "")
    setDefaultLanguage(page.default_language === "ar" ? "ar" : "en")
    setSlug(page.slug || "")
    setCountry(page.country || "uae")
    setCity(page.city || "")
    setEventType(page.event_type || "workshop")
    setAudience(page.audience || "")
    setVenueType(page.venue_type || "onsite")
    setTitle(page.title || "")
    setSubtitle(page.subtitle || "")
    setTagline(page.tagline || "")
    setBannerUrl(page.banner_url || null)
    setTopBannerUrl(page.top_banner_url || null)
    setHostOrgName(page.host_org_name || "")
    setDateLabel(page.date_label || "")
    setLocation(page.location || "")
    setGuidelinesUrl(page.guidelines_url || "")
    setAboutText(page.about_text || "")
    setBenefits(
      Array.isArray(page.benefits)
        ? page.benefits.map((b: any) => ({ title: b.title || "", description: b.description || "" }))
        : [],
    )
    setAtAGlance(
      Array.isArray(page.at_a_glance)
        ? page.at_a_glance.map((g: any) => ({ highlight: g.highlight || "", details: g.details || "" }))
        : [],
    )
    setEligibilityIntro(page.eligibility_intro || "")
    setEligibilityRows(
      Array.isArray(page.eligibility_rows)
        ? page.eligibility_rows.map((r: any) => ({ label: r.label || "", requirement: r.requirement || "" }))
        : [],
    )
    setEligibilityNote(page.eligibility_note || "")
    setJourneyStages(
      Array.isArray(page.journey_stages)
        ? page.journey_stages.map((s: any) => ({ stage: s.stage || "", title: s.title || "", description: s.description || "" }))
        : [],
    )
    setTimeline(
      Array.isArray(page.timeline)
        ? page.timeline.map((t: any) => ({ date: t.date || "", milestone: t.milestone || "" }))
        : [],
    )
    setTimelineNote(page.timeline_note || "")
    setDeliverables(
      Array.isArray(page.deliverables)
        ? page.deliverables.map((d: any) => ({
            phase: d.phase || "",
            deadline: d.deadline || "",
            items: Array.isArray(d.items) ? d.items : [],
          }))
        : [],
    )
    setDeliverablesNote(page.deliverables_note || "")
    setAwardsText(page.awards_text || "")
    setRegistrationUrl(page.registration_url || "")
    setRegistrationText(page.registration_text || "")
    setRegistrationDeadline(page.registration_deadline || "")
    setWhatsappUrl(page.whatsapp_url || "")
    setRegistrationNote(page.registration_note || "")
    setFaqs(
      Array.isArray(page.faqs)
        ? page.faqs.map((f: any) => ({ question: f.question || "", answer: f.answer || "" }))
        : [],
    )
    setPartners(
      Array.isArray(page.partners)
        ? page.partners.map((p: any) => ({ name: p.name || "", role: p.role || "", logo_url: p.logo_url || "" }))
        : [],
    )
    setContacts(
      Array.isArray(page.contacts)
        ? page.contacts.map((c: any) => ({
            name: c.name || "",
            role: c.role || "",
            organization: c.organization || "",
            email: c.email || "",
          }))
        : [],
    )

    const liveCohortIds = (page.live_steps || [])
      .filter((s: any) => !s.is_custom)
      .map((s) => s.cohort_id)
    const hasSavedCustom = Array.isArray(page.overrides?.custom_steps)
    const savedCustom = hasSavedCustom
      ? (page.overrides!.custom_steps as any[]).map((cs) => ({
          id: String(cs.id || `custom-${Math.random().toString(36).slice(2, 10)}`),
          name: String(cs.name || ""),
          description: String(cs.description || ""),
          date_label: String(cs.date_label || ""),
          venue: String(cs.venue || ""),
          status: String(cs.status || ""),
        }))
      : Array.isArray(page.journey_stages)
        ? (page.journey_stages as any[]).map((js, idx) => ({
            id: `legacy-stage-${idx + 1}`,
            name: String(js.title || js.stage || ""),
            description: String(js.description || ""),
            date_label: "",
            venue: "",
            status: "",
          }))
        : []
    setCustomSteps(savedCustom)
    const savedDescs =
      page.overrides?.step_descriptions && typeof page.overrides.step_descriptions === "object"
        ? (page.overrides.step_descriptions as Record<string, string>)
        : {}
    setStepDescriptions(savedDescs)

    const allIds = [...liveCohortIds, ...savedCustom.map((c) => c.id)]
    const savedOrder = Array.isArray(page.overrides?.step_order)
      ? (page.overrides.step_order as string[])
      : []
    const mergedOrder = [
      ...savedOrder.filter((id) => allIds.includes(id)),
      ...allIds.filter((id) => !savedOrder.includes(id)),
    ]
    setStepOrder(mergedOrder)
    setHiddenCohortIds(page.hidden_cohort_ids || [])
    setHiddenSections(page.hidden_sections || [])

    const ar = page.ar_content || {}
    setArEnabled(Boolean(ar.enabled))
    setArContent({
      ...ar,
      title: ar.title || page.title_ar || "",
    })
  }, [page])

  const orderedSteps = useMemo(() => {
    const byId = new Map<string, any>()
    for (const s of page?.live_steps || []) {
      if ((s as any).is_custom) continue
      byId.set(s.cohort_id, {
        ...s,
        is_custom: false,
        description: stepDescriptions[s.cohort_id] ?? (s as any).description ?? "",
      })
    }
    for (const cs of customSteps) {
      byId.set(cs.id, {
        cohort_id: cs.id,
        is_custom: true,
        name: cs.name,
        description: cs.description,
        date_label: cs.date_label || null,
        venue: cs.venue || null,
        city: null,
        status: cs.status || null,
        sessions_count: 0,
        seats_left: null,
      })
    }
    return stepOrder.map((id) => byId.get(id)).filter(Boolean)
  }, [page?.live_steps, customSteps, stepDescriptions, stepOrder])

  const visibleSteps = useMemo(() => {
    const hiddenSet = new Set(hiddenCohortIds)
    return orderedSteps.filter(
      (s) => !hiddenSet.has(s.cohort_id) && (!s.is_custom || (s.name || "").trim().length > 0),
    )
  }, [orderedSteps, hiddenCohortIds])

  // Build live preview payload and stream instantly to real site iframe via postMessage
  const livePreviewData = useMemo(() => {
    if (!page && !isCreatingStandalone) return null
    const hiddenSec = new Set(hiddenSections)
    const fallbackSteps = visibleSteps
    const standaloneStages =
      isStandalone && customSteps.length > 0
        ? customSteps
            .filter((cs) => cs.name.trim() || cs.description.trim())
            .map((cs, i) => ({
              stage: cs.date_label || `Stage ${i + 1}`,
              title: cs.name,
              description: cs.description,
            }))
        : journeyStages.filter((s) => s.title.trim() || s.description.trim())
    return {
      ...(page || {}),
      slug: slug || page?.slug || "draft-event",
      country: country || "uae",
      city: city || null,
      event_type: eventType,
      audience: audience || null,
      venue_type: venueType,
      title: title || page?.title || "Untitled Event",
      title_ar: (arContent.title || "").trim() || null,
      subtitle: subtitle || null,
      tagline: tagline || null,
      banner_url: bannerUrl || null,
      top_banner_url: topBannerUrl || null,
      host_org_name: hostOrgName || null,
      date_label: dateLabel || null,
      location: location || null,
      guidelines_url: guidelinesUrl || null,
      about_text: hiddenSec.has("about") ? null : aboutText || null,
      benefits: benefits.filter((b) => b.title.trim() || b.description.trim()),
      at_a_glance: atAGlance.filter((g) => g.highlight.trim() || g.details.trim()),
      eligibility_intro: eligibilityIntro || null,
      eligibility_rows: eligibilityRows.filter((r) => r.label.trim() || r.requirement.trim()),
      eligibility_note: eligibilityNote || null,
      journey_stages: standaloneStages,
      timeline: timeline.filter((t) => t.date.trim() || t.milestone.trim()),
      timeline_note: timelineNote || null,
      deliverables: deliverables.filter((d) => d.phase.trim() || d.items.length > 0),
      deliverables_note: deliverablesNote || null,
      awards_text: awardsText || null,
      registration_url: hiddenSec.has("registration") ? null : registrationUrl || null,
      registration_text: hiddenSec.has("registration") ? null : registrationText || null,
      registration_deadline: registrationDeadline || null,
      whatsapp_url: whatsappUrl || null,
      registration_note: registrationNote || null,
      faqs: hiddenSec.has("faqs") ? [] : faqs.filter((f) => f.question.trim() || f.answer.trim()),
      partners: hiddenSec.has("partners") ? [] : partners.filter((p) => p.name.trim()),
      contacts: contacts.filter((c) => c.name.trim() || c.email.trim()),
      steps: hiddenSec.has("steps") ? [] : fallbackSteps,
      curriculum_chapters: hiddenSec.has("curriculum") ? [] : page?.curriculum_chapters || [],
      ar_content: {
        ...(page?.ar_content || {}),
        ...arContent,
        enabled: arEnabled,
        en_enabled: true,
      },
    }
  }, [
    isCreatingStandalone,
    isStandalone,
    page,
    slug,
    country,
    city,
    eventType,
    audience,
    venueType,
    title,
    subtitle,
    tagline,
    bannerUrl,
    topBannerUrl,
    hostOrgName,
    dateLabel,
    location,
    guidelinesUrl,
    aboutText,
    benefits,
    atAGlance,
    eligibilityIntro,
    eligibilityRows,
    eligibilityNote,
    journeyStages,
    customSteps,
    timeline,
    timelineNote,
    deliverables,
    deliverablesNote,
    awardsText,
    registrationUrl,
    registrationText,
    registrationDeadline,
    whatsappUrl,
    registrationNote,
    faqs,
    partners,
    contacts,
    visibleSteps,
    hiddenSections,
    arEnabled,
    arContent,
  ])

  useEffect(() => {
    const onMsg = (e: MessageEvent) => {
      if (e.data?.type === "SP_PREVIEW_READY") {
        setIframeReady(true)
      }
    }
    window.addEventListener("message", onMsg)
    return () => window.removeEventListener("message", onMsg)
  }, [])

  useEffect(() => {
    if (!livePreviewData || !iframeRef.current?.contentWindow) return
    iframeRef.current.contentWindow.postMessage(
      {
        type: "SP_LIVE_PREVIEW",
        kind: "event",
        is_published: Boolean(page?.is_published),
        lang: langTab,
        data: livePreviewData,
      },
      "*",
    )
  }, [livePreviewData, langTab, iframeReady, page?.is_published])

  const invalidate = () => {
    if (programId) void qc.invalidateQueries({ queryKey: ["program-landing-page", programId] })
    void qc.invalidateQueries({ queryKey: ["admin-website-events"] })
    void qc.invalidateQueries({ queryKey: ["admin-website-mega-events"] })
    void qc.invalidateQueries({ queryKey: ["admin-website-organizations"] })
  }

  const saveMut = useMutation({
    mutationFn: () => {
      if (isStandalone && !title.trim() && !page?.title) {
        throw new Error("Title is required")
      }
      if (!isStandalone && !page) throw new Error("Not loaded")
      const cleanCustomSteps = customSteps
        .filter((cs) => cs.name.trim() || cs.description.trim())
        .map((cs) => ({
          id: cs.id,
          name: cs.name.trim(),
          description: cs.description.trim(),
          date_label: cs.date_label.trim(),
          venue: cs.venue.trim(),
          status: cs.status.trim(),
        }))
      const nextOverrides: Record<string, any> = {
        ...(page?.overrides || {}),
        step_order: stepOrder,
        step_descriptions: stepDescriptions,
        custom_steps: cleanCustomSteps,
      }
      if (!isStandalone && page) {
        const liveFields: [string, any][] = [
          ["title", title],
          ["about_text", aboutText],
          ["event_type", eventType],
          ["host_org_name", hostOrgName],
          ["date_label", dateLabel],
          ["city", city],
          ["location", location],
        ]
        for (const [key, val] of liveFields) {
          const liveVal = page.field_states?.[key]?.live ?? ""
          if ((val ?? "") !== (liveVal ?? "")) {
            nextOverrides[key] = val
          }
        }
      }
      const syncedStages = isStandalone
        ? cleanCustomSteps.map((cs, i) => ({
            stage: cs.date_label || `Stage ${i + 1}`,
            title: cs.name,
            description: cs.description,
          }))
        : journeyStages.filter((s) => s.title.trim() || s.description.trim())

      const commonPayload = {
        slug: slug.trim() || undefined,
        country: country.trim().toLowerCase() || "uae",
        city: city.trim() || null,
        event_type: eventType,
        audience: audience.trim() || null,
        venue_type: venueType,
        title: title.trim() || page?.title || "",
        title_ar: (arContent.title || "").trim() || null,
        subtitle: subtitle.trim() || null,
        tagline: tagline.trim() || null,
        banner_url: bannerUrl || null,
        top_banner_url: topBannerUrl || null,
        host_org_name: hostOrgName.trim() || null,
        date_label: dateLabel.trim() || null,
        location: location.trim() || null,
        guidelines_url: guidelinesUrl.trim() || null,
        about_text: aboutText.trim() || null,
        benefits: benefits.filter((b) => b.title.trim() || b.description.trim()),
        at_a_glance: atAGlance.filter((g) => g.highlight.trim() || g.details.trim()),
        eligibility_intro: eligibilityIntro.trim() || null,
        eligibility_rows: eligibilityRows.filter((r) => r.label.trim() || r.requirement.trim()),
        eligibility_note: eligibilityNote.trim() || null,
        journey_stages: syncedStages,
        timeline: timeline.filter((t) => t.date.trim() || t.milestone.trim()),
        timeline_note: timelineNote.trim() || null,
        deliverables: deliverables.filter((d) => d.phase.trim() || d.items.length > 0),
        deliverables_note: deliverablesNote.trim() || null,
        awards_text: awardsText.trim() || null,
        registration_url: registrationUrl.trim() || null,
        registration_text: registrationText.trim() || null,
        registration_deadline: registrationDeadline.trim() || null,
        whatsapp_url: whatsappUrl.trim() || null,
        registration_note: registrationNote.trim() || null,
        faqs: faqs.filter((f) => f.question.trim() || f.answer.trim()),
        partners: partners.filter((p) => p.name.trim()),
        contacts: contacts.filter((c) => c.name.trim() || c.email.trim()),
        hidden_cohort_ids: hiddenCohortIds,
        hidden_sections: hiddenSections,
        overrides: nextOverrides,
        ar_content: {
          ...(page?.ar_content || {}),
          ...arContent,
          enabled: arEnabled,
          en_enabled: true,
        },
        ...(isStandalone
          ? {
              mega_event_id: megaEventId || null,
              organization_id: organizationId || null,
              default_language: defaultLanguage,
            }
          : {}),
      }

      if (isStandalone) {
        if (localStandalone) {
          return updateAdminWebsiteEvent(localStandalone.id, commonPayload)
        }
        return createAdminWebsiteEvent({ ...commonPayload, is_published: false })
      }
      return updateProgramLandingPageApi(programId!, commonPayload)
    },
    onSuccess: (saved) => {
      if (isStandalone && saved) {
        const wasNew = isCreatingStandalone
        setLocalStandalone(saved as WebsiteEvent)
        toast.success(wasNew ? "Event draft created" : "Event saved")
        invalidate()
        if (wasNew) onCreated?.(saved as WebsiteEvent)
        return
      }
      toast.success("Landing page saved")
      invalidate()
    },
    onError: (e) => toast.error(getErrorMessage(e, "Could not save landing page")),
  })

  const resetFieldMut = useMutation({
    mutationFn: (field: string) => resetProgramLandingFieldApi(programId!, field),
    onSuccess: () => {
      toast.success("Reset to live portal value")
      invalidate()
    },
    onError: (e) => toast.error(getErrorMessage(e, "Could not reset field")),
  })

  const publishMut = useMutation({
    mutationFn: () => {
      if (isStandalone && localStandalone) {
        return togglePublishWebsiteEvent(localStandalone.id, true)
      }
      return publishProgramLandingPageApi(programId!)
    },
    onSuccess: (res) => {
      if (isStandalone) setLocalStandalone(res as WebsiteEvent)
      toast.success(
        res.is_published
          ? "Landing page published live!"
          : "Submitted to SpacePoint Ops for publishing approval",
      )
      invalidate()
    },
    onError: (e) => toast.error(getErrorMessage(e, "Could not publish landing page")),
  })

  const unpublishMut = useMutation({
    mutationFn: () => {
      if (isStandalone && localStandalone) {
        return togglePublishWebsiteEvent(localStandalone.id, false)
      }
      return unpublishProgramLandingPageApi(programId!)
    },
    onSuccess: (res) => {
      if (isStandalone) setLocalStandalone(res as WebsiteEvent)
      toast.success("Landing page moved back to Draft")
      invalidate()
    },
    onError: (e) => toast.error(getErrorMessage(e, "Could not unpublish landing page")),
  })

  const createMut = useMutation({
    mutationFn: () => createProgramLandingPageApi(programId!),
    onSuccess: () => {
      toast.success("Landing page draft created")
      invalidate()
    },
    onError: (e) => toast.error(getErrorMessage(e, "Could not create landing page")),
  })

  const regenTokenMut = useMutation({
    mutationFn: () => {
      if (isStandalone && localStandalone) {
        return regenerateAdminWebsiteEventToken(localStandalone.id)
      }
      return regenerateProgramLandingTokenApi(programId!)
    },
    onSuccess: (res) => {
      if (isStandalone) setLocalStandalone(res as WebsiteEvent)
      toast.success("Preview link regenerated (previous link revoked)")
      invalidate()
    },
    onError: (e) => toast.error(getErrorMessage(e, "Could not regenerate preview link")),
  })

  const toggleCohortHidden = (cohortId: string) => {
    setHiddenCohortIds((prev) =>
      prev.includes(cohortId) ? prev.filter((id) => id !== cohortId) : [...prev, cohortId],
    )
  }

  const moveStepToPosition = (cohortId: string, oneBasedPos: number) => {
    setStepOrder((prev) => {
      const fromIdx = prev.indexOf(cohortId)
      if (fromIdx === -1) return prev
      const targetIdx = Math.max(0, Math.min(prev.length - 1, oneBasedPos - 1))
      if (fromIdx === targetIdx) return prev
      const next = [...prev]
      const [item] = next.splice(fromIdx, 1)
      next.splice(targetIdx, 0, item)
      return next
    })
  }

  const dropStepOnto = (targetCohortId: string) => {
    if (!dragCohortId || dragCohortId === targetCohortId) return
    const targetIdx = stepOrder.indexOf(targetCohortId)
    if (targetIdx !== -1) {
      moveStepToPosition(dragCohortId, targetIdx + 1)
    }
    setDragCohortId(null)
  }

  const toggleSectionHidden = (sec: string) => {
    setHiddenSections((prev) =>
      prev.includes(sec) ? prev.filter((s) => s !== sec) : [...prev, sec],
    )
  }

  if (!isStandalone && isLoading) return <Spinner />

  if (!isStandalone && isError) {
    return (
      <div className="rounded-[10px] border border-border bg-card p-6 text-sm text-muted-foreground">
        {getErrorMessage(error, "Landing page could not be loaded.")}
      </div>
    )
  }

  if (!isStandalone && !page) {
    return (
      <div className="rounded-[10px] border border-dashed border-border bg-card p-10 text-center space-y-4">
        <p className="text-sm font-bold text-foreground">No landing page yet</p>
        {!readOnly && (
          <button
            type="button"
            disabled={createMut.isPending}
            onClick={() => createMut.mutate()}
            className="inline-flex items-center gap-1.5 h-9 px-4 rounded-[10px] bg-primary text-primary-foreground text-xs font-bold hover:opacity-90 transition-colors cursor-pointer"
          >
            <Plus size={14} /> {createMut.isPending ? "Creating…" : "Create Landing Page"}
          </button>
        )}
      </div>
    )
  }

  const currentSlug = slug || page?.slug || "draft-event"
  const publicUrl = `${WEBSITE_BASE_URL}/events/${country || "uae"}/${currentSlug}`
  const iframeUrl = page?.preview_token
    ? `${WEBSITE_BASE_URL}/preview?t=${page.preview_token}&embed=1`
    : `${WEBSITE_BASE_URL}/preview?embed=1`
  const isReviewOnly = page?.org_access === "review"
  const isSubmitted = !page?.is_published && Boolean(page?.submitted_for_review_at)

  return (
    <div className="space-y-4">
      {/* ── Top Action Bar ──────────────────────────────────────────────── */}
      <div className="rounded-[10px] border border-border bg-card px-4 py-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5 flex-wrap">
          {onBack && (
            <button
              type="button"
              onClick={onBack}
              className="inline-flex items-center gap-1 h-8 px-2.5 rounded-[10px] border border-border bg-background text-xs font-semibold hover:bg-muted cursor-pointer"
            >
              <ArrowLeft size={13} /> Back
            </button>
          )}
          <span className="inline-flex items-center gap-1.5 text-sm font-bold text-foreground">
            <Globe size={15} className="text-primary" /> {isStandalone ? title || "New Event" : "Event Landing Page"}
          </span>
          {page?.is_published ? (
            <span className="inline-flex items-center gap-1 text-[11px] font-bold px-2.5 py-0.5 rounded-[10px] bg-emerald-500/15 text-emerald-600 dark:text-emerald-400">
              <CheckCircle2 size={11} /> Published
            </span>
          ) : isSubmitted ? (
            <span className="inline-flex items-center gap-1 text-[11px] font-bold px-2.5 py-0.5 rounded-[10px] bg-primary/15 text-primary">
              <Clock size={11} /> Pending Review
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 text-[11px] font-bold px-2.5 py-0.5 rounded-[10px] bg-muted text-muted-foreground">
              Draft
            </span>
          )}
          <span className="text-xs font-mono text-muted-foreground hidden sm:inline">
            /events/{country}/{currentSlug}
          </span>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <div className="inline-flex p-0.5 rounded-[10px] bg-muted/60 border border-border">
            <button
              type="button"
              onClick={() => setLangTab("en")}
              className={cn(
                "h-7 px-2.5 rounded-[10px] text-xs font-bold cursor-pointer",
                langTab === "en" ? "bg-background text-foreground" : "text-muted-foreground",
              )}
            >
              EN
            </button>
            <button
              type="button"
              onClick={() => setLangTab("ar")}
              className={cn(
                "h-7 px-2.5 rounded-[10px] text-xs font-bold cursor-pointer inline-flex items-center gap-1",
                langTab === "ar" ? "bg-background text-foreground" : "text-muted-foreground",
              )}
            >
              AR
              {arEnabled && <CheckCircle2 size={11} className="text-emerald-500" />}
            </button>
          </div>

          {page && (
            <SharePagePopover
              publicUrl={publicUrl}
              previewToken={page.preview_token}
              isPublished={Boolean(page.is_published)}
              onRegenerate={readOnly ? undefined : () => regenTokenMut.mutate()}
              regenerating={regenTokenMut.isPending}
            />
          )}

          {!readOnly && (
            <>
              <button
                type="button"
                disabled={saveMut.isPending}
                onClick={() => saveMut.mutate()}
                className="inline-flex items-center gap-1.5 h-8 px-3 rounded-[10px] border border-border bg-background text-xs font-bold text-foreground hover:bg-muted transition-colors cursor-pointer"
              >
                <Save size={13} /> {saveMut.isPending ? "Saving…" : isCreatingStandalone ? "Create Draft" : "Save"}
              </button>

              {page && (page.is_published ? (
                <button
                  type="button"
                  disabled={unpublishMut.isPending}
                  onClick={() => unpublishMut.mutate()}
                  className="inline-flex items-center gap-1.5 h-8 px-3 rounded-[10px] border border-rose-500/40 bg-rose-500/10 text-xs font-bold text-rose-600 dark:text-rose-400 hover:bg-rose-500/20 transition-colors cursor-pointer"
                >
                  <EyeOff size={13} /> Unpublish
                </button>
              ) : (
                <button
                  type="button"
                  disabled={publishMut.isPending}
                  onClick={() => publishMut.mutate()}
                  className="inline-flex items-center gap-1.5 h-8 px-3.5 rounded-[10px] bg-primary text-primary-foreground text-xs font-bold hover:opacity-90 transition-colors cursor-pointer"
                >
                  {isReviewOnly ? <Send size={13} /> : <Globe size={13} />}
                  {publishMut.isPending
                    ? "Working…"
                    : isReviewOnly
                      ? isSubmitted
                        ? "Resubmit for Review"
                        : "Submit for Review"
                      : "Publish Live"}
                </button>
              ))}
            </>
          )}
        </div>
      </div>

      {/* ── Split-Screen: 50% Full Config | 50% Real Live-Updating Iframe ─ */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5 items-start">
        {/* LEFT HALF: ALL SECTIONS */}
        <div className="space-y-3">
          {langTab === "en" ? (
            <>
              {/* 1. Hero & Images */}
              <SectionCard title="1. Hero, Images & Basics" defaultOpen>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <label className="flex flex-col gap-1 sm:col-span-2">
                    <span className="text-xs font-semibold text-muted-foreground">URL Slug</span>
                    <input
                      type="text"
                      disabled={readOnly}
                      value={slug}
                      onChange={(e) => setSlug(e.target.value)}
                      className="h-9 rounded-[10px] border border-border bg-background px-3 font-mono text-xs"
                    />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-xs font-semibold text-muted-foreground">Country</span>
                    <input
                      type="text"
                      disabled={readOnly}
                      value={country}
                      onChange={(e) => setCountry(e.target.value)}
                      className="h-9 rounded-[10px] border border-border bg-background px-3 text-xs"
                    />
                  </label>
                </div>

                <label className="flex flex-col gap-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-semibold text-muted-foreground">Title</span>
                    <FieldSourceBadge
                      source={page?.field_states?.title?.source}
                      onReset={!readOnly && programId ? () => resetFieldMut.mutate("title") : undefined}
                      resetting={resetFieldMut.isPending}
                    />
                  </div>
                  <input
                    type="text"
                    disabled={readOnly}
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    className="h-9 rounded-[10px] border border-border bg-background px-3 text-sm font-medium"
                  />
                </label>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <label className="flex flex-col gap-1">
                    <span className="text-xs font-semibold text-muted-foreground">Subtitle</span>
                    <input
                      type="text"
                      disabled={readOnly}
                      value={subtitle}
                      onChange={(e) => setSubtitle(e.target.value)}
                      className="h-9 rounded-[10px] border border-border bg-background px-3 text-xs"
                    />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-xs font-semibold text-muted-foreground">Tagline</span>
                    <input
                      type="text"
                      disabled={readOnly}
                      value={tagline}
                      onChange={(e) => setTagline(e.target.value)}
                      className="h-9 rounded-[10px] border border-border bg-background px-3 text-xs"
                    />
                  </label>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <label className="flex flex-col gap-1">
                    <div className="flex items-center justify-between gap-1">
                      <span className="text-xs font-semibold text-muted-foreground">Type</span>
                      <FieldSourceBadge
                        source={page?.field_states?.event_type?.source}
                        onReset={!readOnly && programId ? () => resetFieldMut.mutate("event_type") : undefined}
                      />
                    </div>
                    <select
                      disabled={readOnly}
                      value={eventType}
                      onChange={(e) => setEventType(e.target.value)}
                      className="h-9 rounded-[10px] border border-border bg-background px-3 text-xs"
                    >
                      <option value="competition">Competition</option>
                      <option value="workshop">Workshop</option>
                      <option value="talk">Info Session / Talk</option>
                      <option value="hackathon">Hackathon</option>
                      <option value="exhibition">Exhibition</option>
                      <option value="other">Other</option>
                    </select>
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-xs font-semibold text-muted-foreground">Audience</span>
                    <input
                      type="text"
                      disabled={readOnly}
                      value={audience}
                      onChange={(e) => setAudience(e.target.value)}
                      placeholder="Universities, Schools..."
                      className="h-9 rounded-[10px] border border-border bg-background px-3 text-xs"
                    />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-xs font-semibold text-muted-foreground">Venue Format</span>
                    <select
                      disabled={readOnly}
                      value={venueType}
                      onChange={(e) => setVenueType(e.target.value)}
                      className="h-9 rounded-[10px] border border-border bg-background px-3 text-xs"
                    >
                      <option value="onsite">Onsite</option>
                      <option value="online">Online</option>
                      <option value="hybrid">Hybrid</option>
                    </select>
                  </label>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <label className="flex flex-col gap-1">
                    <div className="flex items-center justify-between gap-1">
                      <span className="text-xs font-semibold text-muted-foreground">Host Org</span>
                      <FieldSourceBadge
                        source={page?.field_states?.host_org_name?.source}
                        onReset={!readOnly && programId ? () => resetFieldMut.mutate("host_org_name") : undefined}
                      />
                    </div>
                    <input
                      type="text"
                      disabled={readOnly}
                      value={hostOrgName}
                      onChange={(e) => setHostOrgName(e.target.value)}
                      className="h-9 rounded-[10px] border border-border bg-background px-3 text-xs"
                    />
                  </label>
                  <label className="flex flex-col gap-1">
                    <div className="flex items-center justify-between gap-1">
                      <span className="text-xs font-semibold text-muted-foreground">Dates</span>
                      <FieldSourceBadge
                        source={page?.field_states?.date_label?.source}
                        onReset={!readOnly && programId ? () => resetFieldMut.mutate("date_label") : undefined}
                      />
                    </div>
                    <input
                      type="text"
                      disabled={readOnly}
                      value={dateLabel}
                      onChange={(e) => setDateLabel(e.target.value)}
                      placeholder={isStandalone ? "October 15, 2026" : "Auto from cohorts"}
                      className="h-9 rounded-[10px] border border-border bg-background px-3 text-xs"
                    />
                  </label>
                  <label className="flex flex-col gap-1">
                    <div className="flex items-center justify-between gap-1">
                      <span className="text-xs font-semibold text-muted-foreground">Location</span>
                      <FieldSourceBadge
                        source={page?.field_states?.location?.source}
                        onReset={!readOnly && programId ? () => resetFieldMut.mutate("location") : undefined}
                      />
                    </div>
                    <input
                      type="text"
                      disabled={readOnly}
                      value={location}
                      onChange={(e) => setLocation(e.target.value)}
                      placeholder={isStandalone ? "Venue & City" : "Auto from cohorts"}
                      className="h-9 rounded-[10px] border border-border bg-background px-3 text-xs"
                    />
                  </label>
                </div>

                {isStandalone && (
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <label className="flex flex-col gap-1">
                      <span className="text-xs font-semibold text-muted-foreground">Parent Featured Event</span>
                      <select
                        disabled={readOnly}
                        value={megaEventId}
                        onChange={(e) => setMegaEventId(e.target.value)}
                        className="h-9 rounded-[10px] border border-border bg-background px-3 text-xs"
                      >
                        <option value="">None (Standalone)</option>
                        {megaEvents.map((m) => (
                          <option key={m.id} value={m.id}>
                            {m.title}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="flex flex-col gap-1">
                      <span className="text-xs font-semibold text-muted-foreground">Assigned Partner Org</span>
                      <select
                        disabled={readOnly}
                        value={organizationId}
                        onChange={(e) => setOrganizationId(e.target.value)}
                        className="h-9 rounded-[10px] border border-border bg-background px-3 text-xs"
                      >
                        <option value="">SpacePoint (Unassigned)</option>
                        {organizations.map((o) => (
                          <option key={o.id} value={o.id}>
                            {o.name_latin}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="flex flex-col gap-1">
                      <span className="text-xs font-semibold text-muted-foreground">Default Language</span>
                      <select
                        disabled={readOnly}
                        value={defaultLanguage}
                        onChange={(e) => setDefaultLanguage(e.target.value === "ar" ? "ar" : "en")}
                        className="h-9 rounded-[10px] border border-border bg-background px-3 text-xs"
                      >
                        <option value="en">English (EN)</option>
                        <option value="ar">Arabic (AR)</option>
                      </select>
                    </label>
                  </div>
                )}

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <label className="flex flex-col gap-1">
                    <span className="text-xs font-semibold text-muted-foreground">City</span>
                    <input
                      type="text"
                      disabled={readOnly}
                      value={city}
                      onChange={(e) => setCity(e.target.value)}
                      placeholder="Dubai, Abu Dhabi..."
                      className="h-9 rounded-[10px] border border-border bg-background px-3 text-xs"
                    />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-xs font-semibold text-muted-foreground">Guidelines URL</span>
                    <input
                      type="url"
                      disabled={readOnly}
                      value={guidelinesUrl}
                      onChange={(e) => setGuidelinesUrl(e.target.value)}
                      placeholder="https://..."
                      className="h-9 rounded-[10px] border border-border bg-background px-3 text-xs"
                    />
                  </label>
                </div>

                {!readOnly && (
                  <div className="space-y-3 pt-1">
                    <EventBannerUploader
                      bannerUrl={topBannerUrl}
                      onChange={(u) => setTopBannerUrl(u)}
                      eventTitle={title}
                      breadcrumb={`Events / ${(country || "uae").toUpperCase()}`}
                    />
                    <HeroBackgroundUploader
                      imageUrl={bannerUrl}
                      onChange={(u) => setBannerUrl(u)}
                    />
                  </div>
                )}
              </SectionCard>

              {/* 2. Event Journey (Live Cohorts + Custom Stages) */}
              <SectionCard
                title="2. Event Journey"
                badge={`${visibleSteps.length} / ${orderedSteps.length} visible`}
                defaultOpen
              >
                {!readOnly && (
                  <div className="flex justify-end">
                    <button
                      type="button"
                      onClick={() => {
                        const newId = `custom-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
                        setCustomSteps((prev) => [
                          ...prev,
                          { id: newId, name: "", description: "", date_label: "", venue: "", status: "" },
                        ])
                        setStepOrder((prev) => [...prev, newId])
                      }}
                      className="inline-flex items-center gap-1 h-8 px-3 rounded-[10px] border border-border bg-background text-xs font-semibold text-primary hover:bg-muted cursor-pointer"
                    >
                      <Plus size={12} /> Add Stage
                    </button>
                  </div>
                )}

                {orderedSteps.length === 0 ? (
                  <p className="text-xs text-muted-foreground py-2">No stages yet.</p>
                ) : (
                  <div className="space-y-2.5">
                    {orderedSteps.map((step, idx) => {
                      const isHidden = hiddenCohortIds.includes(step.cohort_id)
                      const isDragging = dragCohortId === step.cohort_id
                      const isCustom = Boolean(step.is_custom)
                      return (
                        <div
                          key={step.cohort_id}
                          draggable={!readOnly}
                          onDragStart={!readOnly ? () => setDragCohortId(step.cohort_id) : undefined}
                          onDragOver={!readOnly ? (e) => e.preventDefault() : undefined}
                          onDrop={!readOnly ? (e) => { e.preventDefault(); dropStepOnto(step.cohort_id) } : undefined}
                          onDragEnd={!readOnly ? () => setDragCohortId(null) : undefined}
                          className={cn(
                            "rounded-[10px] border px-3 py-2.5 text-xs space-y-2 transition-colors",
                            isDragging
                              ? "opacity-40 border-primary bg-background"
                              : isHidden
                                ? "border-border/50 opacity-55 bg-muted/20"
                                : "border-border bg-background",
                            !readOnly && "cursor-grab active:cursor-grabbing",
                          )}
                        >
                          <div className="flex items-center justify-between gap-2.5">
                            <div className="flex items-center gap-2.5 min-w-0 flex-1">
                              {!readOnly && (
                                <GripVertical size={14} className="text-muted-foreground shrink-0 hidden sm:block" />
                              )}
                              {!readOnly && orderedSteps.length > 1 ? (
                                <OrderNumberInput
                                  value={idx + 1}
                                  totalCount={orderedSteps.length}
                                  onCommit={(pos) => moveStepToPosition(step.cohort_id, pos)}
                                />
                              ) : (
                                <span className="text-xs font-semibold text-muted-foreground w-6 text-center shrink-0">
                                  {idx + 1}
                                </span>
                              )}

                              {isCustom ? (
                                <input
                                  type="text"
                                  disabled={readOnly}
                                  value={step.name}
                                  onChange={(e) =>
                                    setCustomSteps((prev) =>
                                      prev.map((c) => (c.id === step.cohort_id ? { ...c, name: e.target.value } : c)),
                                    )
                                  }
                                  placeholder="Stage title"
                                  className="flex-1 h-8 rounded-[10px] border border-border bg-card px-2.5 text-xs font-semibold"
                                />
                              ) : (
                                <div className="min-w-0 space-y-0.5">
                                  <div className="flex items-center gap-2 flex-wrap">
                                    <span className="font-bold text-foreground">{step.name}</span>
                                    <span className="text-[10px] font-bold px-2 py-0.5 rounded-[10px] bg-emerald-500/15 text-emerald-600 dark:text-emerald-400">
                                      Cohort
                                    </span>
                                  </div>
                                  <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                                    <span>{step.date_label || "Dates TBD"}</span>
                                    {step.venue && <span>{step.venue}</span>}
                                    {step.seats_left != null && <span>{step.seats_left} seats left</span>}
                                  </div>
                                </div>
                              )}
                            </div>

                            {!readOnly && (
                              <div className="flex items-center gap-1.5 shrink-0">
                                <button
                                  type="button"
                                  onClick={() => toggleCohortHidden(step.cohort_id)}
                                  className="inline-flex items-center gap-1 h-7 px-2.5 rounded-[10px] border border-border bg-card text-[11px] font-semibold cursor-pointer"
                                >
                                  {isHidden ? <EyeOff size={12} /> : <Eye size={12} className="text-emerald-500" />}
                                  {isHidden ? "Hidden" : "Visible"}
                                </button>
                                {isCustom && (
                                  <button
                                    type="button"
                                    onClick={() => {
                                      setCustomSteps((prev) => prev.filter((c) => c.id !== step.cohort_id))
                                      setStepOrder((prev) => prev.filter((id) => id !== step.cohort_id))
                                      setHiddenCohortIds((prev) => prev.filter((id) => id !== step.cohort_id))
                                    }}
                                    className="p-1.5 rounded-[10px] text-muted-foreground hover:text-rose-500 cursor-pointer"
                                    title="Remove step"
                                  >
                                    <Trash2 size={13} />
                                  </button>
                                )}
                              </div>
                            )}
                          </div>

                          {isCustom && (
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                              <input
                                type="text"
                                disabled={readOnly}
                                value={step.date_label || ""}
                                onChange={(e) =>
                                  setCustomSteps((prev) =>
                                    prev.map((c) => (c.id === step.cohort_id ? { ...c, date_label: e.target.value } : c)),
                                  )
                                }
                                placeholder="Date (optional)"
                                className="h-8 rounded-[10px] border border-border bg-card px-2.5 text-xs"
                              />
                              <input
                                type="text"
                                disabled={readOnly}
                                value={step.venue || ""}
                                onChange={(e) =>
                                  setCustomSteps((prev) =>
                                    prev.map((c) => (c.id === step.cohort_id ? { ...c, venue: e.target.value } : c)),
                                  )
                                }
                                placeholder="Location (optional)"
                                className="h-8 rounded-[10px] border border-border bg-card px-2.5 text-xs"
                              />
                            </div>
                          )}

                          <textarea
                            rows={2}
                            disabled={readOnly}
                            value={step.description || ""}
                            onChange={(e) => {
                              const val = e.target.value
                              if (isCustom) {
                                setCustomSteps((prev) =>
                                  prev.map((c) => (c.id === step.cohort_id ? { ...c, description: val } : c)),
                                )
                              } else {
                                setStepDescriptions((prev) => ({ ...prev, [step.cohort_id]: val }))
                              }
                            }}
                            placeholder="Description (optional)"
                            className="w-full rounded-[10px] border border-border bg-card p-2 text-xs resize-none"
                          />
                        </div>
                      )
                    })}
                  </div>
                )}
              </SectionCard>

              {/* 3. About & Why Participate (Benefits) */}
              <SectionCard title="3. About & Why Participate" badge={`${benefits.length} cards`}>
                <label className="flex flex-col gap-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-semibold text-muted-foreground">About / Overview</span>
                    <FieldSourceBadge
                      source={page?.field_states?.about_text?.source}
                      onReset={!readOnly && programId ? () => resetFieldMut.mutate("about_text") : undefined}
                    />
                  </div>
                  <textarea
                    rows={4}
                    disabled={readOnly}
                    value={aboutText}
                    onChange={(e) => setAboutText(e.target.value)}
                    className="rounded-[10px] border border-border bg-background p-3 text-xs resize-y"
                  />
                </label>

                <div className="space-y-2 pt-2 border-t border-border/60">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-foreground">Why Participate? (Benefit Cards)</span>
                    {!readOnly && (
                      <button
                        type="button"
                        onClick={() => setBenefits((p) => [...p, { title: "", description: "" }])}
                        className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline cursor-pointer"
                      >
                        <Plus size={12} /> Add Card
                      </button>
                    )}
                  </div>
                  {benefits.map((b, i) => (
                    <div key={i} className="rounded-[10px] border border-border bg-background p-2.5 space-y-2">
                      <div className="flex items-center gap-2">
                        <input
                          type="text"
                          disabled={readOnly}
                          value={b.title}
                          onChange={(e) =>
                            setBenefits((p) => p.map((x, idx) => (idx === i ? { ...x, title: e.target.value } : x)))
                          }
                          placeholder="Card Title (e.g. Hands-on engineering)"
                          className="flex-1 h-8 rounded-[10px] border border-border bg-card px-2.5 text-xs"
                        />
                        {!readOnly && (
                          <button
                            type="button"
                            onClick={() => setBenefits((p) => p.filter((_, idx) => idx !== i))}
                            className="p-1 text-muted-foreground hover:text-rose-500 cursor-pointer"
                          >
                            <Trash2 size={13} />
                          </button>
                        )}
                      </div>
                      <textarea
                        rows={2}
                        disabled={readOnly}
                        value={b.description}
                        onChange={(e) =>
                          setBenefits((p) => p.map((x, idx) => (idx === i ? { ...x, description: e.target.value } : x)))
                        }
                        placeholder="Short description..."
                        className="w-full rounded-[10px] border border-border bg-card p-2 text-xs resize-none"
                      />
                    </div>
                  ))}
                </div>
              </SectionCard>

              {/* 4. At a Glance Dynamic Cards */}
              <SectionCard title="4. At a Glance" badge={`${atAGlance.length} cards`}>
                {!readOnly && (
                  <div className="flex justify-end">
                    <button
                      type="button"
                      onClick={() => setAtAGlance((p) => [...p, { highlight: "", details: "" }])}
                      className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline cursor-pointer"
                    >
                      <Plus size={12} /> Add Card
                    </button>
                  </div>
                )}
                {atAGlance.map((g, i) => (
                  <div key={i} className="grid grid-cols-1 sm:grid-cols-12 gap-2 items-center">
                    <input
                      type="text"
                      disabled={readOnly}
                      value={g.highlight}
                      onChange={(e) =>
                        setAtAGlance((p) => p.map((x, idx) => (idx === i ? { ...x, highlight: e.target.value } : x)))
                      }
                      placeholder="Label (e.g. Team Size)"
                      className="sm:col-span-5 h-8 rounded-[10px] border border-border bg-background px-2.5 text-xs"
                    />
                    <input
                      type="text"
                      disabled={readOnly}
                      value={g.details}
                      onChange={(e) =>
                        setAtAGlance((p) => p.map((x, idx) => (idx === i ? { ...x, details: e.target.value } : x)))
                      }
                      placeholder="Value (e.g. 2–4 students)"
                      className="sm:col-span-6 h-8 rounded-[10px] border border-border bg-background px-2.5 text-xs"
                    />
                    {!readOnly && (
                      <button
                        type="button"
                        onClick={() => setAtAGlance((p) => p.filter((_, idx) => idx !== i))}
                        className="sm:col-span-1 p-1 text-muted-foreground hover:text-rose-500 cursor-pointer"
                      >
                        <Trash2 size={13} />
                      </button>
                    )}
                  </div>
                ))}
              </SectionCard>

              {/* 5. Who Can Participate (Eligibility) */}
              <SectionCard title="5. Who Can Participate (Eligibility)" badge={`${eligibilityRows.length} rows`}>
                <label className="flex flex-col gap-1">
                  <span className="text-xs font-semibold text-muted-foreground">Intro</span>
                  <textarea
                    rows={2}
                    disabled={readOnly}
                    value={eligibilityIntro}
                    onChange={(e) => setEligibilityIntro(e.target.value)}
                    className="rounded-[10px] border border-border bg-background p-2.5 text-xs resize-none"
                  />
                </label>
                <div className="flex items-center justify-between pt-1">
                  <span className="text-xs font-bold text-foreground">Eligibility Criteria</span>
                  {!readOnly && (
                    <button
                      type="button"
                      onClick={() => setEligibilityRows((p) => [...p, { label: "", requirement: "" }])}
                      className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline cursor-pointer"
                    >
                      <Plus size={12} /> Add Row
                    </button>
                  )}
                </div>
                {eligibilityRows.map((r, i) => (
                  <div key={i} className="grid grid-cols-1 sm:grid-cols-12 gap-2 items-center">
                    <input
                      type="text"
                      disabled={readOnly}
                      value={r.label}
                      onChange={(e) =>
                        setEligibilityRows((p) => p.map((x, idx) => (idx === i ? { ...x, label: e.target.value } : x)))
                      }
                      placeholder="Criterion (e.g. Age)"
                      className="sm:col-span-4 h-8 rounded-[10px] border border-border bg-background px-2.5 text-xs"
                    />
                    <input
                      type="text"
                      disabled={readOnly}
                      value={r.requirement}
                      onChange={(e) =>
                        setEligibilityRows((p) => p.map((x, idx) => (idx === i ? { ...x, requirement: e.target.value } : x)))
                      }
                      placeholder="Requirement details..."
                      className="sm:col-span-7 h-8 rounded-[10px] border border-border bg-background px-2.5 text-xs"
                    />
                    {!readOnly && (
                      <button
                        type="button"
                        onClick={() => setEligibilityRows((p) => p.filter((_, idx) => idx !== i))}
                        className="sm:col-span-1 p-1 text-muted-foreground hover:text-rose-500 cursor-pointer"
                      >
                        <Trash2 size={13} />
                      </button>
                    )}
                  </div>
                ))}
                <label className="flex flex-col gap-1">
                  <span className="text-xs font-semibold text-muted-foreground">Eligibility Note (optional)</span>
                  <input
                    type="text"
                    disabled={readOnly}
                    value={eligibilityNote}
                    onChange={(e) => setEligibilityNote(e.target.value)}
                    className="h-8 rounded-[10px] border border-border bg-background px-2.5 text-xs"
                  />
                </label>
              </SectionCard>

              {/* 6. Timeline & Important Dates */}
              <SectionCard
                title="6. Timeline & Important Dates"
                badge={`${timeline.length} dates`}
              >
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-foreground">Important Dates</span>
                    {!readOnly && (
                      <button
                        type="button"
                        onClick={() => setTimeline((p) => [...p, { date: "", milestone: "" }])}
                        className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline cursor-pointer"
                      >
                        <Plus size={12} /> Add Date
                      </button>
                    )}
                  </div>
                  {timeline.map((t, i) => (
                    <div key={i} className="grid grid-cols-1 sm:grid-cols-12 gap-2 items-center">
                      <input
                        type="text"
                        disabled={readOnly}
                        value={t.date}
                        onChange={(e) =>
                          setTimeline((p) => p.map((x, idx) => (idx === i ? { ...x, date: e.target.value } : x)))
                        }
                        placeholder="Date (e.g. Oct 15)"
                        className="sm:col-span-4 h-8 rounded-[10px] border border-border bg-background px-2.5 text-xs"
                      />
                      <input
                        type="text"
                        disabled={readOnly}
                        value={t.milestone}
                        onChange={(e) =>
                          setTimeline((p) => p.map((x, idx) => (idx === i ? { ...x, milestone: e.target.value } : x)))
                        }
                        placeholder="Milestone description"
                        className="sm:col-span-7 h-8 rounded-[10px] border border-border bg-background px-2.5 text-xs"
                      />
                      {!readOnly && (
                        <button
                          type="button"
                          onClick={() => setTimeline((p) => p.filter((_, idx) => idx !== i))}
                          className="sm:col-span-1 p-1 text-muted-foreground hover:text-rose-500 cursor-pointer"
                        >
                          <Trash2 size={13} />
                        </button>
                      )}
                    </div>
                  ))}
                  <label className="flex flex-col gap-1 pt-1">
                    <span className="text-xs font-semibold text-muted-foreground">Timeline Note (optional)</span>
                    <input
                      type="text"
                      disabled={readOnly}
                      value={timelineNote}
                      onChange={(e) => setTimelineNote(e.target.value)}
                      className="h-8 rounded-[10px] border border-border bg-background px-2.5 text-xs"
                    />
                  </label>
                </div>
              </SectionCard>

              {/* 7. Deliverables & Awards */}
              <SectionCard title="7. Deliverables & Awards" badge={`${deliverables.length} phases`}>
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-foreground">Deliverable Phases</span>
                  {!readOnly && (
                    <button
                      type="button"
                      onClick={() => setDeliverables((p) => [...p, { phase: "", deadline: "", items: [] }])}
                      className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline cursor-pointer"
                    >
                      <Plus size={12} /> Add Phase
                    </button>
                  )}
                </div>
                {deliverables.map((d, i) => (
                  <div key={i} className="rounded-[10px] border border-border bg-background p-2.5 space-y-2">
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        disabled={readOnly}
                        value={d.phase}
                        onChange={(e) =>
                          setDeliverables((p) => p.map((x, idx) => (idx === i ? { ...x, phase: e.target.value } : x)))
                        }
                        placeholder="Phase title"
                        className="flex-1 h-8 rounded-[10px] border border-border bg-card px-2.5 text-xs"
                      />
                      <input
                        type="text"
                        disabled={readOnly}
                        value={d.deadline}
                        onChange={(e) =>
                          setDeliverables((p) => p.map((x, idx) => (idx === i ? { ...x, deadline: e.target.value } : x)))
                        }
                        placeholder="Deadline"
                        className="w-36 h-8 rounded-[10px] border border-border bg-card px-2 text-xs"
                      />
                      {!readOnly && (
                        <button
                          type="button"
                          onClick={() => setDeliverables((p) => p.filter((_, idx) => idx !== i))}
                          className="p-1 text-muted-foreground hover:text-rose-500 cursor-pointer"
                        >
                          <Trash2 size={13} />
                        </button>
                      )}
                    </div>
                    <textarea
                      rows={3}
                      disabled={readOnly}
                      value={(d.items || []).join("\n")}
                      onChange={(e) =>
                        setDeliverables((p) =>
                          p.map((x, idx) =>
                            idx === i ? { ...x, items: e.target.value.split("\n").filter((l) => l.trim()) } : x,
                          ),
                        )
                      }
                      placeholder="One deliverable item per line..."
                      className="w-full rounded-[10px] border border-border bg-card p-2 text-xs"
                    />
                  </div>
                ))}
                <label className="flex flex-col gap-1 pt-2 border-t border-border/60">
                  <span className="text-xs font-semibold text-muted-foreground">Deliverables Note (optional)</span>
                  <input
                    type="text"
                    disabled={readOnly}
                    value={deliverablesNote}
                    onChange={(e) => setDeliverablesNote(e.target.value)}
                    className="h-8 rounded-[10px] border border-border bg-background px-2.5 text-xs"
                  />
                </label>
                <label className="flex flex-col gap-1 pt-2 border-t border-border/60">
                  <span className="text-xs font-semibold text-muted-foreground">Final Showcase &amp; Awards</span>
                  <textarea
                    rows={3}
                    disabled={readOnly}
                    value={awardsText}
                    onChange={(e) => setAwardsText(e.target.value)}
                    className="rounded-[10px] border border-border bg-background p-2.5 text-xs"
                  />
                </label>
              </SectionCard>

              {/* 8. Registration Link */}
              <SectionCard title="8. Registration Link" defaultOpen>
                <label className="flex flex-col gap-1">
                  <span className="text-xs font-semibold text-muted-foreground">
                    Registration URL
                  </span>
                  <input
                    type="url"
                    disabled={readOnly}
                    value={registrationUrl}
                    onChange={(e) => setRegistrationUrl(e.target.value)}
                    placeholder="https://..."
                    className="h-9 rounded-[10px] border border-border bg-background px-3 text-xs"
                  />
                </label>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <label className="flex flex-col gap-1">
                    <span className="text-xs font-semibold text-muted-foreground">Deadline (optional)</span>
                    <input
                      type="text"
                      disabled={readOnly}
                      value={registrationDeadline}
                      onChange={(e) => setRegistrationDeadline(e.target.value)}
                      className="h-9 rounded-[10px] border border-border bg-background px-3 text-xs"
                    />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-xs font-semibold text-muted-foreground">WhatsApp URL (optional)</span>
                    <input
                      type="url"
                      disabled={readOnly}
                      value={whatsappUrl}
                      onChange={(e) => setWhatsappUrl(e.target.value)}
                      className="h-9 rounded-[10px] border border-border bg-background px-3 text-xs"
                    />
                  </label>
                </div>
                <label className="flex flex-col gap-1">
                  <span className="text-xs font-semibold text-muted-foreground">Registration Text</span>
                  <textarea
                    rows={2}
                    disabled={readOnly}
                    value={registrationText}
                    onChange={(e) => setRegistrationText(e.target.value)}
                    className="rounded-[10px] border border-border bg-background p-2.5 text-xs resize-none"
                  />
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-xs font-semibold text-muted-foreground">Registration Note (optional)</span>
                  <input
                    type="text"
                    disabled={readOnly}
                    value={registrationNote}
                    onChange={(e) => setRegistrationNote(e.target.value)}
                    className="h-8 rounded-[10px] border border-border bg-background px-2.5 text-xs"
                  />
                </label>
              </SectionCard>

              {/* 9. FAQs, Partners, Contacts & Visibility */}
              <SectionCard
                title="9. FAQs, Partners, Contacts & Visibility"
                badge={`${faqs.length} FAQs, ${partners.length} partners`}
              >
                <div className="space-y-2">
                  <span className="text-xs font-bold text-foreground block">Section Visibility</span>
                  <div className="flex flex-wrap gap-2">
                    {[
                      { key: "about", label: "About" },
                      { key: "steps", label: "Event Journey" },
                      { key: "curriculum", label: "Curriculum" },
                      { key: "registration", label: "Registration" },
                      { key: "partners", label: "Partners" },
                      { key: "faqs", label: "FAQs" },
                    ].map((s) => {
                      const hidden = hiddenSections.includes(s.key)
                      return (
                        <button
                          key={s.key}
                          type="button"
                          disabled={readOnly}
                          onClick={() => toggleSectionHidden(s.key)}
                          className={cn(
                            "inline-flex items-center gap-1.5 h-8 px-3 rounded-[10px] border text-xs font-semibold cursor-pointer",
                            hidden
                              ? "border-border bg-background text-muted-foreground line-through opacity-60"
                              : "border-primary bg-primary/10 text-foreground",
                          )}
                        >
                          {hidden ? <EyeOff size={12} /> : <Eye size={12} />} {s.label}
                        </button>
                      )
                    })}
                  </div>
                </div>

                {/* FAQs */}
                <div className="pt-3 border-t border-border/60 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-foreground">FAQs ({faqs.length})</span>
                    {!readOnly && (
                      <button
                        type="button"
                        onClick={() => setFaqs((p) => [...p, { question: "", answer: "" }])}
                        className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline cursor-pointer"
                      >
                        <Plus size={12} /> Add FAQ
                      </button>
                    )}
                  </div>
                  {faqs.map((f, i) => (
                    <div key={i} className="rounded-[10px] border border-border bg-background p-2.5 space-y-2">
                      <div className="flex items-center gap-2">
                        <input
                          type="text"
                          disabled={readOnly}
                          value={f.question}
                          onChange={(e) =>
                            setFaqs((p) => p.map((x, idx) => (idx === i ? { ...x, question: e.target.value } : x)))
                          }
                          placeholder="Question"
                          className="flex-1 h-8 rounded-[10px] border border-border bg-card px-2.5 text-xs"
                        />
                        {!readOnly && (
                          <button
                            type="button"
                            onClick={() => setFaqs((p) => p.filter((_, idx) => idx !== i))}
                            className="p-1 text-muted-foreground hover:text-rose-500 cursor-pointer"
                          >
                            <Trash2 size={13} />
                          </button>
                        )}
                      </div>
                      <textarea
                        rows={2}
                        disabled={readOnly}
                        value={f.answer}
                        onChange={(e) =>
                          setFaqs((p) => p.map((x, idx) => (idx === i ? { ...x, answer: e.target.value } : x)))
                        }
                        placeholder="Answer"
                        className="w-full rounded-[10px] border border-border bg-card p-2 text-xs resize-none"
                      />
                    </div>
                  ))}
                </div>

                {/* Partners */}
                <div className="pt-3 border-t border-border/60 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-foreground">Partners ({partners.length})</span>
                    {!readOnly && (
                      <button
                        type="button"
                        onClick={() => setPartners((p) => [...p, { name: "", role: "Supporting Partner", logo_url: "" }])}
                        className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline cursor-pointer"
                      >
                        <Plus size={12} /> Add Partner
                      </button>
                    )}
                  </div>
                  {partners.map((pt, i) => (
                    <div key={i} className="grid grid-cols-1 sm:grid-cols-12 gap-2 items-center">
                      <input
                        type="text"
                        disabled={readOnly}
                        value={pt.name}
                        onChange={(e) =>
                          setPartners((p) => p.map((x, idx) => (idx === i ? { ...x, name: e.target.value } : x)))
                        }
                        placeholder="Partner Name"
                        className="sm:col-span-5 h-8 rounded-[10px] border border-border bg-background px-2.5 text-xs"
                      />
                      <input
                        type="text"
                        disabled={readOnly}
                        value={pt.role}
                        onChange={(e) =>
                          setPartners((p) => p.map((x, idx) => (idx === i ? { ...x, role: e.target.value } : x)))
                        }
                        placeholder="Role"
                        className="sm:col-span-6 h-8 rounded-[10px] border border-border bg-background px-2.5 text-xs"
                      />
                      {!readOnly && (
                        <button
                          type="button"
                          onClick={() => setPartners((p) => p.filter((_, idx) => idx !== i))}
                          className="sm:col-span-1 p-1 text-muted-foreground hover:text-rose-500 cursor-pointer"
                        >
                          <Trash2 size={13} />
                        </button>
                      )}
                    </div>
                  ))}
                </div>

                {/* Contacts */}
                <div className="pt-3 border-t border-border/60 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-foreground">Contacts ({contacts.length})</span>
                    {!readOnly && (
                      <button
                        type="button"
                        onClick={() =>
                          setContacts((p) => [...p, { name: "", role: "", organization: "", email: "" }])
                        }
                        className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline cursor-pointer"
                      >
                        <Plus size={12} /> Add Contact
                      </button>
                    )}
                  </div>
                  {contacts.map((ct, i) => (
                    <div key={i} className="rounded-[10px] border border-border bg-background p-2.5 space-y-2">
                      <div className="flex items-center gap-2">
                        <input
                          type="text"
                          disabled={readOnly}
                          value={ct.name}
                          onChange={(e) =>
                            setContacts((p) => p.map((x, idx) => (idx === i ? { ...x, name: e.target.value } : x)))
                          }
                          placeholder="Name"
                          className="flex-1 h-8 rounded-[10px] border border-border bg-card px-2.5 text-xs"
                        />
                        <input
                          type="email"
                          disabled={readOnly}
                          value={ct.email}
                          onChange={(e) =>
                            setContacts((p) => p.map((x, idx) => (idx === i ? { ...x, email: e.target.value } : x)))
                          }
                          placeholder="Email"
                          className="flex-1 h-8 rounded-[10px] border border-border bg-card px-2.5 text-xs"
                        />
                        {!readOnly && (
                          <button
                            type="button"
                            onClick={() => setContacts((p) => p.filter((_, idx) => idx !== i))}
                            className="p-1 text-muted-foreground hover:text-rose-500 cursor-pointer"
                          >
                            <Trash2 size={13} />
                          </button>
                        )}
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        <input
                          type="text"
                          disabled={readOnly}
                          value={ct.role}
                          onChange={(e) =>
                            setContacts((p) => p.map((x, idx) => (idx === i ? { ...x, role: e.target.value } : x)))
                          }
                          placeholder="Role"
                          className="h-8 rounded-[10px] border border-border bg-card px-2.5 text-xs"
                        />
                        <input
                          type="text"
                          disabled={readOnly}
                          value={ct.organization}
                          onChange={(e) =>
                            setContacts((p) => p.map((x, idx) => (idx === i ? { ...x, organization: e.target.value } : x)))
                          }
                          placeholder="Organization"
                          className="h-8 rounded-[10px] border border-border bg-card px-2.5 text-xs"
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </SectionCard>
            </>
          ) : (
            /* FULL ARABIC MIRROR OF ALL ENGLISH SECTIONS */
            <div className="space-y-3" dir="rtl">
              <div className="rounded-[10px] border border-border bg-card px-4 py-3 flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs font-extrabold text-foreground">
                  النسخة العربية
                </span>
                <div className="flex items-center gap-3">
                  {!readOnly && (
                    <button
                      type="button"
                      onClick={() => {
                        const stepsCopy: Record<string, any> = {}
                        for (const st of orderedSteps) {
                          stepsCopy[st.cohort_id] = {
                            name: st.name || "",
                            description: st.description || "",
                            date_label: st.date_label || "",
                            venue: [st.venue, st.city].filter(Boolean).join("، "),
                          }
                        }
                        setArContent({
                          ...arContent,
                          title: title || "",
                          subtitle: subtitle || "",
                          tagline: tagline || "",
                          audience: audience || "",
                          host_org_name: hostOrgName || "",
                          date_label: dateLabel || "",
                          location: location || "",
                          city: city || "",
                          about_text: aboutText || "",
                          benefits: benefits.map((b) => ({ title: b.title, description: b.description })),
                          at_a_glance: atAGlance.map((g) => ({ highlight: g.highlight, details: g.details })),
                          eligibility_intro: eligibilityIntro || "",
                          eligibility_rows: eligibilityRows.map((r) => ({ label: r.label, requirement: r.requirement })),
                          eligibility_note: eligibilityNote || "",
                          timeline: timeline.map((t) => ({ date: t.date, milestone: t.milestone })),
                          deliverables: deliverables.map((d) => ({ phase: d.phase, deadline: d.deadline, items: [...d.items] })),
                          awards_text: awardsText || "",
                          registration_deadline: registrationDeadline || "",
                          registration_text: registrationText || "",
                          faqs: faqs.map((f) => ({ question: f.question, answer: f.answer })),
                          partners: partners.map((p) => ({ name: p.name, role: p.role, logo_url: p.logo_url })),
                          contacts: contacts.map((c) => ({ ...c })),
                          steps: stepsCopy,
                        })
                        toast.success("تم نسخ الحقول من الإنجليزية")
                      }}
                      className="h-7 px-2.5 rounded-[10px] border border-border bg-background text-xs font-semibold text-primary hover:bg-muted cursor-pointer"
                    >
                      نسخ من الإنجليزية
                    </button>
                  )}
                  <label className="inline-flex items-center gap-2 text-xs font-semibold text-foreground cursor-pointer">
                    <input
                      type="checkbox"
                      disabled={readOnly}
                      checked={arEnabled}
                      onChange={(e) => setArEnabled(e.target.checked)}
                      className="h-4 w-4 rounded-[10px] border-border"
                    />
                    تفعيل العربية
                  </label>
                </div>
              </div>

              {/* 1. Hero & Basics (AR) */}
              <SectionCard title="1. المقدمة والأساسيات" defaultOpen>
                <div className="space-y-3">
                  <label className="flex flex-col gap-1">
                    <span className="text-xs font-semibold text-muted-foreground">العنوان</span>
                    <input
                      type="text"
                      disabled={readOnly}
                      value={arContent.title ?? ""}
                      onChange={(e) => setArField("title", e.target.value)}
                      placeholder={title || "العنوان"}
                      className="h-9 rounded-[10px] border border-border bg-background px-3 text-sm font-medium"
                    />
                  </label>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <label className="flex flex-col gap-1">
                      <span className="text-xs font-semibold text-muted-foreground">العنوان الفرعي</span>
                      <input
                        type="text"
                        disabled={readOnly}
                        value={arContent.subtitle ?? ""}
                        onChange={(e) => setArField("subtitle", e.target.value)}
                        placeholder={subtitle || "العنوان الفرعي"}
                        className="h-9 rounded-[10px] border border-border bg-background px-3 text-xs"
                      />
                    </label>
                    <label className="flex flex-col gap-1">
                      <span className="text-xs font-semibold text-muted-foreground">الشعار</span>
                      <input
                        type="text"
                        disabled={readOnly}
                        value={arContent.tagline ?? ""}
                        onChange={(e) => setArField("tagline", e.target.value)}
                        placeholder={tagline || "الشعار"}
                        className="h-9 rounded-[10px] border border-border bg-background px-3 text-xs"
                      />
                    </label>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <label className="flex flex-col gap-1">
                      <span className="text-xs font-semibold text-muted-foreground">نوع الفعالية</span>
                      <input
                        type="text"
                        disabled={readOnly}
                        value={arContent.event_type_label ?? ""}
                        onChange={(e) => setArField("event_type_label", e.target.value)}
                        placeholder={eventType}
                        className="h-9 rounded-[10px] border border-border bg-background px-3 text-xs"
                      />
                    </label>
                    <label className="flex flex-col gap-1">
                      <span className="text-xs font-semibold text-muted-foreground">الفئة المستهدفة</span>
                      <input
                        type="text"
                        disabled={readOnly}
                        value={arContent.audience ?? ""}
                        onChange={(e) => setArField("audience", e.target.value)}
                        placeholder={audience || "الفئة المستهدفة"}
                        className="h-9 rounded-[10px] border border-border bg-background px-3 text-xs"
                      />
                    </label>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <label className="flex flex-col gap-1">
                      <span className="text-xs font-semibold text-muted-foreground">الجهة المنظمة</span>
                      <input
                        type="text"
                        disabled={readOnly}
                        value={arContent.host_org_name ?? ""}
                        onChange={(e) => setArField("host_org_name", e.target.value)}
                        placeholder={hostOrgName || "الجهة المنظمة"}
                        className="h-9 rounded-[10px] border border-border bg-background px-3 text-xs"
                      />
                    </label>
                    <label className="flex flex-col gap-1">
                      <span className="text-xs font-semibold text-muted-foreground">التواريخ</span>
                      <input
                        type="text"
                        disabled={readOnly}
                        value={arContent.date_label ?? ""}
                        onChange={(e) => setArField("date_label", e.target.value)}
                        placeholder={dateLabel || "التواريخ"}
                        className="h-9 rounded-[10px] border border-border bg-background px-3 text-xs"
                      />
                    </label>
                    <label className="flex flex-col gap-1">
                      <span className="text-xs font-semibold text-muted-foreground">الموقع</span>
                      <input
                        type="text"
                        disabled={readOnly}
                        value={arContent.location ?? ""}
                        onChange={(e) => setArField("location", e.target.value)}
                        placeholder={location || "الموقع"}
                        className="h-9 rounded-[10px] border border-border bg-background px-3 text-xs"
                      />
                    </label>
                  </div>
                  {!readOnly && (
                    <div className="space-y-3 pt-1" dir="ltr">
                      <EventBannerUploader
                        bannerUrl={arContent.top_banner_url ?? null}
                        onChange={(u) => setArField("top_banner_url", u)}
                        eventTitle={arContent.title || title}
                        breadcrumb={`Events / ${(country || "uae").toUpperCase()} / AR`}
                      />
                      <HeroBackgroundUploader
                        imageUrl={arContent.banner_url ?? null}
                        onChange={(u) => setArField("banner_url", u)}
                      />
                    </div>
                  )}
                </div>
              </SectionCard>

              {/* 2. Event Journey (AR) */}
              <SectionCard title="2. رحلة ومراحل الفعالية" badge={`${orderedSteps.length} مراحل`} defaultOpen>
                {orderedSteps.length === 0 ? (
                  <p className="text-xs text-muted-foreground py-1">لا توجد مراحل بعد</p>
                ) : (
                  <div className="space-y-2.5">
                    {orderedSteps.map((st, idx) => {
                      const arSt = (arContent.steps || {})[st.cohort_id] || {}
                      return (
                        <div key={st.cohort_id} className="rounded-[10px] border border-border bg-background p-3 space-y-2">
                          <div className="text-[11px] font-bold text-primary">
                            المرحلة {idx + 1}
                          </div>
                          <input
                            type="text"
                            disabled={readOnly}
                            value={arSt.name ?? ""}
                            onChange={(e) => setArStepField(st.cohort_id, "name", e.target.value)}
                            placeholder={st.name || "عنوان المرحلة"}
                            className="w-full h-8 rounded-[10px] border border-border bg-card px-2.5 text-xs font-semibold"
                          />
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                            <input
                              type="text"
                              disabled={readOnly}
                              value={arSt.date_label ?? ""}
                              onChange={(e) => setArStepField(st.cohort_id, "date_label", e.target.value)}
                              placeholder={st.date_label || "التاريخ"}
                              className="h-8 rounded-[10px] border border-border bg-card px-2.5 text-xs"
                            />
                            <input
                              type="text"
                              disabled={readOnly}
                              value={arSt.venue ?? ""}
                              onChange={(e) => setArStepField(st.cohort_id, "venue", e.target.value)}
                              placeholder={[st.venue, st.city].filter(Boolean).join("، ") || "الموقع"}
                              className="h-8 rounded-[10px] border border-border bg-card px-2.5 text-xs"
                            />
                          </div>
                          <textarea
                            rows={2}
                            disabled={readOnly}
                            value={arSt.description ?? ""}
                            onChange={(e) => setArStepField(st.cohort_id, "description", e.target.value)}
                            placeholder={st.description || "الوصف"}
                            className="w-full rounded-[10px] border border-border bg-card p-2 text-xs resize-none"
                          />
                        </div>
                      )
                    })}
                  </div>
                )}
              </SectionCard>

              {/* 3. About & Why Participate (AR) */}
              <SectionCard title="3. نبذة عن الفعالية ولماذا تشارك؟" badge={`${benefits.length} بطاقات`}>
                <div className="space-y-3">
                  <label className="flex flex-col gap-1">
                    <span className="text-xs font-semibold text-muted-foreground">نبذة عن الفعالية</span>
                    <textarea
                      rows={4}
                      disabled={readOnly}
                      value={arContent.about_text ?? ""}
                      onChange={(e) => setArField("about_text", e.target.value)}
                      placeholder={aboutText || "نبذة عن الفعالية"}
                      className="rounded-[10px] border border-border bg-background p-3 text-xs resize-y"
                    />
                  </label>
                  {benefits.map((b, i) => {
                    const arB = (arContent.benefits || [])[i] || {}
                    return (
                      <div key={i} className="rounded-[10px] border border-border bg-background p-2.5 space-y-2">
                        <input
                          type="text"
                          disabled={readOnly}
                          value={arB.title ?? ""}
                          onChange={(e) =>
                            setArListItem("benefits", i, benefits, { title: e.target.value, description: arB.description ?? b.description })
                          }
                          placeholder={b.title || "العنوان"}
                          className="w-full h-8 rounded-[10px] border border-border bg-card px-2.5 text-xs"
                        />
                        <textarea
                          rows={2}
                          disabled={readOnly}
                          value={arB.description ?? ""}
                          onChange={(e) =>
                            setArListItem("benefits", i, benefits, { title: arB.title ?? b.title, description: e.target.value })
                          }
                          placeholder={b.description || "الوصف"}
                          className="w-full rounded-[10px] border border-border bg-card p-2 text-xs resize-none"
                        />
                      </div>
                    )
                  })}
                </div>
              </SectionCard>

              {/* 4. At a Glance (AR) */}
              <SectionCard title="4. لمحة سريعة" badge={`${atAGlance.length} بطاقات`}>
                {atAGlance.length === 0 ? (
                  <p className="text-xs text-muted-foreground py-1">لا توجد بطاقات بعد</p>
                ) : (
                  <div className="space-y-2">
                    {atAGlance.map((g, i) => {
                      const arG = (arContent.at_a_glance || [])[i] || {}
                      return (
                        <div key={i} className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                          <input
                            type="text"
                            disabled={readOnly}
                            value={arG.highlight ?? ""}
                            onChange={(e) =>
                              setArListItem("at_a_glance", i, atAGlance, { highlight: e.target.value, details: arG.details ?? g.details })
                            }
                            placeholder={g.highlight || "العنوان"}
                            className="h-8 rounded-[10px] border border-border bg-background px-2.5 text-xs"
                          />
                          <input
                            type="text"
                            disabled={readOnly}
                            value={arG.details ?? ""}
                            onChange={(e) =>
                              setArListItem("at_a_glance", i, atAGlance, { highlight: arG.highlight ?? g.highlight, details: e.target.value })
                            }
                            placeholder={g.details || "القيمة"}
                            className="h-8 rounded-[10px] border border-border bg-background px-2.5 text-xs"
                          />
                        </div>
                      )
                    })}
                  </div>
                )}
              </SectionCard>

              {/* 5. Who Can Participate (AR) */}
              <SectionCard title="5. من يمكنه المشاركة؟" badge={`${eligibilityRows.length} معايير`}>
                <div className="space-y-2.5">
                  <textarea
                    rows={2}
                    disabled={readOnly}
                    value={arContent.eligibility_intro ?? ""}
                    onChange={(e) => setArField("eligibility_intro", e.target.value)}
                    placeholder={eligibilityIntro || "مقدمة"}
                    className="w-full rounded-[10px] border border-border bg-background p-2.5 text-xs resize-none"
                  />
                  {eligibilityRows.map((r, i) => {
                    const arR = (arContent.eligibility_rows || [])[i] || {}
                    return (
                      <div key={i} className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        <input
                          type="text"
                          disabled={readOnly}
                          value={arR.label ?? ""}
                          onChange={(e) =>
                            setArListItem("eligibility_rows", i, eligibilityRows, { label: e.target.value, requirement: arR.requirement ?? r.requirement })
                          }
                          placeholder={r.label || "المعيار"}
                          className="h-8 rounded-[10px] border border-border bg-background px-2.5 text-xs"
                        />
                        <input
                          type="text"
                          disabled={readOnly}
                          value={arR.requirement ?? ""}
                          onChange={(e) =>
                            setArListItem("eligibility_rows", i, eligibilityRows, { label: arR.label ?? r.label, requirement: e.target.value })
                          }
                          placeholder={r.requirement || "المتطلبات"}
                          className="h-8 rounded-[10px] border border-border bg-background px-2.5 text-xs"
                        />
                      </div>
                    )
                  })}
                  <input
                    type="text"
                    disabled={readOnly}
                    value={arContent.eligibility_note ?? ""}
                    onChange={(e) => setArField("eligibility_note", e.target.value)}
                    placeholder={eligibilityNote || "ملاحظة (اختياري)"}
                    className="w-full h-8 rounded-[10px] border border-border bg-background px-2.5 text-xs"
                  />
                </div>
              </SectionCard>

              {/* 6. Timeline & Important Dates (AR) */}
              <SectionCard title="6. الجدول الزمني والمواعيد المهمة" badge={`${timeline.length} مواعيد`}>
                {timeline.length === 0 ? (
                  <p className="text-xs text-muted-foreground py-1">لا توجد مواعيد بعد</p>
                ) : (
                  <div className="space-y-2">
                    {timeline.map((t, i) => {
                      const arT = (arContent.timeline || [])[i] || {}
                      return (
                        <div key={i} className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                          <input
                            type="text"
                            disabled={readOnly}
                            value={arT.date ?? ""}
                            onChange={(e) =>
                              setArListItem("timeline", i, timeline, { date: e.target.value, milestone: arT.milestone ?? t.milestone })
                            }
                            placeholder={t.date || "التاريخ"}
                            className="h-8 rounded-[10px] border border-border bg-background px-2.5 text-xs"
                          />
                          <input
                            type="text"
                            disabled={readOnly}
                            value={arT.milestone ?? ""}
                            onChange={(e) =>
                              setArListItem("timeline", i, timeline, { date: arT.date ?? t.date, milestone: e.target.value })
                            }
                            placeholder={t.milestone || "الحدث"}
                            className="h-8 rounded-[10px] border border-border bg-background px-2.5 text-xs"
                          />
                        </div>
                      )
                    })}
                  </div>
                )}
              </SectionCard>

              {/* 7. Deliverables & Awards (AR) */}
              <SectionCard title="7. التسليمات والجوائز" badge={`${deliverables.length} مراحل`}>
                <div className="space-y-2.5">
                  {deliverables.map((d, i) => {
                    const arD = (arContent.deliverables || [])[i] || {}
                    return (
                      <div key={i} className="rounded-[10px] border border-border bg-background p-2.5 space-y-2">
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                          <input
                            type="text"
                            disabled={readOnly}
                            value={arD.phase ?? ""}
                            onChange={(e) =>
                              setArListItem("deliverables", i, deliverables, {
                                phase: e.target.value,
                                deadline: arD.deadline ?? d.deadline,
                                items: arD.items ?? d.items,
                              })
                            }
                            placeholder={d.phase || "المرحلة"}
                            className="h-8 rounded-[10px] border border-border bg-card px-2.5 text-xs"
                          />
                          <input
                            type="text"
                            disabled={readOnly}
                            value={arD.deadline ?? ""}
                            onChange={(e) =>
                              setArListItem("deliverables", i, deliverables, {
                                phase: arD.phase ?? d.phase,
                                deadline: e.target.value,
                                items: arD.items ?? d.items,
                              })
                            }
                            placeholder={d.deadline || "الموعد النهائي"}
                            className="h-8 rounded-[10px] border border-border bg-card px-2.5 text-xs"
                          />
                        </div>
                        <textarea
                          rows={3}
                          disabled={readOnly}
                          value={Array.isArray(arD.items) ? arD.items.join("\n") : ""}
                          onChange={(e) =>
                            setArListItem("deliverables", i, deliverables, {
                              phase: arD.phase ?? d.phase,
                              deadline: arD.deadline ?? d.deadline,
                              items: e.target.value.split("\n").filter((l) => l.trim()),
                            })
                          }
                          placeholder={(d.items || []).join("\n")}
                          className="w-full rounded-[10px] border border-border bg-card p-2 text-xs"
                        />
                      </div>
                    )
                  })}
                  <label className="flex flex-col gap-1">
                    <span className="text-xs font-semibold text-muted-foreground">العرض الختامي والجوائز</span>
                    <textarea
                      rows={3}
                      disabled={readOnly}
                      value={arContent.awards_text ?? ""}
                      onChange={(e) => setArField("awards_text", e.target.value)}
                      placeholder={awardsText || "الجوائز"}
                      className="w-full rounded-[10px] border border-border bg-background p-2.5 text-xs"
                    />
                  </label>
                </div>
              </SectionCard>

              {/* 8. Registration (AR) */}
              <SectionCard title="8. التسجيل">
                <div className="space-y-2.5">
                  <label className="flex flex-col gap-1">
                    <span className="text-xs font-semibold text-muted-foreground">الموعد النهائي للتسجيل</span>
                    <input
                      type="text"
                      disabled={readOnly}
                      value={arContent.registration_deadline ?? ""}
                      onChange={(e) => setArField("registration_deadline", e.target.value)}
                      placeholder={registrationDeadline || "الموعد النهائي للتسجيل"}
                      className="h-9 rounded-[10px] border border-border bg-background px-3 text-xs"
                    />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-xs font-semibold text-muted-foreground">نص التسجيل</span>
                    <textarea
                      rows={2}
                      disabled={readOnly}
                      value={arContent.registration_text ?? ""}
                      onChange={(e) => setArField("registration_text", e.target.value)}
                      placeholder={registrationText || "نص التسجيل"}
                      className="rounded-[10px] border border-border bg-background p-2.5 text-xs resize-none"
                    />
                  </label>
                </div>
              </SectionCard>

              {/* 9. FAQs, Partners & Contacts (AR) */}
              <SectionCard title="9. الأسئلة الشائعة والشركاء والتواصل" badge={`${faqs.length} أسئلة، ${partners.length} شركاء`}>
                {faqs.length === 0 && partners.length === 0 && contacts.length === 0 ? (
                  <p className="text-xs text-muted-foreground py-1">لا توجد عناصر بعد</p>
                ) : (
                  <div className="space-y-3">
                    {faqs.map((f, i) => {
                      const arF = (arContent.faqs || [])[i] || {}
                      return (
                        <div key={i} className="rounded-[10px] border border-border bg-background p-2.5 space-y-2">
                          <input
                            type="text"
                            disabled={readOnly}
                            value={arF.question ?? ""}
                            onChange={(e) =>
                              setArListItem("faqs", i, faqs, { question: e.target.value, answer: arF.answer ?? f.answer })
                            }
                            placeholder={f.question || "السؤال"}
                            className="w-full h-8 rounded-[10px] border border-border bg-card px-2.5 text-xs"
                          />
                          <textarea
                            rows={2}
                            disabled={readOnly}
                            value={arF.answer ?? ""}
                            onChange={(e) =>
                              setArListItem("faqs", i, faqs, { question: arF.question ?? f.question, answer: e.target.value })
                            }
                            placeholder={f.answer || "الإجابة"}
                            className="w-full rounded-[10px] border border-border bg-card p-2 text-xs resize-none"
                          />
                        </div>
                      )
                    })}
                    {partners.map((pt, i) => {
                      const arP = (arContent.partners || [])[i] || {}
                      return (
                        <div key={i} className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                          <input
                            type="text"
                            disabled={readOnly}
                            value={arP.name ?? ""}
                            onChange={(e) =>
                              setArListItem("partners", i, partners, { name: e.target.value, role: arP.role ?? pt.role, logo_url: pt.logo_url })
                            }
                            placeholder={pt.name || "اسم الشريك"}
                            className="h-8 rounded-[10px] border border-border bg-background px-2.5 text-xs"
                          />
                          <input
                            type="text"
                            disabled={readOnly}
                            value={arP.role ?? ""}
                            onChange={(e) =>
                              setArListItem("partners", i, partners, { name: arP.name ?? pt.name, role: e.target.value, logo_url: pt.logo_url })
                            }
                            placeholder={pt.role || "الدور"}
                            className="h-8 rounded-[10px] border border-border bg-background px-2.5 text-xs"
                          />
                        </div>
                      )
                    })}
                    {contacts.map((ct, i) => {
                      const arC = (arContent.contacts || [])[i] || {}
                      return (
                        <div key={i} className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                          <input
                            type="text"
                            disabled={readOnly}
                            value={arC.name ?? ""}
                            onChange={(e) =>
                              setArListItem("contacts", i, contacts, { ...ct, ...arC, name: e.target.value })
                            }
                            placeholder={ct.name || "الاسم"}
                            className="h-8 rounded-[10px] border border-border bg-background px-2.5 text-xs"
                          />
                          <input
                            type="text"
                            disabled={readOnly}
                            value={arC.role ?? ""}
                            onChange={(e) =>
                              setArListItem("contacts", i, contacts, { ...ct, ...arC, role: e.target.value })
                            }
                            placeholder={ct.role || "المنصب"}
                            className="h-8 rounded-[10px] border border-border bg-background px-2.5 text-xs"
                          />
                          <input
                            type="text"
                            disabled={readOnly}
                            value={arC.organization ?? ""}
                            onChange={(e) =>
                              setArListItem("contacts", i, contacts, { ...ct, ...arC, organization: e.target.value })
                            }
                            placeholder={ct.organization || "الجهة"}
                            className="h-8 rounded-[10px] border border-border bg-background px-2.5 text-xs"
                          />
                        </div>
                      )
                    })}
                  </div>
                )}
              </SectionCard>
            </div>
          )}
        </div>

        {/* RIGHT HALF: REAL LIVE SITE IFRAME (UPDATES INSTANTLY VIA POSTMESSAGE) */}
        <div className="xl:sticky xl:top-4 rounded-[10px] border border-border bg-[#05030A] overflow-hidden shadow-xl">
          <div className="px-4 py-2.5 border-b border-white/10 bg-[#120A22] flex items-center justify-between gap-2 flex-wrap">
            <span className="text-xs font-bold text-white/90">
              Live Preview ({langTab.toUpperCase()})
            </span>
            <span className="text-[11px] font-mono text-white/50 break-all">
              /events/{country}/{currentSlug}
            </span>
          </div>
          <iframe
            ref={iframeRef}
            src={iframeUrl}
            title="Live Event Landing Page Preview"
            onLoad={() => setIframeReady(true)}
            className="w-full h-[780px] bg-[#05030A] border-0"
          />
        </div>
      </div>
    </div>
  )
}

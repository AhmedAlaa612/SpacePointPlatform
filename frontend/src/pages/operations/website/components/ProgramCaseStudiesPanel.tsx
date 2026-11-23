import { useEffect, useMemo, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  Award,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Eye,
  EyeOff,
  Globe,
  Link2,
  Pencil,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  Trash2,
  Upload,
} from "lucide-react"
import { uploadWebsiteAsset } from "@/api/websiteConfig"
import { createWebsiteCaseStudy, pullCaseStudySnapshot } from "@/api/websiteCaseStudies"
import {
  createCaseStudyFromProgramApi,
  deleteCaseStudyApi,
  getCaseStudyDetailApi,
  listProgramCaseStudiesApi,
  publishCaseStudyApi,
  regenerateCaseStudyTokenApi,
  resetCaseStudyFieldApi,
  unpublishCaseStudyApi,
  updateCaseStudyApi,
  type HybridCaseStudy,
} from "@/api/programWebPages"
import { getCohortsApi } from "@/api/sessions/cohorts"
import { WEBSITE_BASE_URL } from "@/components/operations/OrgManagementModals"
import { resolveWebsiteAsset } from "@/pages/operations/website/WebsiteManagement"
import { SharePagePopover } from "@/pages/operations/website/components/SharePagePopover"
import { Spinner } from "@/pages/admin/components/common"
import type { Cohort } from "@/types/sessions"
import { useToast } from "@/components/ui/toast"
import { cn, getErrorMessage } from "@/lib/utils"

const CASE_STUDY_CATEGORIES = [
  "Challenges & Competitions",
  "National Programs",
  "Universities",
  "Roadshows",
  "STEM Programs",
  "Other",
]

const PARTNER_ROLE_PRESETS = [
  "In collaboration with",
  "In partnership with",
  "Program Initiative",
  "Academic Host",
  "Strategic Partner",
]

function CaseStudySection({
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
          {open ? (
            <ChevronDown size={14} className="text-primary" />
          ) : (
            <ChevronRight size={14} className="text-muted-foreground" />
          )}
          <span className="text-xs font-extrabold uppercase tracking-wider text-foreground">
            {title}
          </span>
        </div>
        {badge && <span className="text-[11px] font-semibold text-muted-foreground">{badge}</span>}
      </button>
      {open && <div className="px-4 pb-4 pt-2 space-y-3 border-t border-border/60">{children}</div>}
    </div>
  )
}

export function ProgramCaseStudiesPanel({
  programId,
  programName,
}: {
  programId: string
  programName: string
}) {
  const qc = useQueryClient()
  const toast = useToast()

  const [createOpen, setCreateOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)

  const { data: caseStudies = [], isLoading } = useQuery<HybridCaseStudy[]>({
    queryKey: ["program-case-studies", programId],
    queryFn: () => listProgramCaseStudiesApi(programId),
  })

  const { data: cohorts = [] } = useQuery<Cohort[]>({
    queryKey: ["program-cohorts-for-cs", programId],
    queryFn: () => getCohortsApi({ program_id: programId }),
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteCaseStudyApi(id),
    onSuccess: () => {
      toast.success("Case study deleted")
      void qc.invalidateQueries({ queryKey: ["program-case-studies", programId] })
    },
    onError: (e) => toast.error(getErrorMessage(e, "Could not delete case study")),
  })

  if (editingId) {
    return (
      <CaseStudySplitEditor
        caseStudyId={editingId}
        programId={programId}
        onBack={() => {
          setEditingId(null)
          void qc.invalidateQueries({ queryKey: ["program-case-studies", programId] })
        }}
      />
    )
  }

  return (
    <div className="space-y-4">
      <div className="rounded-[10px] border border-border bg-card p-5 flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-base font-bold text-foreground flex items-center gap-2">
          <Award size={16} className="text-primary" /> Case Studies ({caseStudies.length})
        </h3>
        <button
          type="button"
          onClick={() => setCreateOpen(true)}
          className="inline-flex items-center gap-1.5 h-9 px-4 rounded-[10px] bg-primary text-primary-foreground text-xs font-bold hover:opacity-90 transition-colors cursor-pointer"
        >
          <Plus size={14} /> Create Case Study
        </button>
      </div>

      {isLoading ? (
        <Spinner />
      ) : caseStudies.length === 0 ? (
        <div className="rounded-[10px] border border-dashed border-border bg-card p-10 text-center">
          <p className="text-sm font-bold text-foreground">No case studies yet</p>
          <button
            type="button"
            onClick={() => setCreateOpen(true)}
            className="mt-4 inline-flex items-center gap-1.5 h-9 px-4 rounded-[10px] bg-primary text-primary-foreground text-xs font-bold hover:opacity-90 transition-colors cursor-pointer"
          >
            <Plus size={14} /> Create Case Study
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {caseStudies.map((cs) => (
            <div
              key={cs.id}
              className="rounded-[10px] border border-border bg-card p-4 flex flex-col justify-between gap-3"
            >
              <div className="space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h4 className="text-sm font-bold text-foreground">{cs.title}</h4>
                    <div className="text-[11px] font-mono text-muted-foreground">
                      /case-studies?mission={cs.slug}
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    {cs.live_linked && (
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-[10px] bg-emerald-500/15 text-emerald-600 dark:text-emerald-400">
                        Live
                      </span>
                    )}
                    <span
                      className={cn(
                        "text-[10px] font-bold px-2 py-0.5 rounded-[10px]",
                        cs.is_published
                          ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
                          : "bg-muted text-muted-foreground",
                      )}
                    >
                      {cs.is_published ? "Published" : "Draft"}
                    </span>
                  </div>
                </div>
                {cs.card_summary && (
                  <p className="text-xs text-muted-foreground">{cs.card_summary}</p>
                )}
                <div className="flex flex-wrap gap-1.5">
                  {(cs.metrics || []).slice(0, 3).map((m, idx) => (
                    <span
                      key={idx}
                      className="text-[11px] px-2 py-0.5 rounded-[10px] bg-muted text-foreground font-semibold"
                    >
                      {m.value} {m.label}
                    </span>
                  ))}
                </div>
              </div>

              <div className="pt-3 border-t border-border flex items-center justify-between gap-2">
                <button
                  type="button"
                  onClick={() => {
                    if (window.confirm(`Delete case study "${cs.title}"?`)) {
                      deleteMut.mutate(cs.id)
                    }
                  }}
                  className="p-1.5 rounded-[10px] text-muted-foreground hover:text-rose-500 hover:bg-rose-500/10 transition-colors cursor-pointer"
                  title="Delete Case Study"
                >
                  <Trash2 size={14} />
                </button>
                <div className="flex items-center gap-2">
                  <SharePagePopover
                    publicUrl={`${WEBSITE_BASE_URL}/case-studies?mission=${cs.slug}`}
                    previewToken={cs.preview_token}
                    isPublished={cs.is_published}
                  />
                  <button
                    type="button"
                    onClick={() => setEditingId(cs.id)}
                    className="inline-flex items-center gap-1.5 h-8 px-3 rounded-[10px] bg-primary text-primary-foreground text-xs font-bold hover:opacity-90 transition-colors cursor-pointer"
                  >
                    <Pencil size={12} /> Open Editor
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {createOpen && (
        <CreateCaseStudyFromProgramModal
          programId={programId}
          programName={programName}
          cohorts={cohorts}
          onClose={() => setCreateOpen(false)}
          onCreated={(created) => {
            setCreateOpen(false)
            void qc.invalidateQueries({ queryKey: ["program-case-studies", programId] })
            setEditingId(created.id)
          }}
        />
      )}
    </div>
  )
}

export function CreateCaseStudyFromProgramModal({
  programId,
  programName,
  cohorts,
  onClose,
  onCreated,
}: {
  programId: string
  programName: string
  cohorts: Cohort[]
  onClose: () => void
  onCreated: (cs: HybridCaseStudy) => void
}) {
  const toast = useToast()
  const eligible = cohorts.filter(
    (c) =>
      String(c.status) !== "draft" &&
      String(c.status) !== "cancelled" &&
      !c.name.toLowerCase().startsWith("[template]"),
  )

  const [title, setTitle] = useState(programName)
  const [selectedIds, setSelectedIds] = useState<string[]>(() => eligible.map((c) => c.id))
  const [buckets, setBuckets] = useState<string[]>(["metrics", "structure", "curriculum", "partners"])

  const toggleCohort = (id: string) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  const moveCohort = (idx: number, dir: -1 | 1) => {
    setSelectedIds((prev) => {
      const next = [...prev]
      const target = idx + dir
      if (target < 0 || target >= next.length) return prev
      const [item] = next.splice(idx, 1)
      next.splice(target, 0, item)
      return next
    })
  }

  const toggleBucket = (b: string) => {
    setBuckets((prev) => (prev.includes(b) ? prev.filter((x) => x !== b) : [...prev, b]))
  }

  const mut = useMutation({
    mutationFn: () =>
      createCaseStudyFromProgramApi({
        program_id: programId,
        cohort_ids: selectedIds,
        title: title.trim() || undefined,
        include_buckets: buckets,
      }),
    onSuccess: (created) => {
      toast.success(`Draft case study "${created.title}" created`)
      onCreated(created)
    },
    onError: (e) => toast.error(getErrorMessage(e, "Could not create case study")),
  })

  const cohortMap = new Map(eligible.map((c) => [c.id, c]))

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="w-full max-w-xl max-h-[90vh] overflow-y-auto rounded-[10px] border border-border bg-card p-6 shadow-xl space-y-4">
        <h2 className="text-base font-bold text-foreground">Create Case Study: {programName}</h2>

        <label className="flex flex-col gap-1">
          <span className="text-xs font-semibold text-muted-foreground">Case Study Title</span>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Satty v1"
            className="h-9 rounded-[10px] border border-border bg-background px-3 text-sm"
          />
        </label>

        <div className="space-y-2">
          <span className="text-xs font-semibold text-muted-foreground block">
            Cohorts &amp; Stage Order ({selectedIds.length})
          </span>
          {selectedIds.length === 0 ? (
            <p className="text-xs text-muted-foreground">Select at least one cohort below.</p>
          ) : (
            <div className="space-y-1.5">
              {selectedIds.map((id, idx) => {
                const c = cohortMap.get(id)
                if (!c) return null
                return (
                  <div
                    key={id}
                    className="flex items-center justify-between gap-2 rounded-[10px] border border-primary/40 bg-primary/5 px-3 py-2 text-xs"
                  >
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono font-bold text-primary shrink-0">
                        Stage {String(idx + 1).padStart(2, "0")}
                      </span>
                      <span className="font-semibold text-foreground">{c.name}</span>
                      <span className="text-[10px] uppercase text-muted-foreground">{c.status}</span>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <button
                        type="button"
                        disabled={idx === 0}
                        onClick={() => moveCohort(idx, -1)}
                        className="p-1 rounded-[10px] border border-border bg-background disabled:opacity-30 cursor-pointer"
                      >
                        <ArrowUp size={12} />
                      </button>
                      <button
                        type="button"
                        disabled={idx === selectedIds.length - 1}
                        onClick={() => moveCohort(idx, 1)}
                        className="p-1 rounded-[10px] border border-border bg-background disabled:opacity-30 cursor-pointer"
                      >
                        <ArrowDown size={12} />
                      </button>
                      <button
                        type="button"
                        onClick={() => toggleCohort(id)}
                        className="p-1 rounded-[10px] border border-border bg-background text-rose-500 cursor-pointer"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {eligible.some((c) => !selectedIds.includes(c.id)) && (
            <div className="pt-2 space-y-1">
              <span className="text-[11px] font-semibold text-muted-foreground">Available Cohorts</span>
              <div className="flex flex-wrap gap-1.5">
                {eligible
                  .filter((c) => !selectedIds.includes(c.id))
                  .map((c) => (
                    <button
                      key={c.id}
                      type="button"
                      onClick={() => toggleCohort(c.id)}
                      className="inline-flex items-center gap-1 h-7 px-2.5 rounded-[10px] border border-border bg-background text-xs font-medium hover:bg-muted cursor-pointer"
                    >
                      <Plus size={11} /> {c.name}
                    </button>
                  ))}
              </div>
            </div>
          )}
        </div>

        <div className="space-y-1.5">
          <span className="text-xs font-semibold text-muted-foreground block">Live Data to Include</span>
          <div className="flex flex-wrap gap-2">
            {[
              { key: "metrics", label: "Impact Metrics" },
              { key: "structure", label: "Ordered Stages" },
              { key: "curriculum", label: "Curriculum" },
              { key: "partners", label: "Partner Info" },
            ].map((b) => {
              const active = buckets.includes(b.key)
              return (
                <button
                  key={b.key}
                  type="button"
                  onClick={() => toggleBucket(b.key)}
                  className={cn(
                    "h-8 px-3 rounded-[10px] border text-xs font-semibold cursor-pointer",
                    active
                      ? "border-primary bg-primary/10 text-foreground"
                      : "border-border bg-background text-muted-foreground",
                  )}
                >
                  {b.label}
                </button>
              )
            })}
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 pt-3 border-t border-border">
          <button
            type="button"
            onClick={onClose}
            className="h-9 px-4 rounded-[10px] border border-border bg-background text-xs font-semibold cursor-pointer"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={mut.isPending}
            onClick={() => mut.mutate()}
            className="h-9 px-4 rounded-[10px] bg-primary text-primary-foreground text-xs font-bold hover:opacity-90 cursor-pointer"
          >
            {mut.isPending ? "Creating…" : "Create Draft"}
          </button>
        </div>
      </div>
    </div>
  )
}

export function CaseStudySplitEditor({
  caseStudyId,
  programId,
  programs = [],
  cohorts = [],
  onBack,
  onCreated,
}: {
  caseStudyId: string | null
  programId?: string
  programs?: { id: string; name: string; code?: string | null }[]
  cohorts?: Cohort[]
  onBack: () => void
  onCreated?: (created: HybridCaseStudy) => void
}) {
  const qc = useQueryClient()
  const toast = useToast()
  const isCreating = !caseStudyId

  const { data: cs, isLoading } = useQuery<HybridCaseStudy>({
    queryKey: ["case-study-detail", caseStudyId],
    queryFn: () => getCaseStudyDetailApi(caseStudyId!),
    enabled: Boolean(caseStudyId),
  })

  // Standalone source linking
  const [sourceType, setSourceType] = useState<"manual" | "cohort" | "multi_cohort" | "program">("manual")
  const [srcProgramId, setSrcProgramId] = useState(programId || "")
  const [srcCohortId, setSrcCohortId] = useState("")
  const [srcCohortIds, setSrcCohortIds] = useState<string[]>([])
  const [pullingSnapshot, setPullingSnapshot] = useState(false)

  // 1. Basics & Show Card
  const [title, setTitle] = useState("")
  const [subtitle, setSubtitle] = useState("")
  const [slug, setSlug] = useState("")
  const [category, setCategory] = useState(programId ? "National Programs" : "Challenges & Competitions")
  const [displayOrder, setDisplayOrder] = useState(0)
  const [isFeatured, setIsFeatured] = useState(false)
  const [cardSummary, setCardSummary] = useState("")
  const [coverImageUrl, setCoverImageUrl] = useState("")
  const [partnerName, setPartnerName] = useState("")
  const [partnerLogoUrl, setPartnerLogoUrl] = useState("")

  // 2. Partners
  const [partners, setPartners] = useState<{ name: string; role?: string | null; logo_url?: string }[]>([])

  // 3. Overview & Impact Stats
  const [overviewText, setOverviewText] = useState("")
  const [heroMetricEnabled, setHeroMetricEnabled] = useState(false)
  const [heroMetricValue, setHeroMetricValue] = useState("")
  const [heroMetricLabel, setHeroMetricLabel] = useState("")
  const [metrics, setMetrics] = useState<{ value: string; label: string; is_hero?: boolean }[]>(() =>
    caseStudyId
      ? []
      : [
          { value: "500+", label: "Students Trained" },
          { value: "50", label: "Teams" },
        ],
  )

  // 4. Gallery
  const [galleryImages, setGalleryImages] = useState<string[]>([])

  // 5. Highlights & Chapters
  const [highlights, setHighlights] = useState<{ title: string; description?: string; icon?: string }[]>([])
  const [curriculumChapters, setCurriculumChapters] = useState<{ chapter_num: string; title: string; icon?: string }[]>([])

  // 6. Structure & Formats
  const [structureTitle, setStructureTitle] = useState("Program Structure & Formats")
  const [structureSections, setStructureSections] = useState<
    {
      id?: string
      badge?: string
      title: string
      subtitle?: string | null
      image_url?: string | null
      items?: { title: string; description?: string }[]
      days?: { day_title: string; milestones: string[] }[]
    }[]
  >([])

  // 7. Visibility & Spotlights
  const [visibilityStats, setVisibilityStats] = useState<{ value: string; label: string; icon?: string }[]>([])
  const [spotlights, setSpotlights] = useState<
    { type?: string; tag?: string; title?: string; subtitle?: string; content?: string; logo_url?: string; images?: string[] }[]
  >([])

  // 8. Testimonials & CTA & Section Visibility
  const [testimonials, setTestimonials] = useState<
    { badge?: string; quote: string; author_name: string; author_role?: string; author_photo_url?: string }[]
  >([])
  const [ctaLabel, setCtaLabel] = useState("")
  const [ctaUrl, setCtaUrl] = useState("")
  const [hiddenSections, setHiddenSections] = useState<string[]>([])

  // Uploads & iframe
  const [uploadingCover, setUploadingCover] = useState(false)
  const [uploadingPartnerBadge, setUploadingPartnerBadge] = useState(false)
  const [uploadingPartnerIdx, setUploadingPartnerIdx] = useState<number | null>(null)
  const [uploadingGallery, setUploadingGallery] = useState(false)
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const [iframeReady, setIframeReady] = useState(false)

  useEffect(() => {
    const onMsg = (e: MessageEvent) => {
      if (e.data?.type === "SP_PREVIEW_READY") setIframeReady(true)
    }
    window.addEventListener("message", onMsg)
    return () => window.removeEventListener("message", onMsg)
  }, [])

  useEffect(() => {
    if (!cs) return
    setSourceType(((cs.source_type as any) || "manual"))
    setSrcProgramId(cs.program_id || programId || "")
    setSrcCohortId(cs.cohort_id || "")
    setSrcCohortIds(Array.isArray(cs.cohort_ids) ? [...cs.cohort_ids] : [])
    setTitle(cs.title || "")
    setSubtitle(cs.subtitle || "")
    setSlug(cs.slug || "")
    setCategory(cs.category || (programId ? "National Programs" : "Challenges & Competitions"))
    setDisplayOrder(cs.display_order ?? 0)
    setIsFeatured(Boolean(cs.is_featured))
    setCardSummary(cs.card_summary || "")
    setCoverImageUrl(cs.cover_image_url || "")
    setPartnerName(cs.partner_name || "")
    setPartnerLogoUrl(cs.partner_logo_url || "")
    setPartners(Array.isArray(cs.partners) ? cs.partners.map((p) => ({ ...p })) : [])
    setOverviewText(cs.overview_text || "")
    setHeroMetricEnabled(Boolean(cs.hero_metric_enabled))
    setHeroMetricValue(cs.hero_metric_value || "")
    setHeroMetricLabel(cs.hero_metric_label || "")
    setMetrics(Array.isArray(cs.metrics) ? cs.metrics.map((m) => ({ ...m })) : [])
    setGalleryImages(Array.isArray(cs.gallery_images) ? [...cs.gallery_images] : [])
    setHighlights(Array.isArray(cs.highlights) ? cs.highlights.map((h) => ({ ...h })) : [])
    setCurriculumChapters(
      Array.isArray(cs.curriculum_chapters) ? cs.curriculum_chapters.map((c) => ({ ...c })) : [],
    )
    setStructureTitle(cs.structure_title || "Program Structure & Formats")
    setStructureSections(
      Array.isArray(cs.structure_sections) ? cs.structure_sections.map((s) => ({ ...s })) : [],
    )
    setVisibilityStats(Array.isArray(cs.visibility_stats) ? cs.visibility_stats.map((v) => ({ ...v })) : [])
    setSpotlights(Array.isArray(cs.spotlights) ? cs.spotlights.map((sp) => ({ ...sp })) : [])
    setTestimonials(Array.isArray(cs.testimonials) ? cs.testimonials.map((t) => ({ ...t })) : [])
    setCtaLabel(cs.cta_label || "")
    setCtaUrl(cs.cta_url || "")
    setHiddenSections(Array.isArray(cs.hidden_sections) ? [...cs.hidden_sections] : [])
  }, [cs, programId])

  const liveCsData = useMemo(() => {
    if (!isCreating && !cs) return null
    const hid = new Set(hiddenSections)
    const activeMetrics = hid.has("metrics") ? [] : metrics
    return {
      ...(cs || {}),
      slug: slug || cs?.slug || "draft-case-study",
      title: title || cs?.title || "Untitled Case Study",
      subtitle: subtitle || null,
      category,
      display_order: displayOrder,
      is_featured: isFeatured,
      card_summary: cardSummary,
      cover_image_url: coverImageUrl,
      partner_name: partnerName || null,
      partner_logo_url: partnerLogoUrl || null,
      partners: hid.has("partners") ? [] : partners.filter((p) => p.name.trim()),
      overview_text: overviewText || null,
      hero_metric_enabled: heroMetricEnabled,
      hero_metric_value: heroMetricValue || null,
      hero_metric_label: heroMetricLabel || null,
      metrics: activeMetrics,
      card_metrics: activeMetrics.slice(0, 2),
      gallery_images: hid.has("gallery") ? [] : galleryImages.filter((u) => u.trim()),
      highlights: highlights.filter((h) => h.title.trim() || (h.description || "").trim()),
      curriculum_chapters: hid.has("curriculum")
        ? []
        : curriculumChapters.filter((ch) => ch.title.trim()),
      structure_title: structureTitle || null,
      structure_sections: hid.has("structure")
        ? []
        : structureSections.filter((s) => s.title.trim()),
      visibility_stats: visibilityStats.filter((v) => v.value.trim() || v.label.trim()),
      spotlights: spotlights.filter((sp) => (sp.title || "").trim() || (sp.content || "").trim()),
      testimonials: hid.has("testimonials")
        ? []
        : testimonials.filter((t) => t.quote.trim() || t.author_name.trim()),
      cta_label: ctaLabel || null,
      cta_url: ctaUrl || null,
    }
  }, [
    isCreating,
    cs,
    slug,
    title,
    subtitle,
    category,
    displayOrder,
    isFeatured,
    cardSummary,
    coverImageUrl,
    partnerName,
    partnerLogoUrl,
    partners,
    overviewText,
    heroMetricEnabled,
    heroMetricValue,
    heroMetricLabel,
    metrics,
    galleryImages,
    highlights,
    curriculumChapters,
    structureTitle,
    structureSections,
    visibilityStats,
    spotlights,
    testimonials,
    ctaLabel,
    ctaUrl,
    hiddenSections,
  ])

  useEffect(() => {
    if (!liveCsData || !iframeRef.current?.contentWindow) return
    iframeRef.current.contentWindow.postMessage(
      {
        type: "SP_LIVE_PREVIEW",
        kind: "case_study",
        is_published: Boolean(cs?.is_published),
        data: liveCsData,
      },
      "*",
    )
  }, [liveCsData, iframeReady, cs?.is_published])

  const invalidate = () => {
    if (caseStudyId) void qc.invalidateQueries({ queryKey: ["case-study-detail", caseStudyId] })
    if (programId) void qc.invalidateQueries({ queryKey: ["program-case-studies", programId] })
    void qc.invalidateQueries({ queryKey: ["admin-case-studies"] })
    void qc.invalidateQueries({ queryKey: ["website-case-studies"] })
  }

  const handlePullSnapshot = async () => {
    if (sourceType === "manual") return
    setPullingSnapshot(true)
    try {
      const snap = await pullCaseStudySnapshot({
        source_type: sourceType,
        program_id: srcProgramId || null,
        cohort_id: srcCohortId || null,
        cohort_ids: srcCohortIds,
      })
      if (snap.title && !title) setTitle(snap.title)
      if (snap.subtitle && !subtitle) setSubtitle(snap.subtitle)
      if (snap.category) setCategory(snap.category)
      if (snap.card_summary && !cardSummary) setCardSummary(snap.card_summary)
      if (snap.overview_text && !overviewText) setOverviewText(snap.overview_text)
      if (snap.partner_name && !partnerName) setPartnerName(snap.partner_name)
      if (snap.partner_logo_url && !partnerLogoUrl) setPartnerLogoUrl(snap.partner_logo_url)
      if (Array.isArray(snap.partners) && snap.partners.length) {
        setPartners(snap.partners.map((p) => ({ name: p.name, role: p.role, logo_url: p.logo_url || "" })))
      }
      if (Array.isArray(snap.metrics) && snap.metrics.length) {
        setMetrics(snap.metrics.map((m) => ({ value: m.value, label: m.label, is_hero: Boolean(m.is_hero) })))
      }
      if (Array.isArray(snap.curriculum_chapters) && snap.curriculum_chapters.length) {
        setCurriculumChapters(
          snap.curriculum_chapters.map((ch) => ({
            chapter_num: ch.chapter_num,
            title: ch.title,
            icon: ch.icon ?? undefined,
          })),
        )
      }
      if (Array.isArray(snap.structure_sections) && snap.structure_sections.length) {
        setStructureSections(
          snap.structure_sections.map((s) => ({
            id: s.id ?? undefined,
            badge: s.badge ?? undefined,
            title: s.title,
            subtitle: s.subtitle ?? null,
            image_url: s.image_url ?? null,
            items: Array.isArray(s.items)
              ? s.items.map((it) => ({ title: it.title, description: it.description ?? undefined }))
              : undefined,
            days: Array.isArray(s.days) ? s.days.map((d) => ({ ...d })) : undefined,
          })),
        )
      }
      toast.success("Portal snapshot pulled")
    } catch (err) {
      toast.error(getErrorMessage(err, "Failed to pull portal snapshot"))
    } finally {
      setPullingSnapshot(false)
    }
  }

  const saveMut = useMutation({
    mutationFn: () => {
      if (!title.trim() && !cs?.title) throw new Error("Mission title is required")
      const cleanMetrics = metrics.filter((m) => m.value.trim() || m.label.trim())
      const cleanPartners = partners.filter((p) => p.name.trim())
      const cleanChapters = curriculumChapters.filter((ch) => ch.title.trim())
      const cleanStructure = structureSections.filter((s) => s.title.trim())
      const commonPayload = {
        slug: slug.trim() || undefined,
        title: title.trim() || cs?.title || "",
        subtitle: subtitle.trim() || null,
        category,
        display_order: Number(displayOrder) || 0,
        is_featured: isFeatured,
        card_summary: cardSummary.trim(),
        cover_image_url: coverImageUrl.trim(),
        partner_name: partnerName.trim() || null,
        partner_logo_url: partnerLogoUrl.trim() || null,
        source_type: programId ? cs?.source_type || "program" : sourceType,
        program_id: programId || (sourceType === "program" ? srcProgramId || null : cs?.program_id || null),
        cohort_id: sourceType === "cohort" ? srcCohortId || null : null,
        cohort_ids: sourceType === "multi_cohort" ? srcCohortIds : cs?.cohort_ids || [],
        partners: cleanPartners,
        overview_text: overviewText.trim() || null,
        hero_metric_enabled: heroMetricEnabled,
        hero_metric_value: heroMetricValue.trim() || null,
        hero_metric_label: heroMetricLabel.trim() || null,
        metrics: cleanMetrics,
        card_metrics: cleanMetrics.slice(0, 2),
        gallery_images: galleryImages.filter((u) => u.trim()),
        highlights: highlights.filter((h) => h.title.trim() || (h.description || "").trim()),
        curriculum_chapters: cleanChapters,
        structure_title: structureTitle.trim() || null,
        structure_sections: cleanStructure,
        visibility_stats: visibilityStats.filter((v) => v.value.trim() || v.label.trim()),
        spotlights: spotlights.filter((sp) => (sp.title || "").trim() || (sp.content || "").trim()),
        testimonials: testimonials.filter((t) => t.quote.trim() || t.author_name.trim()),
        cta_label: ctaLabel.trim() || null,
        cta_url: ctaUrl.trim() || null,
        hidden_sections: hiddenSections,
      }

      if (!caseStudyId) {
        return createWebsiteCaseStudy({
          ...commonPayload,
          is_published: false,
        } as any) as Promise<HybridCaseStudy>
      }

      if (!cs) throw new Error("Not loaded")
      const nextOverrides: Record<string, any> = {}
      if (cs.live_linked) {
        const liveTrack: [string, any][] = [
          ["title", title.trim() || cs.title],
          ["subtitle", subtitle.trim() || null],
          ["category", category],
          ["card_summary", cardSummary.trim()],
          ["overview_text", overviewText.trim() || null],
          ["partner_name", partnerName.trim() || null],
          ["partners", cleanPartners],
          ["metrics", cleanMetrics],
          ["card_metrics", cleanMetrics.slice(0, 2)],
          ["curriculum_chapters", cleanChapters],
          ["structure_sections", cleanStructure],
        ]
        for (const [key, val] of liveTrack) {
          const liveVal = cs.field_states?.[key]?.live
          if (JSON.stringify(val ?? null) !== JSON.stringify(liveVal ?? null)) {
            nextOverrides[key] = val
          }
        }
      }

      return updateCaseStudyApi(caseStudyId, {
        ...commonPayload,
        overrides: nextOverrides,
      })
    },
    onSuccess: (saved) => {
      toast.success(isCreating ? "Case study draft created" : "Case study saved")
      invalidate()
      if (isCreating && saved) onCreated?.(saved)
    },
    onError: (e) => toast.error(getErrorMessage(e, "Could not save case study")),
  })

  const resetMut = useMutation({
    mutationFn: (field: string) => {
      if (!caseStudyId) throw new Error("Not saved yet")
      return resetCaseStudyFieldApi(caseStudyId, field)
    },
    onSuccess: () => {
      toast.success("Reset to live portal value")
      invalidate()
    },
    onError: (e) => toast.error(getErrorMessage(e, "Could not reset field")),
  })

  const pubMut = useMutation({
    mutationFn: () => {
      if (!caseStudyId) throw new Error("Save draft before publishing")
      return cs?.is_published ? unpublishCaseStudyApi(caseStudyId) : publishCaseStudyApi(caseStudyId)
    },
    onSuccess: (updated) => {
      toast.success(updated.is_published ? "Case study published!" : "Case study unpublished")
      invalidate()
    },
    onError: (e) => toast.error(getErrorMessage(e, "Could not update status")),
  })

  const regenMut = useMutation({
    mutationFn: () => {
      if (!caseStudyId) throw new Error("Save draft first")
      return regenerateCaseStudyTokenApi(caseStudyId)
    },
    onSuccess: () => {
      toast.success("Preview link regenerated")
      invalidate()
    },
    onError: (e) => toast.error(getErrorMessage(e, "Could not regenerate link")),
  })

  const toggleSectionHidden = (sec: string) => {
    setHiddenSections((prev) =>
      prev.includes(sec) ? prev.filter((s) => s !== sec) : [...prev, sec],
    )
  }

  if (!isCreating && (isLoading || !cs)) return <Spinner />

  const currentSlug = slug || cs?.slug || "draft-case-study"
  const publicUrl = `${WEBSITE_BASE_URL}/case-studies?mission=${currentSlug}`
  const iframeUrl = cs?.preview_token
    ? `${WEBSITE_BASE_URL}/preview?t=${cs.preview_token}&embed=1`
    : `${WEBSITE_BASE_URL}/preview?embed=1`

  const renderBadge = (field: string) => {
    const src = cs?.field_states?.[field]?.source
    if (!src) return null
    if (src === "override") {
      return (
        <span className="inline-flex items-center gap-1.5">
          <span className="text-[10px] font-bold px-2 py-0.5 rounded-[10px] bg-primary/15 text-primary">
            Overridden
          </span>
          <button
            type="button"
            onClick={() => resetMut.mutate(field)}
            className="text-[10px] font-semibold text-primary hover:underline inline-flex items-center gap-0.5 cursor-pointer"
          >
            <RotateCcw size={9} /> Reset
          </button>
        </span>
      )
    }
    return (
      <span className="text-[10px] font-bold px-2 py-0.5 rounded-[10px] bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 inline-flex items-center gap-1">
        <Link2 size={9} /> Live
      </span>
    )
  }

  return (
    <div className="space-y-4">
      {/* Top Action Bar */}
      <div className="rounded-[10px] border border-border bg-card px-4 py-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5 flex-wrap">
          <button
            type="button"
            onClick={onBack}
            className="inline-flex items-center gap-1 h-8 px-2.5 rounded-[10px] border border-border bg-background text-xs font-semibold hover:bg-muted cursor-pointer"
          >
            <ArrowLeft size={13} /> Back
          </button>
          <span className="text-sm font-bold text-foreground">
            {title || cs?.title || "New Case Study"}
          </span>
          <span
            className={cn(
              "text-[11px] font-bold px-2 py-0.5 rounded-[10px] inline-flex items-center gap-1",
              cs?.is_published
                ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
                : "bg-muted text-muted-foreground",
            )}
          >
            {cs?.is_published ? <CheckCircle2 size={11} /> : null}
            {cs?.is_published ? "Published" : "Draft"}
          </span>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {cs && (
            <SharePagePopover
              publicUrl={publicUrl}
              previewToken={cs.preview_token}
              isPublished={cs.is_published}
              onRegenerate={() => regenMut.mutate()}
              regenerating={regenMut.isPending}
            />
          )}
          <button
            type="button"
            disabled={saveMut.isPending}
            onClick={() => saveMut.mutate()}
            className="inline-flex items-center gap-1.5 h-8 px-3 rounded-[10px] border border-border bg-background text-xs font-bold hover:bg-muted cursor-pointer"
          >
            <Save size={13} /> {saveMut.isPending ? "Saving…" : isCreating ? "Create Draft" : "Save"}
          </button>
          {!isCreating && cs && (
            <button
              type="button"
              disabled={pubMut.isPending}
              onClick={() => pubMut.mutate()}
              className={cn(
                "inline-flex items-center gap-1.5 h-8 px-3.5 rounded-[10px] text-xs font-bold cursor-pointer",
                cs.is_published
                  ? "border border-rose-500/40 bg-rose-500/10 text-rose-600 dark:text-rose-400"
                  : "bg-primary text-primary-foreground hover:opacity-90",
              )}
            >
              {cs.is_published ? <EyeOff size={13} /> : <Globe size={13} />}
              {cs.is_published ? "Unpublish" : "Publish Live"}
            </button>
          )}
        </div>
      </div>

      {/* Split Screen */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5 items-start">
        {/* LEFT HALF: ALL 8 CASE STUDY SECTIONS */}
        <div className="space-y-3">
          {/* 1. Basics & Show Card */}
          <CaseStudySection title="1. Basics & Show Card" defaultOpen>
            {!programId && (programs.length > 0 || cohorts.length > 0) && (
              <div className="rounded-[10px] border border-border bg-background p-3 space-y-2.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-xs font-semibold text-muted-foreground">Portal Source</span>
                  {sourceType !== "manual" && (
                    <button
                      type="button"
                      disabled={pullingSnapshot}
                      onClick={() => handlePullSnapshot()}
                      className="inline-flex items-center gap-1 h-7 px-2.5 rounded-[10px] border border-primary/40 bg-primary/10 text-[11px] font-semibold text-primary hover:bg-primary/20 cursor-pointer disabled:opacity-50"
                    >
                      <RefreshCw size={11} className={pullingSnapshot ? "animate-spin" : ""} />
                      {pullingSnapshot ? "Pulling…" : "Pull Snapshot"}
                    </button>
                  )}
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                  <select
                    value={sourceType}
                    onChange={(e) => setSourceType(e.target.value as any)}
                    className="h-9 rounded-[10px] border border-border bg-card px-3 text-xs"
                  >
                    <option value="manual">Manual Standalone</option>
                    <option value="program">Program Aggregate</option>
                    <option value="cohort">Single Cohort</option>
                    <option value="multi_cohort">Multi-Cohort</option>
                  </select>
                  {sourceType === "program" && (
                    <select
                      value={srcProgramId}
                      onChange={(e) => setSrcProgramId(e.target.value)}
                      className="h-9 rounded-[10px] border border-border bg-card px-3 text-xs"
                    >
                      <option value="">Select Program…</option>
                      {programs.map((pr) => (
                        <option key={pr.id} value={pr.id}>
                          {pr.name}
                        </option>
                      ))}
                    </select>
                  )}
                  {sourceType === "cohort" && (
                    <select
                      value={srcCohortId}
                      onChange={(e) => setSrcCohortId(e.target.value)}
                      className="h-9 rounded-[10px] border border-border bg-card px-3 text-xs"
                    >
                      <option value="">Select Cohort…</option>
                      {cohorts.map((ch) => (
                        <option key={ch.id} value={ch.id}>
                          {ch.name}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
                {sourceType === "multi_cohort" && cohorts.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {cohorts.map((ch) => {
                      const active = srcCohortIds.includes(ch.id)
                      return (
                        <button
                          key={ch.id}
                          type="button"
                          onClick={() =>
                            setSrcCohortIds((prev) =>
                              active ? prev.filter((id) => id !== ch.id) : [...prev, ch.id],
                            )
                          }
                          className={cn(
                            "h-7 px-2.5 rounded-[10px] border text-[11px] font-semibold cursor-pointer",
                            active
                              ? "border-primary bg-primary/15 text-primary"
                              : "border-border bg-card text-muted-foreground",
                          )}
                        >
                          {ch.name}
                        </button>
                      )
                    })}
                  </div>
                )}
              </div>
            )}

            <label className="flex flex-col gap-1">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-muted-foreground">Mission Title</span>
                {renderBadge("title")}
              </div>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="h-9 rounded-[10px] border border-border bg-background px-3 text-sm font-medium"
              />
            </label>

            <label className="flex flex-col gap-1">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-muted-foreground">Subtitle / Tagline</span>
                {renderBadge("subtitle")}
              </div>
              <input
                type="text"
                value={subtitle}
                onChange={(e) => setSubtitle(e.target.value)}
                className="h-9 rounded-[10px] border border-border bg-background px-3 text-xs"
              />
            </label>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <label className="flex flex-col gap-1">
                <span className="text-xs font-semibold text-muted-foreground">URL Slug</span>
                <input
                  type="text"
                  value={slug}
                  onChange={(e) => setSlug(e.target.value)}
                  className="h-9 rounded-[10px] border border-border bg-background px-3 font-mono text-xs"
                />
              </label>
              <label className="flex flex-col gap-1">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-muted-foreground">Category</span>
                  {renderBadge("category")}
                </div>
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="h-9 rounded-[10px] border border-border bg-background px-3 text-xs"
                >
                  {CASE_STUDY_CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs font-semibold text-muted-foreground">Display Order</span>
                <input
                  type="number"
                  value={displayOrder}
                  onChange={(e) => setDisplayOrder(Number(e.target.value))}
                  className="h-9 rounded-[10px] border border-border bg-background px-3 text-xs"
                />
              </label>
            </div>

            <label className="flex flex-col gap-1">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-muted-foreground">Card Summary</span>
                {renderBadge("card_summary")}
              </div>
              <textarea
                rows={2}
                value={cardSummary}
                onChange={(e) => setCardSummary(e.target.value)}
                className="rounded-[10px] border border-border bg-background p-2.5 text-xs resize-none"
              />
            </label>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {/* Cover Image */}
              <div className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-muted-foreground">Cover Photo</span>
                  <label className="inline-flex items-center gap-1 text-[11px] font-semibold text-primary hover:underline cursor-pointer">
                    <Upload size={11} />
                    <span>{uploadingCover ? "Uploading…" : "Upload"}</span>
                    <input
                      type="file"
                      accept="image/*"
                      className="hidden"
                      disabled={uploadingCover}
                      onChange={async (e) => {
                        const f = e.target.files?.[0]
                        if (!f) return
                        e.target.value = ""
                        setUploadingCover(true)
                        try {
                          const res = await uploadWebsiteAsset(f)
                          setCoverImageUrl(res.url)
                          toast.success("Cover image uploaded")
                        } catch (err) {
                          toast.error(getErrorMessage(err, "Upload failed"))
                        } finally {
                          setUploadingCover(false)
                        }
                      }}
                    />
                  </label>
                </div>
                <input
                  type="text"
                  value={coverImageUrl}
                  onChange={(e) => setCoverImageUrl(e.target.value)}
                  placeholder="/assets/img/..."
                  className="h-9 rounded-[10px] border border-border bg-background px-3 text-xs"
                />
                {coverImageUrl && (
                  <div className="h-20 rounded-[10px] overflow-hidden border border-border bg-black/40">
                    <img
                      src={resolveWebsiteAsset(coverImageUrl)}
                      alt=""
                      className="w-full h-full object-cover"
                    />
                  </div>
                )}
              </div>

              {/* Primary Partner Card Badge */}
              <div className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-muted-foreground">Primary Partner (Card Badge)</span>
                  {renderBadge("partner_name")}
                </div>
                <input
                  type="text"
                  value={partnerName}
                  onChange={(e) => setPartnerName(e.target.value)}
                  placeholder="Partner Name"
                  className="h-9 rounded-[10px] border border-border bg-background px-3 text-xs"
                />
                <div className="flex gap-1.5">
                  <input
                    type="text"
                    value={partnerLogoUrl}
                    onChange={(e) => setPartnerLogoUrl(e.target.value)}
                    placeholder="Partner Logo URL"
                    className="flex-1 h-8 rounded-[10px] border border-border bg-background px-2.5 text-xs"
                  />
                  <label className="inline-flex items-center gap-1 h-8 px-2.5 rounded-[10px] border border-border bg-background text-xs font-semibold hover:bg-muted cursor-pointer shrink-0">
                    <Upload size={11} />
                    <span>{uploadingPartnerBadge ? "…" : "Logo"}</span>
                    <input
                      type="file"
                      accept="image/*"
                      className="hidden"
                      disabled={uploadingPartnerBadge}
                      onChange={async (e) => {
                        const f = e.target.files?.[0]
                        if (!f) return
                        e.target.value = ""
                        setUploadingPartnerBadge(true)
                        try {
                          const res = await uploadWebsiteAsset(f)
                          setPartnerLogoUrl(res.url)
                          toast.success("Partner logo uploaded")
                        } catch (err) {
                          toast.error(getErrorMessage(err, "Upload failed"))
                        } finally {
                          setUploadingPartnerBadge(false)
                        }
                      }}
                    />
                  </label>
                </div>
              </div>
            </div>

            <label className="inline-flex items-center gap-2 text-xs font-semibold text-foreground cursor-pointer pt-1">
              <input
                type="checkbox"
                checked={isFeatured}
                onChange={(e) => setIsFeatured(e.target.checked)}
              />
              Default Featured Mission on Case Studies Page
            </label>
          </CaseStudySection>

          {/* 2. Partners & Collabs */}
          <CaseStudySection
            title="2. Partners & Collabs"
            badge={`${partners.length} partners`}
          >
            <div className="flex items-center justify-between">
              {renderBadge("partners")}
              <button
                type="button"
                onClick={() =>
                  setPartners((p) => [...p, { name: "", role: "In collaboration with", logo_url: "" }])
                }
                className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline cursor-pointer ml-auto"
              >
                <Plus size={12} /> Add Partner
              </button>
            </div>
            {partners.map((pt, i) => (
              <div key={i} className="rounded-[10px] border border-border bg-background p-3 space-y-2">
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={pt.name}
                    onChange={(e) =>
                      setPartners((p) => p.map((x, idx) => (idx === i ? { ...x, name: e.target.value } : x)))
                    }
                    placeholder="Organization Name"
                    className="flex-1 h-8 rounded-[10px] border border-border bg-card px-2.5 text-xs font-semibold"
                  />
                  <button
                    type="button"
                    onClick={() => setPartners((p) => p.filter((_, idx) => idx !== i))}
                    className="p-1.5 text-muted-foreground hover:text-rose-500 cursor-pointer"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
                <input
                  type="text"
                  value={pt.role || ""}
                  onChange={(e) =>
                    setPartners((p) => p.map((x, idx) => (idx === i ? { ...x, role: e.target.value } : x)))
                  }
                  placeholder="Role"
                  className="w-full h-8 rounded-[10px] border border-border bg-card px-2.5 text-xs"
                />
                <div className="flex flex-wrap gap-1">
                  {PARTNER_ROLE_PRESETS.map((tag) => (
                    <button
                      key={tag}
                      type="button"
                      onClick={() =>
                        setPartners((p) => p.map((x, idx) => (idx === i ? { ...x, role: tag } : x)))
                      }
                      className="text-[10px] px-2 py-0.5 rounded-[10px] border border-border bg-card text-muted-foreground hover:text-foreground cursor-pointer"
                    >
                      {tag}
                    </button>
                  ))}
                </div>
                <div className="flex gap-1.5 items-center">
                  <input
                    type="text"
                    value={pt.logo_url || ""}
                    onChange={(e) =>
                      setPartners((p) => p.map((x, idx) => (idx === i ? { ...x, logo_url: e.target.value } : x)))
                    }
                    placeholder="Logo URL"
                    className="flex-1 h-8 rounded-[10px] border border-border bg-card px-2.5 text-xs"
                  />
                  <label className="inline-flex items-center gap-1 h-8 px-2.5 rounded-[10px] border border-border bg-card text-xs font-semibold hover:bg-muted cursor-pointer">
                    <Upload size={11} />
                    <span>{uploadingPartnerIdx === i ? "…" : "Upload"}</span>
                    <input
                      type="file"
                      accept="image/*"
                      className="hidden"
                      onChange={async (e) => {
                        const f = e.target.files?.[0]
                        if (!f) return
                        e.target.value = ""
                        setUploadingPartnerIdx(i)
                        try {
                          const res = await uploadWebsiteAsset(f)
                          setPartners((p) => p.map((x, idx) => (idx === i ? { ...x, logo_url: res.url } : x)))
                          toast.success("Partner logo uploaded")
                        } catch (err) {
                          toast.error(getErrorMessage(err, "Upload failed"))
                        } finally {
                          setUploadingPartnerIdx(null)
                        }
                      }}
                    />
                  </label>
                </div>
              </div>
            ))}
          </CaseStudySection>

          {/* 3. Overview & Impact Stats */}
          <CaseStudySection
            title="3. Overview & Impact Stats"
            badge={`${metrics.length} stats`}
            defaultOpen
          >
            <label className="flex flex-col gap-1">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-muted-foreground">Mission Overview</span>
                {renderBadge("overview_text")}
              </div>
              <textarea
                rows={4}
                value={overviewText}
                onChange={(e) => setOverviewText(e.target.value)}
                className="rounded-[10px] border border-border bg-background p-2.5 text-xs resize-y"
              />
            </label>

            <div className="rounded-[10px] border border-border bg-background p-3 space-y-2">
              <label className="flex items-center justify-between text-xs font-bold text-foreground cursor-pointer">
                <span>Hero Impact Highlight</span>
                <input
                  type="checkbox"
                  checked={heroMetricEnabled}
                  onChange={(e) => setHeroMetricEnabled(e.target.checked)}
                />
              </label>
              {heroMetricEnabled && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <input
                    type="text"
                    value={heroMetricValue}
                    onChange={(e) => setHeroMetricValue(e.target.value)}
                    placeholder="504 out of 520"
                    className="h-8 rounded-[10px] border border-border bg-card px-2.5 text-xs font-bold"
                  />
                  <input
                    type="text"
                    value={heroMetricLabel}
                    onChange={(e) => setHeroMetricLabel(e.target.value)}
                    placeholder="Students Trained"
                    className="h-8 rounded-[10px] border border-border bg-card px-2.5 text-xs"
                  />
                </div>
              )}
            </div>

            <div className="space-y-2 pt-2 border-t border-border/60">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-foreground">Metrics &amp; Show Card Stats</span>
                  {renderBadge("metrics")}
                </div>
                <button
                  type="button"
                  onClick={() => setMetrics((p) => [...p, { value: "", label: "" }])}
                  className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline cursor-pointer"
                >
                  <Plus size={12} /> Add Stat
                </button>
              </div>
              {metrics.map((m, i) => (
                <div key={i} className="flex items-center gap-2">
                  <span className="text-[11px] font-mono text-muted-foreground w-6 text-center">
                    #{i + 1}
                  </span>
                  <input
                    type="text"
                    value={m.value}
                    onChange={(e) =>
                      setMetrics((p) => p.map((x, idx) => (idx === i ? { ...x, value: e.target.value } : x)))
                    }
                    placeholder="Value"
                    className="w-28 h-8 rounded-[10px] border border-border bg-background px-2.5 text-xs font-bold"
                  />
                  <input
                    type="text"
                    value={m.label}
                    onChange={(e) =>
                      setMetrics((p) => p.map((x, idx) => (idx === i ? { ...x, label: e.target.value } : x)))
                    }
                    placeholder="Label"
                    className="flex-1 h-8 rounded-[10px] border border-border bg-background px-2.5 text-xs"
                  />
                  {i < 2 && (
                    <span className="text-[10px] px-2 py-0.5 rounded-[10px] bg-primary/15 text-primary font-semibold shrink-0">
                      Card #{i + 1}
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={() => setMetrics((p) => p.filter((_, idx) => idx !== i))}
                    className="p-1 text-muted-foreground hover:text-rose-500 cursor-pointer"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              ))}
            </div>
          </CaseStudySection>

          {/* 4. Gallery */}
          <CaseStudySection title="4. Gallery Photos" badge={`${galleryImages.length} photos`}>
            <div className="flex items-center justify-end gap-2">
              <label className="inline-flex items-center gap-1.5 h-8 px-3 rounded-[10px] bg-primary text-primary-foreground text-xs font-semibold cursor-pointer">
                <Upload size={12} />
                <span>{uploadingGallery ? "Uploading…" : "Upload Photo"}</span>
                <input
                  type="file"
                  accept="image/*"
                  className="hidden"
                  disabled={uploadingGallery}
                  onChange={async (e) => {
                    const f = e.target.files?.[0]
                    if (!f) return
                    e.target.value = ""
                    setUploadingGallery(true)
                    try {
                      const res = await uploadWebsiteAsset(f)
                      setGalleryImages((p) => [...p, res.url])
                      toast.success("Photo added to gallery")
                    } catch (err) {
                      toast.error(getErrorMessage(err, "Upload failed"))
                    } finally {
                      setUploadingGallery(false)
                    }
                  }}
                />
              </label>
              <button
                type="button"
                onClick={() => setGalleryImages((p) => [...p, ""])}
                className="inline-flex items-center gap-1 h-8 px-3 rounded-[10px] border border-border bg-background text-xs font-semibold hover:bg-muted cursor-pointer"
              >
                <Plus size={12} /> Add URL
              </button>
            </div>
            <div className="space-y-2">
              {galleryImages.map((img, i) => (
                <div key={i} className="flex items-center gap-2">
                  {img ? (
                    <img
                      src={resolveWebsiteAsset(img)}
                      alt=""
                      className="w-10 h-10 rounded-[10px] object-cover border border-border shrink-0"
                    />
                  ) : (
                    <div className="w-10 h-10 rounded-[10px] bg-muted shrink-0" />
                  )}
                  <input
                    type="text"
                    value={img}
                    onChange={(e) =>
                      setGalleryImages((p) => p.map((x, idx) => (idx === i ? e.target.value : x)))
                    }
                    placeholder="/assets/img/..."
                    className="flex-1 h-8 rounded-[10px] border border-border bg-background px-2.5 text-xs"
                  />
                  <button
                    type="button"
                    onClick={() => setGalleryImages((p) => p.filter((_, idx) => idx !== i))}
                    className="p-1.5 text-muted-foreground hover:text-rose-500 cursor-pointer"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              ))}
            </div>
          </CaseStudySection>

          {/* 5. Highlights & Curriculum Chapters */}
          <CaseStudySection
            title="5. Highlights & Curriculum"
            badge={`${highlights.length} highlights, ${curriculumChapters.length} modules`}
          >
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-foreground">Core Highlights</span>
                <button
                  type="button"
                  onClick={() => setHighlights((p) => [...p, { title: "", description: "" }])}
                  className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline cursor-pointer"
                >
                  <Plus size={12} /> Add Highlight
                </button>
              </div>
              {highlights.map((h, i) => (
                <div key={i} className="rounded-[10px] border border-border bg-background p-2.5 space-y-2">
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={h.title}
                      onChange={(e) =>
                        setHighlights((p) => p.map((x, idx) => (idx === i ? { ...x, title: e.target.value } : x)))
                      }
                      placeholder="Capability Title"
                      className="flex-1 h-8 rounded-[10px] border border-border bg-card px-2.5 text-xs font-semibold"
                    />
                    <button
                      type="button"
                      onClick={() => setHighlights((p) => p.filter((_, idx) => idx !== i))}
                      className="p-1 text-muted-foreground hover:text-rose-500 cursor-pointer"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                  <textarea
                    rows={2}
                    value={h.description || ""}
                    onChange={(e) =>
                      setHighlights((p) =>
                        p.map((x, idx) => (idx === i ? { ...x, description: e.target.value } : x)),
                      )
                    }
                    placeholder="Description..."
                    className="w-full rounded-[10px] border border-border bg-card p-2 text-xs resize-none"
                  />
                </div>
              ))}
            </div>

            <div className="space-y-2 pt-3 border-t border-border/60">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-foreground">Curriculum Modules</span>
                  {renderBadge("curriculum_chapters")}
                </div>
                <button
                  type="button"
                  onClick={() =>
                    setCurriculumChapters((p) => [...p, { chapter_num: `Ch. ${p.length + 1}`, title: "" }])
                  }
                  className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline cursor-pointer"
                >
                  <Plus size={12} /> Add Module
                </button>
              </div>
              {curriculumChapters.map((ch, i) => (
                <div key={i} className="flex items-center gap-2">
                  <input
                    type="text"
                    value={ch.chapter_num}
                    onChange={(e) =>
                      setCurriculumChapters((p) =>
                        p.map((x, idx) => (idx === i ? { ...x, chapter_num: e.target.value } : x)),
                      )
                    }
                    placeholder="Ch. 1"
                    className="w-20 h-8 rounded-[10px] border border-border bg-background px-2 text-xs font-bold text-primary"
                  />
                  <input
                    type="text"
                    value={ch.title}
                    onChange={(e) =>
                      setCurriculumChapters((p) =>
                        p.map((x, idx) => (idx === i ? { ...x, title: e.target.value } : x)),
                      )
                    }
                    placeholder="Module Title"
                    className="flex-1 h-8 rounded-[10px] border border-border bg-background px-2.5 text-xs"
                  />
                  <button
                    type="button"
                    onClick={() => setCurriculumChapters((p) => p.filter((_, idx) => idx !== i))}
                    className="p-1 text-muted-foreground hover:text-rose-500 cursor-pointer"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              ))}
            </div>
          </CaseStudySection>

          {/* 6. Structure & Formats */}
          <CaseStudySection
            title="6. Program Structure & Formats"
            badge={`${structureSections.length} sections`}
          >
            <div className="flex items-center justify-between gap-2">
              {renderBadge("structure_sections")}
              <button
                type="button"
                onClick={() =>
                  setStructureSections((p) => [
                    ...p,
                    {
                      id: `sec-${Date.now()}`,
                      badge: `Stage ${String(p.length + 1).padStart(2, "0")}`,
                      title: "",
                      subtitle: "",
                      items: [],
                    },
                  ])
                }
                className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline cursor-pointer ml-auto"
              >
                <Plus size={12} /> Add Stage / Format
              </button>
            </div>
            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-muted-foreground">Section Title</span>
              <input
                type="text"
                value={structureTitle}
                onChange={(e) => setStructureTitle(e.target.value)}
                className="h-9 rounded-[10px] border border-border bg-background px-3 text-xs"
              />
            </label>
            {structureSections.map((sec, i) => (
              <div key={sec.id || i} className="rounded-[10px] border border-border bg-background p-3 space-y-2">
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={sec.badge || ""}
                    onChange={(e) =>
                      setStructureSections((p) =>
                        p.map((x, idx) => (idx === i ? { ...x, badge: e.target.value } : x)),
                      )
                    }
                    placeholder="Stage 01"
                    className="w-24 h-8 rounded-[10px] border border-border bg-card px-2 text-xs font-bold text-primary text-center"
                  />
                  <input
                    type="text"
                    value={sec.title}
                    onChange={(e) =>
                      setStructureSections((p) =>
                        p.map((x, idx) => (idx === i ? { ...x, title: e.target.value } : x)),
                      )
                    }
                    placeholder="Title"
                    className="flex-1 h-8 rounded-[10px] border border-border bg-card px-2.5 text-xs font-bold"
                  />
                  <button
                    type="button"
                    onClick={() => setStructureSections((p) => p.filter((_, idx) => idx !== i))}
                    className="p-1 text-muted-foreground hover:text-rose-500 cursor-pointer"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
                <input
                  type="text"
                  value={sec.subtitle || ""}
                  onChange={(e) =>
                    setStructureSections((p) =>
                      p.map((x, idx) => (idx === i ? { ...x, subtitle: e.target.value } : x)),
                    )
                  }
                  placeholder="Subtitle (dates, location)"
                  className="w-full h-8 rounded-[10px] border border-border bg-card px-2.5 text-xs"
                />

                <div className="space-y-1.5">
                  <div className="flex gap-1.5 items-center">
                    <input
                      type="text"
                      value={sec.image_url || ""}
                      onChange={(e) =>
                        setStructureSections((p) =>
                          p.map((x, idx) => (idx === i ? { ...x, image_url: e.target.value } : x)),
                        )
                      }
                      placeholder="Side Image URL (optional)"
                      className="flex-1 h-8 rounded-[10px] border border-border bg-card px-2.5 text-xs"
                    />
                    <label className="inline-flex items-center gap-1 h-8 px-2.5 rounded-[10px] border border-border bg-card text-xs font-semibold hover:bg-muted cursor-pointer shrink-0">
                      <Upload size={11} />
                      <span>Upload</span>
                      <input
                        type="file"
                        accept="image/*"
                        className="hidden"
                        onChange={async (e) => {
                          const f = e.target.files?.[0]
                          if (!f) return
                          e.target.value = ""
                          try {
                            const res = await uploadWebsiteAsset(f)
                            setStructureSections((p) =>
                              p.map((x, idx) => (idx === i ? { ...x, image_url: res.url } : x)),
                            )
                            toast.success("Stage image uploaded")
                          } catch (err) {
                            toast.error(getErrorMessage(err, "Upload failed"))
                          }
                        }}
                      />
                    </label>
                  </div>
                  {sec.image_url && (
                    <div className="relative h-20 rounded-[10px] overflow-hidden border border-border bg-black/40">
                      <img
                        src={resolveWebsiteAsset(sec.image_url)}
                        alt=""
                        className="w-full h-full object-cover"
                      />
                    </div>
                  )}
                </div>

                {/* Items & Descriptions inside this Stage */}
                <div className="space-y-1.5 pt-2 border-t border-border/50">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-bold text-muted-foreground">Items &amp; Descriptions</span>
                    <button
                      type="button"
                      onClick={() =>
                        setStructureSections((p) =>
                          p.map((x, idx) =>
                            idx === i
                              ? { ...x, items: [...(x.items || []), { title: "", description: "" }] }
                              : x,
                          ),
                        )
                      }
                      className="inline-flex items-center gap-1 text-[11px] font-semibold text-primary hover:underline cursor-pointer"
                    >
                      <Plus size={11} /> Add Item
                    </button>
                  </div>
                  {(sec.items || []).map((it, itIdx) => (
                    <div key={itIdx} className="rounded-[10px] border border-border/70 bg-card p-2 space-y-1.5">
                      <div className="flex items-center gap-1.5">
                        <input
                          type="text"
                          value={it.title || ""}
                          onChange={(e) =>
                            setStructureSections((p) =>
                              p.map((x, idx) =>
                                idx === i
                                  ? {
                                      ...x,
                                      items: (x.items || []).map((cur, j) =>
                                        j === itIdx ? { ...cur, title: e.target.value } : cur,
                                      ),
                                    }
                                  : x,
                              ),
                            )
                          }
                          placeholder="Item title"
                          className="flex-1 h-7 rounded-[10px] border border-border bg-background px-2 text-xs font-semibold"
                        />
                        <button
                          type="button"
                          onClick={() =>
                            setStructureSections((p) =>
                              p.map((x, idx) =>
                                idx === i
                                  ? { ...x, items: (x.items || []).filter((_, j) => j !== itIdx) }
                                  : x,
                              ),
                            )
                          }
                          className="p-1 text-muted-foreground hover:text-rose-500 cursor-pointer"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                      <textarea
                        rows={2}
                        value={it.description || ""}
                        onChange={(e) =>
                          setStructureSections((p) =>
                            p.map((x, idx) =>
                              idx === i
                                ? {
                                    ...x,
                                    items: (x.items || []).map((cur, j) =>
                                      j === itIdx ? { ...cur, description: e.target.value } : cur,
                                    ),
                                  }
                                : x,
                            ),
                          )
                        }
                        placeholder="Description..."
                        className="w-full rounded-[10px] border border-border bg-background p-2 text-xs resize-none"
                      />
                    </div>
                  ))}
                </div>

                {/* Days / Milestones */}
                <div className="space-y-1.5 pt-2 border-t border-border/50">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-bold text-muted-foreground">Schedule Days</span>
                    <button
                      type="button"
                      onClick={() =>
                        setStructureSections((p) =>
                          p.map((x, idx) =>
                            idx === i
                              ? {
                                  ...x,
                                  days: [
                                    ...(x.days || []),
                                    { day_title: `Day ${(x.days || []).length + 1}`, milestones: [] },
                                  ],
                                }
                              : x,
                          ),
                        )
                      }
                      className="inline-flex items-center gap-1 text-[11px] font-semibold text-primary hover:underline cursor-pointer"
                    >
                      <Plus size={11} /> Add Day
                    </button>
                  </div>
                  {(sec.days || []).map((d, dIdx) => (
                    <div key={dIdx} className="rounded-[10px] border border-border/70 bg-card p-2 space-y-1.5">
                      <div className="flex items-center gap-1.5">
                        <input
                          type="text"
                          value={d.day_title || ""}
                          onChange={(e) =>
                            setStructureSections((p) =>
                              p.map((x, idx) =>
                                idx === i
                                  ? {
                                      ...x,
                                      days: (x.days || []).map((cur, j) =>
                                        j === dIdx ? { ...cur, day_title: e.target.value } : cur,
                                      ),
                                    }
                                  : x,
                              ),
                            )
                          }
                          placeholder="Day 1"
                          className="flex-1 h-7 rounded-[10px] border border-border bg-background px-2 text-xs font-semibold"
                        />
                        <button
                          type="button"
                          onClick={() =>
                            setStructureSections((p) =>
                              p.map((x, idx) =>
                                idx === i
                                  ? { ...x, days: (x.days || []).filter((_, j) => j !== dIdx) }
                                  : x,
                              ),
                            )
                          }
                          className="p-1 text-muted-foreground hover:text-rose-500 cursor-pointer"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                      <input
                        type="text"
                        value={(d.milestones || []).join(", ")}
                        onChange={(e) =>
                          setStructureSections((p) =>
                            p.map((x, idx) =>
                              idx === i
                                ? {
                                    ...x,
                                    days: (x.days || []).map((cur, j) =>
                                      j === dIdx
                                        ? {
                                            ...cur,
                                            milestones: e.target.value
                                              .split(",")
                                              .map((s) => s.trim())
                                              .filter(Boolean),
                                          }
                                        : cur,
                                    ),
                                  }
                                : x,
                            ),
                          )
                        }
                        placeholder="Milestones (comma-separated)"
                        className="w-full h-7 rounded-[10px] border border-border bg-background px-2 text-xs"
                      />
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </CaseStudySection>

          {/* 7. Visibility & Spotlights */}
          <CaseStudySection
            title="7. Visibility & Spotlights"
            badge={`${visibilityStats.length} metrics, ${spotlights.length} spotlights`}
          >
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-foreground">Impact &amp; Visibility Stats</span>
                <button
                  type="button"
                  onClick={() => setVisibilityStats((p) => [...p, { value: "", label: "" }])}
                  className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline cursor-pointer"
                >
                  <Plus size={12} /> Add Metric
                </button>
              </div>
              {visibilityStats.map((v, i) => (
                <div key={i} className="flex items-center gap-2">
                  <input
                    type="text"
                    value={v.value}
                    onChange={(e) =>
                      setVisibilityStats((p) => p.map((x, idx) => (idx === i ? { ...x, value: e.target.value } : x)))
                    }
                    placeholder="23,000+"
                    className="w-28 h-8 rounded-[10px] border border-border bg-background px-2.5 text-xs font-bold"
                  />
                  <input
                    type="text"
                    value={v.label}
                    onChange={(e) =>
                      setVisibilityStats((p) => p.map((x, idx) => (idx === i ? { ...x, label: e.target.value } : x)))
                    }
                    placeholder="Impressions / label"
                    className="flex-1 h-8 rounded-[10px] border border-border bg-background px-2.5 text-xs"
                  />
                  <button
                    type="button"
                    onClick={() => setVisibilityStats((p) => p.filter((_, idx) => idx !== i))}
                    className="p-1 text-muted-foreground hover:text-rose-500 cursor-pointer"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              ))}
            </div>

            <div className="space-y-2 pt-3 border-t border-border/60">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-foreground">Spotlights &amp; Showcases</span>
                <button
                  type="button"
                  onClick={() =>
                    setSpotlights((p) => [...p, { tag: "Spotlight", title: "", content: "", images: [] }])
                  }
                  className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline cursor-pointer"
                >
                  <Plus size={12} /> Add Spotlight
                </button>
              </div>
              {spotlights.map((sp, i) => (
                <div key={i} className="rounded-[10px] border border-border bg-background p-2.5 space-y-2">
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={sp.tag || ""}
                      onChange={(e) =>
                        setSpotlights((p) => p.map((x, idx) => (idx === i ? { ...x, tag: e.target.value } : x)))
                      }
                      placeholder="Tag"
                      className="w-28 h-8 rounded-[10px] border border-border bg-card px-2 text-xs font-bold text-primary"
                    />
                    <input
                      type="text"
                      value={sp.title || ""}
                      onChange={(e) =>
                        setSpotlights((p) => p.map((x, idx) => (idx === i ? { ...x, title: e.target.value } : x)))
                      }
                      placeholder="Spotlight Title"
                      className="flex-1 h-8 rounded-[10px] border border-border bg-card px-2.5 text-xs font-semibold"
                    />
                    <button
                      type="button"
                      onClick={() => setSpotlights((p) => p.filter((_, idx) => idx !== i))}
                      className="p-1 text-muted-foreground hover:text-rose-500 cursor-pointer"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                  <textarea
                    rows={2}
                    value={sp.content || ""}
                    onChange={(e) =>
                      setSpotlights((p) => p.map((x, idx) => (idx === i ? { ...x, content: e.target.value } : x)))
                    }
                    placeholder="Details..."
                    className="w-full rounded-[10px] border border-border bg-card p-2 text-xs resize-none"
                  />
                </div>
              ))}
            </div>
          </CaseStudySection>

          {/* 8. Testimonials, CTA & Section Visibility */}
          <CaseStudySection
            title="8. Testimonials, CTA & Visibility"
            badge={`${testimonials.length} quotes`}
          >
            <div className="space-y-2">
              <span className="text-xs font-bold text-foreground block">Section Visibility</span>
              <div className="flex flex-wrap gap-2">
                {[
                  { key: "metrics", label: "Metrics" },
                  { key: "gallery", label: "Gallery" },
                  { key: "curriculum", label: "Curriculum" },
                  { key: "structure", label: "Structure" },
                  { key: "partners", label: "Partners" },
                  { key: "testimonials", label: "Testimonials" },
                ].map((s) => {
                  const hidden = hiddenSections.includes(s.key)
                  return (
                    <button
                      key={s.key}
                      type="button"
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

            <div className="space-y-2 pt-3 border-t border-border/60">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-foreground">Participant Voices</span>
                <button
                  type="button"
                  onClick={() =>
                    setTestimonials((p) => [
                      ...p,
                      { badge: "Student Voice", quote: "", author_name: "", author_role: "Student Participant" },
                    ])
                  }
                  className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline cursor-pointer"
                >
                  <Plus size={12} /> Add Quote
                </button>
              </div>
              {testimonials.map((t, i) => (
                <div key={i} className="rounded-[10px] border border-border bg-background p-2.5 space-y-2">
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={t.badge || ""}
                      onChange={(e) =>
                        setTestimonials((p) => p.map((x, idx) => (idx === i ? { ...x, badge: e.target.value } : x)))
                      }
                      placeholder="Badge"
                      className="w-28 h-8 rounded-[10px] border border-border bg-card px-2 text-xs font-bold text-primary"
                    />
                    <input
                      type="text"
                      value={t.author_name}
                      onChange={(e) =>
                        setTestimonials((p) =>
                          p.map((x, idx) => (idx === i ? { ...x, author_name: e.target.value } : x)),
                        )
                      }
                      placeholder="Author Name"
                      className="flex-1 h-8 rounded-[10px] border border-border bg-card px-2.5 text-xs font-semibold"
                    />
                    <button
                      type="button"
                      onClick={() => setTestimonials((p) => p.filter((_, idx) => idx !== i))}
                      className="p-1 text-muted-foreground hover:text-rose-500 cursor-pointer"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                  <textarea
                    rows={2}
                    value={t.quote}
                    onChange={(e) =>
                      setTestimonials((p) => p.map((x, idx) => (idx === i ? { ...x, quote: e.target.value } : x)))
                    }
                    placeholder="Quote..."
                    className="w-full rounded-[10px] border border-border bg-card p-2 text-xs resize-none"
                  />
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    <input
                      type="text"
                      value={t.author_role || ""}
                      onChange={(e) =>
                        setTestimonials((p) =>
                          p.map((x, idx) => (idx === i ? { ...x, author_role: e.target.value } : x)),
                        )
                      }
                      placeholder="Role"
                      className="h-8 rounded-[10px] border border-border bg-card px-2.5 text-xs"
                    />
                    <div className="flex gap-1.5 items-center">
                      <input
                        type="text"
                        value={t.author_photo_url || ""}
                        onChange={(e) =>
                          setTestimonials((p) =>
                            p.map((x, idx) => (idx === i ? { ...x, author_photo_url: e.target.value } : x)),
                          )
                        }
                        placeholder="Avatar URL"
                        className="flex-1 h-8 rounded-[10px] border border-border bg-card px-2.5 text-xs"
                      />
                      <label className="inline-flex items-center gap-1 h-8 px-2.5 rounded-[10px] border border-border bg-card text-xs font-semibold hover:bg-muted cursor-pointer shrink-0">
                        <Upload size={11} />
                        <span>Upload</span>
                        <input
                          type="file"
                          accept="image/*"
                          className="hidden"
                          onChange={async (e) => {
                            const f = e.target.files?.[0]
                            if (!f) return
                            e.target.value = ""
                            try {
                              const res = await uploadWebsiteAsset(f)
                              setTestimonials((p) =>
                                p.map((x, idx) => (idx === i ? { ...x, author_photo_url: res.url } : x)),
                              )
                              toast.success("Avatar uploaded")
                            } catch (err) {
                              toast.error(getErrorMessage(err, "Upload failed"))
                            }
                          }}
                        />
                      </label>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-3 border-t border-border/60">
              <label className="flex flex-col gap-1">
                <span className="text-xs font-semibold text-muted-foreground">Report / CTA Label</span>
                <input
                  type="text"
                  value={ctaLabel}
                  onChange={(e) => setCtaLabel(e.target.value)}
                  className="h-9 rounded-[10px] border border-border bg-background px-3 text-xs"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs font-semibold text-muted-foreground">Report / CTA URL</span>
                <input
                  type="url"
                  value={ctaUrl}
                  onChange={(e) => setCtaUrl(e.target.value)}
                  placeholder="https://..."
                  className="h-9 rounded-[10px] border border-border bg-background px-3 text-xs"
                />
              </label>
            </div>
          </CaseStudySection>
        </div>

        {/* RIGHT HALF: REAL LIVE SITE IFRAME (SHOW CARD + BIG CARD FROM /case-studies) */}
        <div className="xl:sticky xl:top-4 rounded-[10px] border border-border bg-[#05030A] overflow-hidden shadow-xl">
          <div className="px-4 py-2.5 border-b border-white/10 bg-[#120A22] flex items-center justify-between gap-2 flex-wrap">
            <span className="text-xs font-bold text-white/90">Live Case Study Preview</span>
            <span className="text-[11px] font-mono text-white/50 break-all">
              /case-studies?mission={currentSlug}
            </span>
          </div>
          <iframe
            ref={iframeRef}
            src={iframeUrl}
            title="Live Case Study Preview"
            onLoad={() => setIframeReady(true)}
            className="w-full h-[780px] bg-[#05030A] border-0"
          />
        </div>
      </div>
    </div>
  )
}

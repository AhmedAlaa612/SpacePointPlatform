import { useEffect, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  ChevronLeft,
  ChevronRight,
  Eye,
  EyeOff,
  Layers,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  SlidersHorizontal,
  Trash2,
  Upload,
  X,
} from "lucide-react"
import { cn, getErrorMessage } from "@/lib/utils"
import { Spinner } from "@/components/ui/primitives"
import { useToast } from "@/components/ui/toast"
import { Modal, ModalActions } from "@/pages/admin/components/common"
import { uploadWebsiteAsset } from "@/api/websiteConfig"
import { resolveWebsiteAsset } from "./WebsiteManagement"
import { WebsiteCaseStudiesHeaderModal } from "./WebsiteCaseStudiesHeaderModal"
import { getProgramsApi } from "@/api/sessions/programs"
import { getCohortsApi } from "@/api/sessions/cohorts"
import {
  createWebsiteCaseStudy,
  deleteWebsiteCaseStudy,
  getWebsiteCaseStudies,
  pullCaseStudySnapshot,
  updateWebsiteCaseStudy,
  type CaseStudyCurriculumChapter,
  type CaseStudyHighlightItem,
  type CaseStudyMetricItem,
  type CaseStudyPartnerItem,
  type CaseStudySnapshotRequest,
  type CaseStudySpotlightItem,
  type CaseStudyStructureSection,
  type CaseStudyTestimonialItem,
  type CaseStudyVisibilityStat,
  type WebsiteCaseStudy,
  type WebsiteCaseStudyCreate,
} from "@/api/websiteCaseStudies"

const CATEGORIES = [
  "Challenges & Competitions",
  "National Programs",
  "Universities",
  "Roadshows",
  "STEM Programs",
  "Other",
]

const inputCls =
  "w-full h-10 rounded-xl border border-border bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none"

const textareaCls =
  "w-full rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none"

function FieldWrapper({
  label,
  children,
  helper,
}: {
  label: string
  children: React.ReactNode
  helper?: string
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      {children}
      {helper && <span className="text-[11px] text-muted-foreground">{helper}</span>}
    </div>
  )
}

export function WebsiteCaseStudiesPanel() {
  const queryClient = useQueryClient()
  const toast = useToast()

  const [search, setSearch] = useState("")
  const [selectedCategory, setSelectedCategory] = useState("all")
  const [modalOpen, setModalOpen] = useState(false)
  const [headerModalOpen, setHeaderModalOpen] = useState(false)
  const [editingItem, setEditingItem] = useState<WebsiteCaseStudy | null>(null)
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null)

  const { data: caseStudies = [], isLoading } = useQuery({
    queryKey: ["website-case-studies"],
    queryFn: getWebsiteCaseStudies,
  })

  const { data: programs = [] } = useQuery({
    queryKey: ["sessions-programs"],
    queryFn: getProgramsApi,
  })

  const { data: cohorts = [] } = useQuery({
    queryKey: ["sessions-cohorts"],
    queryFn: () => getCohortsApi(),
  })

  const deleteMutation = useMutation({
    mutationFn: deleteWebsiteCaseStudy,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["website-case-studies"] })
      toast.success("Case study deleted")
      setDeleteConfirmId(null)
    },
    onError: (e) => toast.error(getErrorMessage(e, "Could not delete case study")),
  })

  const togglePublishMutation = useMutation({
    mutationFn: ({ id, is_published }: { id: string; is_published: boolean }) =>
      updateWebsiteCaseStudy(id, { is_published }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["website-case-studies"] })
      toast.success("Status updated")
    },
    onError: (e) => toast.error(getErrorMessage(e, "Could not update status")),
  })

  const filteredItems = caseStudies.filter((item) => {
    if (selectedCategory !== "all" && item.category !== selectedCategory) return false
    const q = search.trim().toLowerCase()
    if (!q) return true
    return (
      item.title.toLowerCase().includes(q) ||
      (item.subtitle && item.subtitle.toLowerCase().includes(q)) ||
      (item.partner_name && item.partner_name.toLowerCase().includes(q)) ||
      item.slug.toLowerCase().includes(q)
    )
  })

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-foreground">Case Studies & Missions</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Manage standardized missions displayed on the public marketing site.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setHeaderModalOpen(true)}
            className="h-9 px-3.5 rounded-xl border border-border bg-card hover:bg-muted text-xs font-semibold inline-flex items-center gap-1.5 transition-colors text-foreground"
            title="Edit page header stats and partners strip"
          >
            <SlidersHorizontal size={14} /> Page Header & Partners
          </button>
          <button
            onClick={() => {
              setEditingItem(null)
              setModalOpen(true)
            }}
            className="h-9 px-4 rounded-xl bg-primary text-primary-foreground text-xs font-semibold inline-flex items-center gap-1.5 hover:opacity-90 transition-opacity"
          >
            <Plus size={14} /> New Case Study
          </button>
        </div>
      </div>

      {/* Filter / Search Bar */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[220px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search missions, partners, or slugs…"
            className={cn(inputCls, "pl-9")}
          />
        </div>
        <select
          value={selectedCategory}
          onChange={(e) => setSelectedCategory(e.target.value)}
          className={cn(inputCls, "w-auto cursor-pointer")}
        >
          <option value="all">All Categories</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </div>

      {/* Case Studies Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        {filteredItems.map((item) => (
          <div
            key={item.id}
            className="flex flex-col rounded-2xl border border-border bg-card overflow-hidden transition-all hover:border-primary/40 hover:shadow-lg"
          >
            {/* Thumbnail Header */}
            <div className="relative aspect-[16/9] bg-muted/40 overflow-hidden">
              {item.cover_image_url ? (
                <img
                  src={resolveWebsiteAsset(item.cover_image_url)}
                  alt={item.title}
                  className="w-full h-full object-cover"
                  onError={(e) => {
                    e.currentTarget.style.display = "none"
                  }}
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-muted-foreground text-xs">
                  No image
                </div>
              )}
              {item.partner_logo_url && (
                <div className="absolute top-3 left-3 bg-black/60 backdrop-blur-md px-2 py-1 rounded-lg border border-white/10 max-h-8 flex items-center">
                  <img
                    src={resolveWebsiteAsset(item.partner_logo_url)}
                    alt=""
                    className="h-4 object-contain max-w-[80px]"
                    onError={(e) => {
                      e.currentTarget.style.display = "none"
                    }}
                  />
                </div>
              )}
              <div className="absolute top-3 right-3 flex items-center gap-1.5">
                {item.is_featured && (
                  <span className="bg-amber-500/90 text-white text-[10px] font-bold px-2 py-0.5 rounded-full shadow-sm">
                    Featured
                  </span>
                )}
                <span className="bg-primary/90 text-primary-foreground text-[10px] font-bold px-2.5 py-0.5 rounded-full uppercase tracking-wider shadow-sm">
                  {item.category}
                </span>
              </div>
            </div>

            {/* Content Body */}
            <div className="p-4 flex flex-col flex-1 gap-2.5">
              <div>
                <h3 className="font-bold text-base text-foreground leading-snug line-clamp-1">
                  {item.title}
                </h3>
                {item.subtitle && (
                  <p className="text-xs text-muted-foreground line-clamp-1 mt-0.5">
                    {item.subtitle}
                  </p>
                )}
              </div>

              <p className="text-xs text-muted-foreground/90 line-clamp-2 leading-relaxed flex-1">
                {item.card_summary}
              </p>

              {/* Quick Metrics */}
              {item.metrics && item.metrics.length > 0 && (
                <div className="flex items-center gap-3 py-2 border-t border-border/60 text-xs">
                  {item.metrics.slice(0, 2).map((m, idx) => (
                    <div key={idx} className="flex flex-col">
                      <span className="font-bold text-foreground text-sm leading-tight">{m.value}</span>
                      <span className="text-[10px] text-muted-foreground uppercase">{m.label}</span>
                    </div>
                  ))}
                  {item.metrics.length > 2 && (
                    <span className="text-[10px] text-muted-foreground ml-auto">
                      +{item.metrics.length - 2} more stats
                    </span>
                  )}
                </div>
              )}

              {/* Source Link indicator */}
              <div className="flex items-center justify-between text-[11px] text-muted-foreground pt-2 border-t border-border/40">
                <span className="flex items-center gap-1">
                  <Layers size={12} />
                  {item.source_type === "cohort"
                    ? "Single Cohort"
                    : item.source_type === "multi_cohort"
                    ? "Multi-Cohort"
                    : item.source_type === "program"
                    ? "Program Aggregate"
                    : "Manual Standalone"}
                </span>
                <span className="font-mono text-[10px]">/{item.slug}</span>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center justify-between pt-3 border-t border-border mt-auto">
                <button
                  type="button"
                  onClick={() =>
                    togglePublishMutation.mutate({
                      id: item.id,
                      is_published: !item.is_published,
                    })
                  }
                  className={cn(
                    "h-8 px-2.5 rounded-lg text-xs font-semibold inline-flex items-center gap-1.5 transition-colors",
                    item.is_published
                      ? "text-emerald-500 bg-emerald-500/10 hover:bg-emerald-500/20"
                      : "text-muted-foreground bg-muted hover:text-foreground"
                  )}
                >
                  {item.is_published ? <Eye size={13} /> : <EyeOff size={13} />}
                  {item.is_published ? "Published" : "Draft"}
                </button>

                <div className="flex items-center gap-1.5">
                  <button
                    onClick={() => {
                      setEditingItem(item)
                      setModalOpen(true)
                    }}
                    className="h-8 px-2.5 rounded-lg border border-border text-xs font-semibold text-foreground hover:bg-muted inline-flex items-center gap-1 transition-colors"
                  >
                    <Pencil size={12} /> Edit
                  </button>
                  <button
                    onClick={() => setDeleteConfirmId(item.id)}
                    className="h-8 w-8 rounded-lg border border-border text-red-500 hover:bg-red-500/10 inline-flex items-center justify-center transition-colors"
                    title="Delete"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {filteredItems.length === 0 && (
        <div className="p-12 text-center border border-dashed border-border rounded-2xl flex flex-col items-center justify-center gap-2">
          <p className="text-sm font-semibold text-foreground">No case studies found</p>
          <p className="text-xs text-muted-foreground">
            Try adjusting your search query or create a new case study.
          </p>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deleteConfirmId && (
        <Modal title="Delete Case Study" onClose={() => setDeleteConfirmId(null)}>
          <div className="flex flex-col gap-4">
            <p className="text-sm text-foreground">
              Are you sure you want to delete this case study? This action cannot be undone.
            </p>
            <ModalActions
              onCancel={() => setDeleteConfirmId(null)}
              onConfirm={() => deleteMutation.mutate(deleteConfirmId)}
              loading={deleteMutation.isPending}
              label="Yes, Delete"
            />
          </div>
        </Modal>
      )}

      {/* Case Studies Page Header & Partners Modal */}
      <WebsiteCaseStudiesHeaderModal
        isOpen={headerModalOpen}
        onClose={() => setHeaderModalOpen(false)}
      />

      {/* Create / Edit Case Study Modal */}
      {modalOpen && (
        <CaseStudyEditorModal
          caseStudy={editingItem}
          programs={programs}
          cohorts={cohorts}
          onClose={() => setModalOpen(false)}
          onSuccess={() => {
            queryClient.invalidateQueries({ queryKey: ["website-case-studies"] })
            setModalOpen(false)
          }}
        />
      )}
    </div>
  )
}

function CaseStudyEditorModal({
  caseStudy,
  programs,
  cohorts,
  onClose,
  onSuccess,
}: {
  caseStudy: WebsiteCaseStudy | null
  programs: any[]
  cohorts: any[]
  onClose: () => void
  onSuccess: () => void
}) {
  const toast = useToast()
  const isEdit = !!caseStudy

  // Navigation Sections definition
  const SECTIONS = [
    { id: "general", label: "1. Basics & Source" },
    { id: "partners", label: "2. Partners & Collabs" },
    { id: "overview_stats", label: "3. Overview & Stats" },
    { id: "gallery", label: "4. Gallery" },
    { id: "highlights", label: "5. Highlights & Chapters" },
    { id: "structure", label: "6. Structure & Formats" },
    { id: "visibility_spotlights", label: "7. Spotlights" },
    { id: "voices_cta", label: "8. Testimonials & CTA" },
  ] as const

  // Active section tab in editor
  const [activeSection, setActiveSection] = useState<(typeof SECTIONS)[number]["id"]>("general")

  // Tabs scroll track state & helpers
  const tabsContainerRef = useRef<HTMLDivElement>(null)
  const [canScrollLeft, setCanScrollLeft] = useState(false)
  const [canScrollRight, setCanScrollRight] = useState(true)

  const checkTabScroll = () => {
    const el = tabsContainerRef.current
    if (!el) return
    setCanScrollLeft(el.scrollLeft > 6)
    setCanScrollRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 10)
  }

  useEffect(() => {
    checkTabScroll()
    const el = tabsContainerRef.current
    if (!el) return
    el.addEventListener("scroll", checkTabScroll, { passive: true })
    window.addEventListener("resize", checkTabScroll)
    return () => {
      el.removeEventListener("scroll", checkTabScroll)
      window.removeEventListener("resize", checkTabScroll)
    }
  }, [])

  const scrollTabs = (direction: "left" | "right") => {
    if (!tabsContainerRef.current) return
    tabsContainerRef.current.scrollBy({
      left: direction === "left" ? -220 : 220,
      behavior: "smooth",
    })
    setTimeout(checkTabScroll, 250)
  }

  // Form State
  const [title, setTitle] = useState(caseStudy?.title ?? "")
  const [subtitle, setSubtitle] = useState(caseStudy?.subtitle ?? "")
  const [slug, setSlug] = useState(caseStudy?.slug ?? "")
  const [category, setCategory] = useState(caseStudy?.category ?? "Challenges & Competitions")
  const [cardSummary, setCardSummary] = useState(caseStudy?.card_summary ?? "")
  const [coverImageUrl, setCoverImageUrl] = useState(caseStudy?.cover_image_url ?? "")
  const [partnerLogoUrl, setPartnerLogoUrl] = useState(caseStudy?.partner_logo_url ?? "")
  const [partnerName, setPartnerName] = useState(caseStudy?.partner_name ?? "")

  // Source Type and Linking
  const [sourceType, setSourceType] = useState<string>(caseStudy?.source_type ?? "manual")
  const [programId, setProgramId] = useState<string>(caseStudy?.program_id ?? "")
  const [cohortId, setCohortId] = useState<string>(caseStudy?.cohort_id ?? "")
  const [cohortIds, setCohortIds] = useState<string[]>(caseStudy?.cohort_ids ?? [])

  // Section 1: Partners
  const [partners, setPartners] = useState<CaseStudyPartnerItem[]>(caseStudy?.partners ?? [])

  // Section 2: Overview & Impact Metrics
  const [overviewText, setOverviewText] = useState(caseStudy?.overview_text ?? "")
  const [heroMetricEnabled, setHeroMetricEnabled] = useState(caseStudy?.hero_metric_enabled ?? false)
  const [heroMetricValue, setHeroMetricValue] = useState(caseStudy?.hero_metric_value ?? "")
  const [heroMetricLabel, setHeroMetricLabel] = useState(caseStudy?.hero_metric_label ?? "")
  const [metrics, setMetrics] = useState<CaseStudyMetricItem[]>(
    caseStudy?.metrics ?? [
      { value: "500+", label: "Students Trained" },
      { value: "50", label: "Teams" },
    ]
  )

  // Section 3: Photo Gallery
  const [galleryImages, setGalleryImages] = useState<string[]>(caseStudy?.gallery_images ?? [])

  // Section 4: Highlights & Chapters
  const [highlights, setHighlights] = useState<CaseStudyHighlightItem[]>(caseStudy?.highlights ?? [])
  const [curriculumChapters, setCurriculumChapters] = useState<CaseStudyCurriculumChapter[]>(
    caseStudy?.curriculum_chapters ?? []
  )

  // Section 5: Structure & Formats
  const [structureTitle, setStructureTitle] = useState(caseStudy?.structure_title ?? "Bootcamp Structure")
  const [structureSections, setStructureSections] = useState<CaseStudyStructureSection[]>(
    caseStudy?.structure_sections ?? []
  )

  // Section 6: Visibility & Spotlights
  const [visibilityStats, setVisibilityStats] = useState<CaseStudyVisibilityStat[]>(
    caseStudy?.visibility_stats ?? []
  )
  const [spotlights, setSpotlights] = useState<CaseStudySpotlightItem[]>(caseStudy?.spotlights ?? [])

  // Section 7: Testimonials & CTA
  const [testimonials, setTestimonials] = useState<CaseStudyTestimonialItem[]>(
    caseStudy?.testimonials ?? []
  )
  const [ctaLabel, setCtaLabel] = useState(caseStudy?.cta_label ?? "")
  const [ctaUrl, setCtaUrl] = useState(caseStudy?.cta_url ?? "")

  // Meta controls
  const [displayOrder, setDisplayOrder] = useState(caseStudy?.display_order ?? 0)
  const [isFeatured, setIsFeatured] = useState(caseStudy?.is_featured ?? false)
  const [isPublished, setIsPublished] = useState(caseStudy?.is_published ?? true)

  const [pulling, setPulling] = useState(false)

  // Handlers for Pulling Snapshot Data
  const handlePullSnapshot = async () => {
    if (sourceType === "manual") {
      toast.error("Please select a source type (Cohort, Multi-Cohort, or Program) to pull data")
      return
    }
    setPulling(true)
    try {
      const payload: CaseStudySnapshotRequest = {
        source_type: sourceType as any,
        program_id: programId || undefined,
        cohort_id: cohortId || undefined,
        cohort_ids: cohortIds.length > 0 ? cohortIds : undefined,
      }
      const data = await pullCaseStudySnapshot(payload)

      if (data.title && !title) setTitle(data.title)
      if (data.subtitle && !subtitle) setSubtitle(data.subtitle)
      if (data.card_summary && !cardSummary) setCardSummary(data.card_summary)
      if (data.overview_text && !overviewText) setOverviewText(data.overview_text)
      if (data.category) setCategory(data.category)
      if (data.partner_name && !partnerName) setPartnerName(data.partner_name)
      if (data.partners && data.partners.length > 0 && partners.length === 0) setPartners(data.partners)
      if (data.metrics && data.metrics.length > 0) {
        setMetrics(data.metrics)
      }
      if (data.curriculum_chapters && data.curriculum_chapters.length > 0 && curriculumChapters.length === 0) {
        setCurriculumChapters(data.curriculum_chapters)
      }
      if (data.structure_sections && data.structure_sections.length > 0 && structureSections.length === 0) {
        setStructureSections(data.structure_sections)
      }

      toast.success("Template data and aggregate metrics pulled from system!")
    } catch (err) {
      toast.error(getErrorMessage(err, "Failed to pull system data"))
    } finally {
      setPulling(false)
    }
  }

  // Image and Asset Upload Handlers
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [uploadingImage, setUploadingImage] = useState(false)
  const handleCoverUpload = async (file?: File) => {
    if (!file) return
    setUploadingImage(true)
    try {
      const res = await uploadWebsiteAsset(file)
      setCoverImageUrl(res.url)
      toast.success("Cover image uploaded")
    } catch (err) {
      toast.error(getErrorMessage(err, "Failed to upload image"))
    } finally {
      setUploadingImage(false)
    }
  }

  const partnerLogoInputRef = useRef<HTMLInputElement>(null)
  const [uploadingPrimaryPartner, setUploadingPrimaryPartner] = useState(false)
  const handlePrimaryPartnerUpload = async (file?: File) => {
    if (!file) return
    setUploadingPrimaryPartner(true)
    try {
      const res = await uploadWebsiteAsset(file)
      setPartnerLogoUrl(res.url)
      toast.success("Primary partner logo uploaded")
    } catch (err) {
      toast.error(getErrorMessage(err, "Failed to upload logo"))
    } finally {
      setUploadingPrimaryPartner(false)
    }
  }

  const [uploadingPartnerIdx, setUploadingPartnerIdx] = useState<number | null>(null)
  const handlePartnerLogoUpload = async (idx: number, file?: File) => {
    if (!file) return
    setUploadingPartnerIdx(idx)
    try {
      const res = await uploadWebsiteAsset(file)
      const copy = [...partners]
      copy[idx] = { ...copy[idx], logo_url: res.url }
      setPartners(copy)
      toast.success("Partner logo uploaded")
    } catch (err) {
      toast.error(getErrorMessage(err, "Failed to upload logo"))
    } finally {
      setUploadingPartnerIdx(null)
    }
  }

  const galleryInputRef = useRef<HTMLInputElement>(null)
  const [uploadingGallery, setUploadingGallery] = useState(false)
  const handleGalleryUpload = async (file?: File) => {
    if (!file) return
    setUploadingGallery(true)
    try {
      const res = await uploadWebsiteAsset(file)
      setGalleryImages([...galleryImages, res.url])
      toast.success("Photo added to gallery")
    } catch (err) {
      toast.error(getErrorMessage(err, "Failed to upload photo"))
    } finally {
      setUploadingGallery(false)
    }
  }

  // Save Mutation
  const mutation = useMutation({
    mutationFn: () => {
      const payload: WebsiteCaseStudyCreate = {
        title: title.trim(),
        subtitle: subtitle.trim() || null,
        slug: slug.trim() || undefined,
        category,
        card_summary: cardSummary.trim(),
        cover_image_url: coverImageUrl.trim(),
        partner_logo_url: partnerLogoUrl.trim() || null,
        partner_name: partnerName.trim() || null,

        source_type: sourceType,
        program_id: programId || null,
        cohort_id: cohortId || null,
        cohort_ids: cohortIds,

        partners,
        overview_text: overviewText.trim() || null,
        metrics,
        hero_metric_enabled: heroMetricEnabled,
        hero_metric_value: heroMetricValue.trim() || null,
        hero_metric_label: heroMetricLabel.trim() || null,
        card_metrics: metrics.slice(0, 2),

        gallery_images: galleryImages,
        highlights,
        curriculum_chapters: curriculumChapters,

        structure_title: structureTitle.trim() || null,
        structure_sections: structureSections,

        visibility_stats: visibilityStats,
        spotlights,

        testimonials,
        cta_label: ctaLabel.trim() || null,
        cta_url: ctaUrl.trim() || null,

        display_order: Number(displayOrder),
        is_featured: isFeatured,
        is_published: isPublished,
      }
      return isEdit ? updateWebsiteCaseStudy(caseStudy!.id, payload) : createWebsiteCaseStudy(payload)
    },
    onSuccess: () => {
      toast.success(isEdit ? "Case study updated" : "Case study created")
      onSuccess()
    },
    onError: (err) => toast.error(getErrorMessage(err, "Failed to save case study")),
  })

  return (
    <Modal
      title={isEdit ? `Edit Case Study — ${caseStudy!.title}` : "New Case Study"}
      onClose={onClose}
      maxWidth="sm:max-w-4xl max-w-4xl"
    >
      <div className="flex flex-col gap-5">
        {/* Navigation Tabs for Editor Sections with Explicit Arrow Controls & Visible Scrollbar */}
        <div className="relative flex items-center gap-1.5 border-b border-border pb-2.5">
          {/* Scroll Left Arrow */}
          <button
            type="button"
            onClick={() => scrollTabs("left")}
            disabled={!canScrollLeft}
            title="Scroll tabs left"
            aria-label="Scroll tabs left"
            className={cn(
              "h-8 w-8 rounded-xl border border-border bg-card shrink-0 flex items-center justify-center transition-all",
              canScrollLeft
                ? "hover:bg-muted text-foreground hover:border-primary/50 cursor-pointer shadow-sm"
                : "opacity-30 text-muted-foreground cursor-not-allowed"
            )}
          >
            <ChevronLeft size={16} />
          </button>

          {/* Scrollable Track with visible custom scrollbar */}
          <div
            ref={tabsContainerRef}
            className="flex-1 flex items-center gap-1.5 overflow-x-auto py-1 scroll-smooth"
            style={{
              scrollbarWidth: "thin",
              scrollbarColor: "hsl(var(--primary) / 0.4) transparent",
            }}
          >
            {SECTIONS.map((sec) => (
              <button
                key={sec.id}
                onClick={() => setActiveSection(sec.id)}
                className={cn(
                  "px-3 py-1.5 rounded-lg font-semibold text-xs whitespace-nowrap transition-all border",
                  activeSection === sec.id
                    ? "bg-primary text-primary-foreground border-primary shadow-sm"
                    : "border-transparent text-muted-foreground hover:bg-muted hover:text-foreground"
                )}
              >
                {sec.label}
              </button>
            ))}
          </div>

          {/* Scroll Right Arrow with highlight when tabs are hidden off-screen */}
          <button
            type="button"
            onClick={() => scrollTabs("right")}
            disabled={!canScrollRight}
            title="Scroll tabs right"
            aria-label="Scroll tabs right"
            className={cn(
              "h-8 w-8 rounded-xl border shrink-0 flex items-center justify-center transition-all",
              canScrollRight
                ? "bg-primary/10 border-primary/50 text-primary hover:bg-primary/20 cursor-pointer shadow-sm ring-1 ring-primary/40"
                : "border-border bg-card opacity-30 text-muted-foreground cursor-not-allowed"
            )}
          >
            <ChevronRight size={16} />
          </button>
        </div>

        {/* SECTION 1: BASICS & SOURCE LINKING */}
        {activeSection === "general" && (
          <div className="flex flex-col gap-5">
            {/* Source Linking Box */}
            <div className="p-4 rounded-2xl border border-primary/30 bg-primary/5 flex flex-col gap-3">
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                <div>
                  <h4 className="text-xs font-bold uppercase tracking-wider text-primary">
                    Portal Data Linking (Optional)
                  </h4>
                  <p className="text-xs text-muted-foreground">
                    Connect this case study to a Cohort or Program to pull real participant counts, teams, and curriculum.
                  </p>
                </div>
                {sourceType !== "manual" && (
                  <button
                    type="button"
                    disabled={pulling}
                    onClick={handlePullSnapshot}
                    className="h-8 px-3 rounded-xl bg-primary text-primary-foreground text-xs font-semibold inline-flex items-center gap-1.5 shadow-sm hover:opacity-90 disabled:opacity-50"
                  >
                    <RefreshCw size={13} className={cn(pulling && "animate-spin")} />
                    {pulling ? "Pulling…" : "Pull / Re-sync Metrics"}
                  </button>
                )}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2">
                <FieldWrapper label="Source Mode">
                  <select
                    value={sourceType}
                    onChange={(e) => setSourceType(e.target.value)}
                    className={inputCls}
                  >
                    <option value="manual">Manual (Standalone)</option>
                    <option value="cohort">Single Cohort</option>
                    <option value="multi_cohort">Multiple Cohorts</option>
                    <option value="program">Entire Program</option>
                  </select>
                </FieldWrapper>

                {sourceType === "cohort" && (
                  <FieldWrapper label="Select Cohort">
                    <select
                      value={cohortId}
                      onChange={(e) => setCohortId(e.target.value)}
                      className={inputCls}
                    >
                      <option value="">-- Choose Cohort --</option>
                      {cohorts.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name} {c.starts_on ? `(${c.starts_on})` : ""}
                        </option>
                      ))}
                    </select>
                  </FieldWrapper>
                )}

                {sourceType === "program" && (
                  <FieldWrapper label="Select Program">
                    <select
                      value={programId}
                      onChange={(e) => setProgramId(e.target.value)}
                      className={inputCls}
                    >
                      <option value="">-- Choose Program --</option>
                      {programs.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name} ({p.code})
                        </option>
                      ))}
                    </select>
                  </FieldWrapper>
                )}

                {sourceType === "multi_cohort" && (
                  <div className="sm:col-span-2 flex flex-col gap-1.5">
                    <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      Pick Cohorts ({cohortIds.length} selected)
                    </span>
                    <div className="max-h-28 overflow-y-auto border border-border rounded-xl p-2 bg-background flex flex-col gap-1 text-xs">
                      {cohorts.map((c) => {
                        const checked = cohortIds.includes(c.id)
                        return (
                          <label key={c.id} className="flex items-center gap-2 cursor-pointer hover:bg-muted/50 p-1 rounded">
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={(e) => {
                                if (e.target.checked) setCohortIds([...cohortIds, c.id])
                                else setCohortIds(cohortIds.filter((id) => id !== c.id))
                              }}
                            />
                            <span>{c.name}</span>
                          </label>
                        )
                      })}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Core Titles */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <FieldWrapper label="Mission Title *">
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g. Planet X – Lander Design Challenge"
                  className={inputCls}
                />
              </FieldWrapper>

              <FieldWrapper label="Subtitle / Tagline">
                <input
                  type="text"
                  value={subtitle}
                  onChange={(e) => setSubtitle(e.target.value)}
                  placeholder="e.g. National Space Engineering Experience"
                  className={inputCls}
                />
              </FieldWrapper>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <FieldWrapper label="URL Slug (Unique)">
                <input
                  type="text"
                  value={slug}
                  onChange={(e) => setSlug(e.target.value)}
                  placeholder="planetx (auto-generated if empty)"
                  className={inputCls}
                />
              </FieldWrapper>

              <FieldWrapper label="Category">
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className={inputCls}
                >
                  {CATEGORIES.map((cat) => (
                    <option key={cat} value={cat}>
                      {cat}
                    </option>
                  ))}
                </select>
              </FieldWrapper>

              <FieldWrapper label="Display Order">
                <input
                  type="number"
                  value={displayOrder}
                  onChange={(e) => setDisplayOrder(Number(e.target.value))}
                  className={inputCls}
                />
              </FieldWrapper>
            </div>

            {/* Card Summary & Cover Image */}
            <FieldWrapper label="Card Summary * (1-2 sentences shown on card)">
              <textarea
                rows={2}
                value={cardSummary}
                onChange={(e) => setCardSummary(e.target.value)}
                placeholder="Brief summary of the mission..."
                className={textareaCls}
              />
            </FieldWrapper>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <FieldWrapper label="Cover Photo URL *">
                <div className="flex flex-col gap-2">
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={coverImageUrl}
                      onChange={(e) => setCoverImageUrl(e.target.value)}
                      placeholder="/assets/img/Case studies/Cards Images/PlanetX.jpg"
                      className={inputCls}
                    />
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept="image/*"
                      className="hidden"
                      onChange={(e) => handleCoverUpload(e.target.files?.[0])}
                    />
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      disabled={uploadingImage}
                      className="h-10 px-3 shrink-0 rounded-xl border border-border bg-muted hover:bg-muted/80 text-xs font-semibold inline-flex items-center gap-1.5"
                    >
                      <Upload size={14} />
                      {uploadingImage ? "…" : "Upload"}
                    </button>
                  </div>
                  {coverImageUrl && (
                    <div className="relative h-24 w-full rounded-xl overflow-hidden border border-border bg-black/40">
                      <img
                        src={resolveWebsiteAsset(coverImageUrl)}
                        alt="Cover Preview"
                        className="w-full h-full object-cover"
                        onError={(e) => {
                          e.currentTarget.style.display = "none"
                        }}
                      />
                    </div>
                  )}
                </div>
              </FieldWrapper>

              <FieldWrapper label="Primary Partner / Host (Card Badge)">
                <div className="flex flex-col gap-2">
                  <input
                    type="text"
                    value={partnerName}
                    onChange={(e) => setPartnerName(e.target.value)}
                    placeholder="e.g. UAE Space Agency (shown on card tooltip)"
                    className={inputCls}
                  />
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={partnerLogoUrl}
                      onChange={(e) => setPartnerLogoUrl(e.target.value)}
                      placeholder="/assets/img/Case studies/Logos/..."
                      className={inputCls}
                    />
                    <input
                      ref={partnerLogoInputRef}
                      type="file"
                      accept="image/*"
                      className="hidden"
                      onChange={(e) => handlePrimaryPartnerUpload(e.target.files?.[0])}
                    />
                    <button
                      type="button"
                      onClick={() => partnerLogoInputRef.current?.click()}
                      disabled={uploadingPrimaryPartner}
                      className="h-10 px-3 shrink-0 rounded-xl border border-border bg-muted hover:bg-muted/80 text-xs font-semibold inline-flex items-center gap-1.5"
                    >
                      <Upload size={14} />
                      {uploadingPrimaryPartner ? "…" : "Upload"}
                    </button>
                  </div>
                  {partnerLogoUrl && (
                    <div className="h-12 w-full px-3 rounded-xl border border-white/10 bg-[#0B0510] flex items-center justify-center">
                      <img
                        src={resolveWebsiteAsset(partnerLogoUrl)}
                        alt="Partner Logo Preview"
                        className="max-h-8 max-w-[140px] object-contain"
                        onError={(e) => {
                          e.currentTarget.style.display = "none"
                        }}
                      />
                    </div>
                  )}
                </div>
              </FieldWrapper>
            </div>

            {/* Status & Featured Flags */}
            <div className="flex items-center gap-6 p-4 rounded-xl border border-border bg-card">
              <label className="flex items-center gap-2 cursor-pointer text-xs font-semibold select-none">
                <input
                  type="checkbox"
                  checked={isPublished}
                  onChange={(e) => setIsPublished(e.target.checked)}
                />
                Published (Visible on Website)
              </label>

              <label className="flex items-center gap-2 cursor-pointer text-xs font-semibold select-none">
                <input
                  type="checkbox"
                  checked={isFeatured}
                  onChange={(e) => setIsFeatured(e.target.checked)}
                />
                Default Featured Mission on Page Load
              </label>
            </div>
          </div>
        )}

        {/* SECTION 2: PARTNERS & COLLABORATIONS */}
        {activeSection === "partners" && (
          <div className="flex flex-col gap-5">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-bold text-foreground">
                  Mission Partners & Collaborations
                </h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Manage the organizations partnering on this mission. These appear in the "In collaboration with" bar.
                </p>
              </div>
              <button
                type="button"
                onClick={() =>
                  setPartners([
                    ...partners,
                    {
                      name: "",
                      role: "In collaboration with",
                      logo_url: "",
                    },
                  ])
                }
                className="h-8 px-3 rounded-xl bg-primary text-primary-foreground text-xs font-semibold inline-flex items-center gap-1.5 shadow-sm hover:opacity-90"
              >
                <Plus size={13} /> Add Partner
              </button>
            </div>

            {/* Partners List */}
            <div className="flex flex-col gap-4">
              {partners.map((p, idx) => (
                <div
                  key={idx}
                  className="p-4 rounded-2xl border border-border bg-card flex flex-col gap-3 transition-all hover:border-primary/30"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold uppercase tracking-wider text-primary">
                      Partner #{idx + 1}
                    </span>
                    <button
                      type="button"
                      onClick={() => setPartners(partners.filter((_, i) => i !== idx))}
                      className="p-1.5 text-red-500 hover:bg-red-500/10 rounded-lg transition-colors text-xs inline-flex items-center gap-1"
                    >
                      <Trash2 size={13} /> Remove
                    </button>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <FieldWrapper label="Partner Organization Name *">
                      <input
                        type="text"
                        value={p.name}
                        onChange={(e) => {
                          const copy = [...partners]
                          copy[idx].name = e.target.value
                          setPartners(copy)
                        }}
                        placeholder="e.g. UAE Space Agency, Planet X, MBRSC"
                        className={inputCls}
                      />
                    </FieldWrapper>

                    <FieldWrapper label="Collaboration Role / Tag">
                      <div className="flex flex-col gap-1.5">
                        <input
                          type="text"
                          value={p.role || ""}
                          onChange={(e) => {
                            const copy = [...partners]
                            copy[idx].role = e.target.value
                            setPartners(copy)
                          }}
                          placeholder="e.g. In collaboration with, Academic Host"
                          className={inputCls}
                        />
                        <div className="flex flex-wrap gap-1">
                          {[
                            "In collaboration with",
                            "In partnership with",
                            "Program Initiative",
                            "Academic Host",
                            "Strategic Partner",
                          ].map((tag) => (
                            <button
                              key={tag}
                              type="button"
                              onClick={() => {
                                const copy = [...partners]
                                copy[idx].role = tag
                                setPartners(copy)
                              }}
                              className="text-[10px] px-2 py-0.5 rounded-md border border-border bg-muted/60 hover:bg-muted text-muted-foreground hover:text-foreground"
                            >
                              {tag}
                            </button>
                          ))}
                        </div>
                      </div>
                    </FieldWrapper>
                  </div>

                  {/* Logo URL and Upload */}
                  <div className="grid grid-cols-1 sm:grid-cols-12 gap-3 items-center">
                    <div className="sm:col-span-8">
                      <FieldWrapper label="Logo Image URL">
                        <div className="flex gap-2">
                          <input
                            type="text"
                            value={p.logo_url || ""}
                            onChange={(e) => {
                              const copy = [...partners]
                              copy[idx].logo_url = e.target.value
                              setPartners(copy)
                            }}
                            placeholder="/assets/img/Case studies/Logos/..."
                            className={inputCls}
                          />
                          <input
                            id={`partner-file-${idx}`}
                            type="file"
                            accept="image/*"
                            className="hidden"
                            onChange={(e) => handlePartnerLogoUpload(idx, e.target.files?.[0])}
                          />
                          <button
                            type="button"
                            onClick={() => document.getElementById(`partner-file-${idx}`)?.click()}
                            disabled={uploadingPartnerIdx === idx}
                            className="h-10 px-3 shrink-0 rounded-xl border border-border bg-muted hover:bg-muted/80 text-xs font-semibold inline-flex items-center gap-1.5"
                          >
                            <Upload size={14} />
                            {uploadingPartnerIdx === idx ? "…" : "Upload"}
                          </button>
                        </div>
                      </FieldWrapper>
                    </div>

                    <div className="sm:col-span-4 flex items-center justify-center sm:justify-start gap-2 pt-4">
                      {p.logo_url ? (
                        <div className="h-16 w-full px-3 rounded-xl border border-white/10 bg-[#0B0510] flex items-center justify-center shadow-inner">
                          <img
                            src={resolveWebsiteAsset(p.logo_url)}
                            alt={p.name}
                            className="max-h-12 max-w-[160px] object-contain filter drop-shadow"
                            onError={(e) => {
                              e.currentTarget.style.display = "none"
                            }}
                          />
                        </div>
                      ) : (
                        <div className="h-16 w-full rounded-xl border border-dashed border-border bg-muted/30 flex items-center justify-center text-xs text-muted-foreground">
                          No Logo
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {partners.length === 0 && (
              <div className="text-center py-8 px-4 border border-dashed border-border rounded-2xl flex flex-col items-center gap-2">
                <span className="text-xs text-muted-foreground">
                  No partner organizations added to this mission yet.
                </span>
                <button
                  type="button"
                  onClick={() =>
                    setPartners([
                      {
                        name: partnerName || "UAE Space Agency",
                        role: "In collaboration with",
                        logo_url: partnerLogoUrl || "",
                      },
                    ])
                  }
                  className="mt-1 h-8 px-3 rounded-xl bg-muted hover:bg-muted/80 text-xs font-semibold text-foreground inline-flex items-center gap-1"
                >
                  <Plus size={13} /> Add First Partner
                </button>
              </div>
            )}
          </div>
        )}

        {/* SECTION 2: OVERVIEW & IMPACT METRICS */}
        {activeSection === "overview_stats" && (
          <div className="flex flex-col gap-5">
            <FieldWrapper label="Mission Overview (Detailed narrative text)">
              <textarea
                rows={4}
                value={overviewText}
                onChange={(e) => setOverviewText(e.target.value)}
                placeholder="Full description of the mission, collaboration, goals, and delivery format..."
                className={textareaCls}
              />
            </FieldWrapper>

            {/* Hero Metric Banner Option (like AGF's 504 out of 520) */}
            <div className="p-4 rounded-2xl border border-border bg-card flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-xs font-bold uppercase tracking-wider text-foreground">
                    Giant Hero Metric Banner
                  </span>
                  <p className="text-xs text-muted-foreground">
                    Display one prominent headline number in a gradient banner (e.g. "504 out of 520").
                  </p>
                </div>
                <label className="flex items-center gap-2 text-xs font-semibold cursor-pointer">
                  <input
                    type="checkbox"
                    checked={heroMetricEnabled}
                    onChange={(e) => setHeroMetricEnabled(e.target.checked)}
                  />
                  Enable Hero Banner
                </label>
              </div>

              {heroMetricEnabled && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
                  <FieldWrapper label="Hero Value">
                    <input
                      type="text"
                      value={heroMetricValue}
                      onChange={(e) => setHeroMetricValue(e.target.value)}
                      placeholder="504 out of 520"
                      className={inputCls}
                    />
                  </FieldWrapper>
                  <FieldWrapper label="Hero Label">
                    <input
                      type="text"
                      value={heroMetricLabel}
                      onChange={(e) => setHeroMetricLabel(e.target.value)}
                      placeholder="Students Trained"
                      className={inputCls}
                    />
                  </FieldWrapper>
                </div>
              )}
            </div>

            {/* Standard Metrics Grid */}
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-xs font-bold uppercase tracking-wider text-foreground">
                    Case Study Numbers & Impact Stats
                  </span>
                  <p className="text-xs text-muted-foreground">
                    Counters displayed on the case study page. The first 2 stats appear directly on the card.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setMetrics([...metrics, { value: "100+", label: "Metric Label" }])}
                  className="h-7 px-2.5 rounded-lg border border-border text-xs font-semibold inline-flex items-center gap-1 hover:bg-muted"
                >
                  <Plus size={12} /> Add Stat
                </button>
              </div>

              {/* Quick Add Presets */}
              <div className="flex flex-wrap items-center gap-1.5 text-xs">
                <span className="text-[11px] text-muted-foreground font-medium">Quick Add:</span>
                {[
                  { value: "1,750+", label: "Students Trained" },
                  { value: "50", label: "Teams" },
                  { value: "100%", label: "Graduation Rate" },
                  { value: "25+", label: "Schools / Universities" },
                  { value: "12 Hours", label: "Curriculum Hours" },
                ].map((preset) => (
                  <button
                    key={preset.label}
                    type="button"
                    onClick={() => setMetrics([...metrics, preset])}
                    className="text-[10px] px-2 py-0.5 rounded-md border border-border bg-muted/60 hover:bg-muted text-muted-foreground hover:text-foreground"
                  >
                    + {preset.label}
                  </button>
                ))}
              </div>

              <div className="flex flex-col gap-2">
                {metrics.map((m, idx) => (
                  <div key={idx} className="flex items-center gap-2 bg-card p-2 rounded-xl border border-border">
                    <span className="text-[11px] font-bold text-muted-foreground w-6 text-center">
                      #{idx + 1}
                    </span>
                    <input
                      type="text"
                      value={m.value}
                      onChange={(e) => {
                        const copy = [...metrics]
                        copy[idx].value = e.target.value
                        setMetrics(copy)
                      }}
                      placeholder="Value (e.g. 1,750+)"
                      className={cn(inputCls, "w-1/3 font-bold")}
                    />
                    <input
                      type="text"
                      value={m.label}
                      onChange={(e) => {
                        const copy = [...metrics]
                        copy[idx].label = e.target.value
                        setMetrics(copy)
                      }}
                      placeholder="Label (e.g. Students Trained)"
                      className={cn(inputCls, "flex-1")}
                    />
                    {idx < 2 && (
                      <span className="text-[10px] px-2 py-0.5 rounded bg-primary/10 text-primary font-semibold whitespace-nowrap hidden sm:inline">
                        Card Stat #{idx + 1}
                      </span>
                    )}
                    <button
                      type="button"
                      onClick={() => setMetrics(metrics.filter((_, i) => i !== idx))}
                      className="p-2 text-red-500 hover:bg-red-500/10 rounded-lg"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* SECTION 3: PHOTO GALLERY */}
        {activeSection === "gallery" && (
          <div className="flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  Gallery Photos (Right 2x2 preview grid + Fullscreen Lightbox)
                </span>
                <p className="text-xs text-muted-foreground">
                  First 3 photos form the preview grid; the 4th tile shows "+N Photos" launching the modal.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <input
                  ref={galleryInputRef}
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={(e) => handleGalleryUpload(e.target.files?.[0])}
                />
                <button
                  type="button"
                  onClick={() => galleryInputRef.current?.click()}
                  disabled={uploadingGallery}
                  className="h-8 px-3 rounded-xl bg-primary text-primary-foreground text-xs font-semibold inline-flex items-center gap-1.5 shadow-sm hover:opacity-90"
                >
                  <Upload size={13} /> {uploadingGallery ? "Uploading…" : "Upload Photo"}
                </button>
                <button
                  type="button"
                  onClick={() => setGalleryImages([...galleryImages, ""])}
                  className="h-8 px-3 rounded-xl border border-border text-xs font-semibold inline-flex items-center gap-1 hover:bg-muted"
                >
                  <Plus size={13} /> Add Photo URL
                </button>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {galleryImages.map((img, idx) => (
                <div key={idx} className="flex items-center gap-2 p-2 rounded-xl border border-border bg-card">
                  {img ? (
                    <img
                      src={resolveWebsiteAsset(img)}
                      alt=""
                      className="w-12 h-12 rounded-lg object-cover bg-muted shrink-0"
                      onError={(e) => {
                        e.currentTarget.style.display = "none"
                      }}
                    />
                  ) : (
                    <div className="w-12 h-12 rounded-lg bg-muted shrink-0 flex items-center justify-center text-muted-foreground text-[10px]">
                      Photo
                    </div>
                  )}
                  <input
                    type="text"
                    value={img}
                    onChange={(e) => {
                      const copy = [...galleryImages]
                      copy[idx] = e.target.value
                      setGalleryImages(copy)
                    }}
                    placeholder="/assets/img/Case studies/.../pic.jpg"
                    className={cn(inputCls, "flex-1 text-xs")}
                  />
                  <button
                    type="button"
                    onClick={() => setGalleryImages(galleryImages.filter((_, i) => i !== idx))}
                    className="p-2 text-red-500 hover:bg-red-500/10 rounded-lg"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>

            {galleryImages.length === 0 && (
              <p className="text-xs text-muted-foreground text-center py-6 border border-dashed border-border rounded-xl">
                No photos in gallery. The overview section will render full-width.
              </p>
            )}
          </div>
        )}

        {/* SECTION 4: HIGHLIGHTS & CHAPTERS */}
        {activeSection === "highlights" && (
          <div className="flex flex-col gap-6">
            {/* Highlights / Capabilities */}
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                    Core Highlights & Capabilities
                  </span>
                  <p className="text-xs text-muted-foreground">
                    Icon cards showcasing key training pillars (e.g. Electrical Integration, SatKit Assembly).
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    setHighlights([
                      ...highlights,
                      { title: "New Capability", description: "Details about this skill or subsystem." },
                    ])
                  }
                  className="h-7 px-2.5 rounded-lg border border-border text-xs font-semibold inline-flex items-center gap-1 hover:bg-muted"
                >
                  <Plus size={12} /> Add Card
                </button>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {highlights.map((h, idx) => (
                  <div key={idx} className="flex flex-col gap-2 p-3 rounded-xl border border-border bg-card">
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        value={h.title}
                        onChange={(e) => {
                          const copy = [...highlights]
                          copy[idx].title = e.target.value
                          setHighlights(copy)
                        }}
                        placeholder="Title (e.g. Mechanical Assembly)"
                        className={cn(inputCls, "font-semibold")}
                      />
                      <button
                        type="button"
                        onClick={() => setHighlights(highlights.filter((_, i) => i !== idx))}
                        className="p-2 text-red-500 hover:bg-red-500/10 rounded-lg shrink-0"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                    <textarea
                      rows={2}
                      value={h.description}
                      onChange={(e) => {
                        const copy = [...highlights]
                        copy[idx].description = e.target.value
                        setHighlights(copy)
                      }}
                      placeholder="Description..."
                      className={textareaCls}
                    />
                  </div>
                ))}
              </div>
            </div>

            {/* Curriculum Chapters Strip */}
            <div className="flex flex-col gap-3 pt-4 border-t border-border">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                    Curriculum Chapters Strip (Optional)
                  </span>
                  <p className="text-xs text-muted-foreground">
                    Numbered badges (e.g. Ch. 1 Intro to Sat, Ch. 2 CDHS, Ch. 3 EPS).
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    setCurriculumChapters([
                      ...curriculumChapters,
                      { chapter_num: `Ch. ${curriculumChapters.length + 1}`, title: "Module Name" },
                    ])
                  }
                  className="h-7 px-2.5 rounded-lg border border-border text-xs font-semibold inline-flex items-center gap-1 hover:bg-muted"
                >
                  <Plus size={12} /> Add Chapter
                </button>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
                {curriculumChapters.map((ch, idx) => (
                  <div key={idx} className="flex flex-col gap-1.5 p-2 rounded-xl border border-border bg-card text-xs">
                    <div className="flex items-center justify-between">
                      <input
                        type="text"
                        value={ch.chapter_num}
                        onChange={(e) => {
                          const copy = [...curriculumChapters]
                          copy[idx].chapter_num = e.target.value
                          setCurriculumChapters(copy)
                        }}
                        className="w-14 font-bold text-primary uppercase text-[10px] bg-transparent focus:outline-none"
                      />
                      <button
                        type="button"
                        onClick={() => setCurriculumChapters(curriculumChapters.filter((_, i) => i !== idx))}
                        className="text-red-500 hover:opacity-80"
                      >
                        <X size={12} />
                      </button>
                    </div>
                    <input
                      type="text"
                      value={ch.title}
                      onChange={(e) => {
                        const copy = [...curriculumChapters]
                        copy[idx].title = e.target.value
                        setCurriculumChapters(copy)
                      }}
                      placeholder="Chapter title"
                      className={cn(inputCls, "h-8 text-xs")}
                    />
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* SECTION 5: STRUCTURE & FORMATS */}
        {activeSection === "structure" && (
          <div className="flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  Program Structure & Formats (Accordions or Cards)
                </span>
                <p className="text-xs text-muted-foreground">
                  Handles 2-Week Bootcamp phases (Online vs OnSite), daily schedules, or Semester vs Break formats.
                </p>
              </div>
              <button
                type="button"
                onClick={() =>
                  setStructureSections([
                    ...structureSections,
                    {
                      id: `sec-${Date.now()}`,
                      badge: `0${structureSections.length + 1}`,
                      title: "New Phase / Format",
                      subtitle: "Phase Description",
                      days: [{ day_title: "Day 1", milestones: ["Activity 1", "Activity 2"] }],
                    },
                  ])
                }
                className="h-8 px-3 rounded-xl border border-border text-xs font-semibold inline-flex items-center gap-1 hover:bg-muted"
              >
                <Plus size={13} /> Add Section
              </button>
            </div>

            <FieldWrapper label="Section Header Title">
              <input
                type="text"
                value={structureTitle}
                onChange={(e) => setStructureTitle(e.target.value)}
                placeholder="Bootcamp Structure / Program Formats"
                className={inputCls}
              />
            </FieldWrapper>

            <div className="flex flex-col gap-4">
              {structureSections.map((sec, idx) => (
                <div key={idx} className="p-4 rounded-2xl border border-border bg-card flex flex-col gap-3">
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={sec.badge || ""}
                      onChange={(e) => {
                        const copy = [...structureSections]
                        copy[idx].badge = e.target.value
                        setStructureSections(copy)
                      }}
                      placeholder="Badge (01)"
                      className="w-16 h-9 px-2 text-xs font-bold text-primary bg-background border border-border rounded-lg text-center"
                    />
                    <input
                      type="text"
                      value={sec.title}
                      onChange={(e) => {
                        const copy = [...structureSections]
                        copy[idx].title = e.target.value
                        setStructureSections(copy)
                      }}
                      placeholder="Title (e.g. Week 1 - Online)"
                      className={cn(inputCls, "flex-1 font-bold")}
                    />
                    <button
                      type="button"
                      onClick={() => setStructureSections(structureSections.filter((_, i) => i !== idx))}
                      className="p-2 text-red-500 hover:bg-red-500/10 rounded-lg"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>

                  <input
                    type="text"
                    value={sec.subtitle || ""}
                    onChange={(e) => {
                      const copy = [...structureSections]
                      copy[idx].subtitle = e.target.value
                      setStructureSections(copy)
                    }}
                    placeholder="Subtitle (e.g. Foundational Skills & Preparation)"
                    className={inputCls}
                  />

                  <input
                    type="text"
                    value={sec.image_url || ""}
                    onChange={(e) => {
                      const copy = [...structureSections]
                      copy[idx].image_url = e.target.value
                      setStructureSections(copy)
                    }}
                    placeholder="Optional Side Image URL (/assets/img/...)"
                    className={inputCls}
                  />
                </div>
              ))}
            </div>

            {structureSections.length === 0 && (
              <p className="text-xs text-muted-foreground text-center py-6 border border-dashed border-border rounded-xl">
                No structure sections added. This section will auto-hide on the public page.
              </p>
            )}
          </div>
        )}

        {/* SECTION 6: VISIBILITY & SPOTLIGHTS */}
        {activeSection === "visibility_spotlights" && (
          <div className="flex flex-col gap-6">
            {/* Visibility Metrics */}
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                    Impact & Visibility Metrics
                  </span>
                  <p className="text-xs text-muted-foreground">
                    Public reach, creator views, or LinkedIn engagement rates (Planet X style).
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    setVisibilityStats([
                      ...visibilityStats,
                      { value: "10,000+", label: "Impressions" },
                    ])
                  }
                  className="h-7 px-2.5 rounded-lg border border-border text-xs font-semibold inline-flex items-center gap-1 hover:bg-muted"
                >
                  <Plus size={12} /> Add Metric
                </button>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {visibilityStats.map((vs, idx) => (
                  <div key={idx} className="flex items-center gap-2 p-2 rounded-xl border border-border bg-card">
                    <input
                      type="text"
                      value={vs.value}
                      onChange={(e) => {
                        const copy = [...visibilityStats]
                        copy[idx].value = e.target.value
                        setVisibilityStats(copy)
                      }}
                      placeholder="Value (e.g. 23,000+)"
                      className={cn(inputCls, "w-1/3")}
                    />
                    <input
                      type="text"
                      value={vs.label}
                      onChange={(e) => {
                        const copy = [...visibilityStats]
                        copy[idx].label = e.target.value
                        setVisibilityStats(copy)
                      }}
                      placeholder="Label (e.g. views on day 4 alone)"
                      className={cn(inputCls, "flex-1 text-xs")}
                    />
                    <button
                      type="button"
                      onClick={() => setVisibilityStats(visibilityStats.filter((_, i) => i !== idx))}
                      className="p-1.5 text-red-500 hover:bg-red-500/10 rounded-lg"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                ))}
              </div>
            </div>

            {/* Spotlights (GITEX, Learner-to-Leader, HCTSat-2) */}
            <div className="flex flex-col gap-3 pt-4 border-t border-border">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                    Spotlights, Showcases & Future Missions
                  </span>
                  <p className="text-xs text-muted-foreground">
                    Feature exhibitions (e.g. GITEX), student instructor stories, or upcoming satellite projects.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    setSpotlights([
                      ...spotlights,
                      {
                        type: "showcase",
                        title: "Presented at GITEX GLOBAL",
                        tag: "Showcase",
                        content: "Description of the showcase...",
                        images: [],
                      },
                    ])
                  }
                  className="h-7 px-2.5 rounded-lg border border-border text-xs font-semibold inline-flex items-center gap-1 hover:bg-muted"
                >
                  <Plus size={12} /> Add Spotlight
                </button>
              </div>

              <div className="flex flex-col gap-3">
                {spotlights.map((sp, idx) => (
                  <div key={idx} className="p-3 rounded-xl border border-border bg-card flex flex-col gap-2.5">
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        value={sp.tag || ""}
                        onChange={(e) => {
                          const copy = [...spotlights]
                          copy[idx].tag = e.target.value
                          setSpotlights(copy)
                        }}
                        placeholder="Tag (e.g. 🌟 Spotlight)"
                        className="w-32 h-9 px-2 text-xs font-bold text-primary bg-background border border-border rounded-lg"
                      />
                      <input
                        type="text"
                        value={sp.title}
                        onChange={(e) => {
                          const copy = [...spotlights]
                          copy[idx].title = e.target.value
                          setSpotlights(copy)
                        }}
                        placeholder="Spotlight Title"
                        className={cn(inputCls, "flex-1 font-bold")}
                      />
                      <button
                        type="button"
                        onClick={() => setSpotlights(spotlights.filter((_, i) => i !== idx))}
                        className="p-2 text-red-500 hover:bg-red-500/10 rounded-lg"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>

                    <textarea
                      rows={2}
                      value={sp.content || ""}
                      onChange={(e) => {
                        const copy = [...spotlights]
                        copy[idx].content = e.target.value
                        setSpotlights(copy)
                      }}
                      placeholder="Story or details..."
                      className={textareaCls}
                    />
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* SECTION 7: TESTIMONIALS & CTA */}
        {activeSection === "voices_cta" && (
          <div className="flex flex-col gap-6">
            {/* Student Testimonials */}
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                    Student Voices & Testimonials
                  </span>
                  <p className="text-xs text-muted-foreground">
                    Quotes from participating students with name, role, and avatar.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    setTestimonials([
                      ...testimonials,
                      {
                        quote: "I learned many things about space systems and real satellites...",
                        author_name: "Student Name",
                        author_role: "Student Participant",
                        badge: "Student Voice",
                      },
                    ])
                  }
                  className="h-7 px-2.5 rounded-lg border border-border text-xs font-semibold inline-flex items-center gap-1 hover:bg-muted"
                >
                  <Plus size={12} /> Add Quote
                </button>
              </div>

              <div className="flex flex-col gap-4">
                {testimonials.map((t, idx) => (
                  <div key={idx} className="p-4 rounded-xl border border-border bg-card flex flex-col gap-2.5">
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        value={t.badge || ""}
                        onChange={(e) => {
                          const copy = [...testimonials]
                          copy[idx].badge = e.target.value
                          setTestimonials(copy)
                        }}
                        placeholder="Badge (e.g. Student Voice)"
                        className="w-36 h-9 px-2 text-xs font-bold text-primary bg-background border border-border rounded-lg"
                      />
                      <input
                        type="text"
                        value={t.author_name}
                        onChange={(e) => {
                          const copy = [...testimonials]
                          copy[idx].author_name = e.target.value
                          setTestimonials(copy)
                        }}
                        placeholder="Student Name"
                        className={cn(inputCls, "flex-1 font-bold")}
                      />
                      <button
                        type="button"
                        onClick={() => setTestimonials(testimonials.filter((_, i) => i !== idx))}
                        className="p-2 text-red-500 hover:bg-red-500/10 rounded-lg"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>

                    <textarea
                      rows={2}
                      value={t.quote}
                      onChange={(e) => {
                        const copy = [...testimonials]
                        copy[idx].quote = e.target.value
                        setTestimonials(copy)
                      }}
                      placeholder="Quote..."
                      className={textareaCls}
                    />

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
                      <input
                        type="text"
                        value={t.author_role}
                        onChange={(e) => {
                          const copy = [...testimonials]
                          copy[idx].author_role = e.target.value
                          setTestimonials(copy)
                        }}
                        placeholder="Role (Student Participant)"
                        className={cn(inputCls, "text-xs")}
                      />
                      <div className="flex items-center gap-2">
                        {t.author_photo_url && (
                          <div className="w-8 h-8 rounded-full overflow-hidden shrink-0 border border-border bg-muted">
                            <img
                              src={resolveWebsiteAsset(t.author_photo_url)}
                              alt=""
                              className="w-full h-full object-cover"
                              onError={(e) => {
                                e.currentTarget.style.display = "none"
                              }}
                            />
                          </div>
                        )}
                        <input
                          type="text"
                          value={t.author_photo_url || ""}
                          onChange={(e) => {
                            const copy = [...testimonials]
                            copy[idx].author_photo_url = e.target.value
                            setTestimonials(copy)
                          }}
                          placeholder="Avatar photo URL (/assets/img/...)"
                          className={cn(inputCls, "text-xs flex-1")}
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Bottom Report / Flyer Link */}
            <div className="p-4 rounded-xl border border-border bg-card flex flex-col gap-3">
              <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                Bottom Download / Report CTA Link (Optional)
              </span>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <FieldWrapper label="CTA Link Label">
                  <input
                    type="text"
                    value={ctaLabel}
                    onChange={(e) => setCtaLabel(e.target.value)}
                    placeholder="Press Here >> Satellite Development Course Flyer"
                    className={inputCls}
                  />
                </FieldWrapper>
                <FieldWrapper label="CTA Link URL or PDF Path">
                  <input
                    type="text"
                    value={ctaUrl}
                    onChange={(e) => setCtaUrl(e.target.value)}
                    placeholder="https://... or /files/flyer.pdf"
                    className={inputCls}
                  />
                </FieldWrapper>
              </div>
            </div>
          </div>
        )}

        {/* Section Stepper Helper */}
        {(() => {
          const curIdx = SECTIONS.findIndex((s) => s.id === activeSection)
          const prevSec = curIdx > 0 ? SECTIONS[curIdx - 1] : null
          const nextSec = curIdx < SECTIONS.length - 1 ? SECTIONS[curIdx + 1] : null
          return (
            <div className="flex items-center justify-between pt-2 border-t border-border/60 text-xs">
              {prevSec ? (
                <button
                  type="button"
                  onClick={() => {
                    setActiveSection(prevSec.id)
                    scrollTabs("left")
                  }}
                  className="px-3 py-1.5 rounded-lg border border-border bg-card text-muted-foreground hover:text-foreground hover:bg-muted font-medium inline-flex items-center gap-1.5 transition-colors"
                >
                  <ChevronLeft size={14} /> Back: {prevSec.label}
                </button>
              ) : (
                <span />
              )}

              {nextSec && (
                <button
                  type="button"
                  onClick={() => {
                    setActiveSection(nextSec.id)
                    scrollTabs("right")
                  }}
                  className="px-3 py-1.5 rounded-lg border border-primary/40 bg-primary/10 text-primary hover:bg-primary/20 font-semibold inline-flex items-center gap-1.5 transition-colors ml-auto"
                >
                  Next: {nextSec.label} <ChevronRight size={14} />
                </button>
              )}
            </div>
          )
        })()}

        {/* Modal Actions */}
        <ModalActions
          onCancel={onClose}
          onConfirm={() => mutation.mutate()}
          loading={mutation.isPending}
          disabled={!title.trim() || !cardSummary.trim() || !coverImageUrl.trim()}
          label={isEdit ? "Save Changes" : "Create Case Study"}
        />
      </div>
    </Modal>
  )
}

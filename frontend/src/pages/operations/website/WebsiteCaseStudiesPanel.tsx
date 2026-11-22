import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Eye,
  EyeOff,
  Layers,
  Pencil,
  Plus,
  Search,
  SlidersHorizontal,
  Trash2,
} from "lucide-react"
import { cn, getErrorMessage } from "@/lib/utils"
import { Spinner } from "@/components/ui/primitives"
import { useToast } from "@/components/ui/toast"
import { Modal, ModalActions } from "@/pages/admin/components/common"
import { WEBSITE_BASE_URL } from "@/components/operations/OrgManagementModals"
import { resolveWebsiteAsset } from "./WebsiteManagement"
import { WebsiteCaseStudiesHeaderModal } from "./WebsiteCaseStudiesHeaderModal"
import { CaseStudySplitEditor } from "./components/ProgramCaseStudiesPanel"
import { SharePagePopover } from "./components/SharePagePopover"
import { getProgramsApi } from "@/api/sessions/programs"
import { getCohortsApi } from "@/api/sessions/cohorts"
import { regenerateCaseStudyTokenApi } from "@/api/programWebPages"
import {
  deleteWebsiteCaseStudy,
  getWebsiteCaseStudies,
  updateWebsiteCaseStudy,
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
  "w-full h-10 rounded-[10px] border border-border bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none"

export function WebsiteCaseStudiesPanel() {
  const queryClient = useQueryClient()
  const toast = useToast()

  const [search, setSearch] = useState("")
  const [selectedCategory, setSelectedCategory] = useState("all")
  // undefined = cards grid, null = creating new case study, string = editing caseStudyId
  const [editorCsId, setEditorCsId] = useState<string | null | undefined>(undefined)
  const [headerModalOpen, setHeaderModalOpen] = useState(false)
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

  const regenTokenMutation = useMutation({
    mutationFn: regenerateCaseStudyTokenApi,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["website-case-studies"] })
      toast.success("Preview link regenerated")
    },
    onError: (e) => toast.error(getErrorMessage(e, "Could not regenerate link")),
  })

  if (editorCsId !== undefined) {
    return (
      <CaseStudySplitEditor
        caseStudyId={editorCsId}
        programs={programs}
        cohorts={cohorts}
        onBack={() => {
          setEditorCsId(undefined)
          void queryClient.invalidateQueries({ queryKey: ["website-case-studies"] })
        }}
        onCreated={(created) => {
          setEditorCsId(created.id)
          void queryClient.invalidateQueries({ queryKey: ["website-case-studies"] })
        }}
      />
    )
  }

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
        <h2 className="text-lg font-bold text-foreground">Case Studies & Missions</h2>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setHeaderModalOpen(true)}
            className="h-9 px-3.5 rounded-[10px] border border-border bg-card hover:bg-muted text-xs font-semibold inline-flex items-center gap-1.5 transition-colors text-foreground cursor-pointer"
          >
            <SlidersHorizontal size={14} /> Page Header & Partners
          </button>
          <button
            type="button"
            onClick={() => setEditorCsId(null)}
            className="h-9 px-4 rounded-[10px] bg-primary text-primary-foreground text-xs font-semibold inline-flex items-center gap-1.5 hover:opacity-90 transition-opacity cursor-pointer"
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
            className="flex flex-col rounded-[10px] border border-border bg-card overflow-hidden transition-all hover:border-primary/40 hover:shadow-lg"
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
                <div className="absolute top-3 left-3 bg-black/70 px-2 py-1 rounded-[10px] border border-white/10 max-h-8 flex items-center">
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
                  <span className="bg-background/90 border border-primary/40 text-primary text-[10px] font-bold px-2 py-0.5 rounded-[10px]">
                    Featured
                  </span>
                )}
                <span className="bg-primary text-primary-foreground text-[10px] font-bold px-2.5 py-0.5 rounded-[10px] uppercase tracking-wider">
                  {item.category}
                </span>
              </div>
            </div>

            {/* Content Body */}
            <div className="p-4 flex flex-col flex-1 gap-2.5">
              <div>
                <h3 className="font-bold text-base text-foreground leading-snug">{item.title}</h3>
                {item.subtitle && (
                  <p className="text-xs text-muted-foreground mt-0.5">{item.subtitle}</p>
                )}
              </div>

              <p className="text-xs text-muted-foreground leading-relaxed flex-1">
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
              <div className="flex items-center justify-between gap-2 pt-3 border-t border-border mt-auto flex-wrap">
                <button
                  type="button"
                  onClick={() =>
                    togglePublishMutation.mutate({
                      id: item.id,
                      is_published: !item.is_published,
                    })
                  }
                  className={cn(
                    "h-8 px-2.5 rounded-[10px] text-xs font-semibold inline-flex items-center gap-1.5 transition-colors cursor-pointer",
                    item.is_published
                      ? "text-emerald-600 dark:text-emerald-400 bg-emerald-500/15 hover:bg-emerald-500/20"
                      : "text-muted-foreground bg-muted hover:text-foreground",
                  )}
                >
                  {item.is_published ? <Eye size={13} /> : <EyeOff size={13} />}
                  {item.is_published ? "Published" : "Draft"}
                </button>

                <div className="flex items-center gap-1.5">
                  <SharePagePopover
                    publicUrl={`${WEBSITE_BASE_URL}/case-studies?mission=${item.slug}`}
                    previewToken={item.preview_token}
                    isPublished={item.is_published}
                    onRegenerate={() => regenTokenMutation.mutate(item.id)}
                    regenerating={regenTokenMutation.isPending}
                  />
                  <button
                    type="button"
                    onClick={() => setEditorCsId(item.id)}
                    className="h-8 px-2.5 rounded-[10px] border border-border text-xs font-semibold text-foreground hover:bg-muted inline-flex items-center gap-1 transition-colors cursor-pointer"
                  >
                    <Pencil size={12} /> Edit
                  </button>
                  <button
                    type="button"
                    onClick={() => setDeleteConfirmId(item.id)}
                    className="h-8 w-8 rounded-[10px] border border-border text-rose-500 hover:bg-rose-500/10 inline-flex items-center justify-center transition-colors cursor-pointer"
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
        <div className="p-12 text-center border border-dashed border-border rounded-[10px] flex flex-col items-center justify-center gap-2">
          <p className="text-sm font-semibold text-foreground">No case studies found</p>
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
    </div>
  )
}

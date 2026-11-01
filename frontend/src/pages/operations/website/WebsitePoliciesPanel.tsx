import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  ExternalLink,
  FileText,
  Pencil,
  Plus,
  Search,
  Trash2,
} from "lucide-react"
import { cn, getErrorMessage } from "@/lib/utils"
import { Spinner } from "@/components/ui/primitives"
import { useToast } from "@/components/ui/toast"
import { ConfirmDialog, Modal, ModalActions } from "@/pages/admin/components/common"
import {
  getAdminWebsitePolicies,
  createWebsitePolicy,
  updateWebsitePolicy,
  deleteWebsitePolicy,
  type WebsitePolicy,
  type WebsitePolicyCreate,
  type WebsitePolicyUpdate,
} from "@/api/websitePolicies"

const WEBSITE_BASE_URL =
  (import.meta.env.VITE_WEBSITE_URL as string | undefined)?.replace(/\/$/, "") ||
  (typeof window !== "undefined" &&
  window.location.hostname !== "localhost" &&
  window.location.hostname !== "127.0.0.1"
    ? "https://spacepoint.ae"
    : "http://localhost:4321")

const inputCls =
  "w-full h-10 rounded-xl border border-border bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none"

const textareaCls =
  "w-full rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none font-mono text-xs"

function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\w\s-]/g, "")
    .replace(/[\s_-]+/g, "-")
    .replace(/^-+|-+$/g, "")
}

const CATEGORY_SUGGESTIONS = [
  "Corporate Governance & Sustainability",
  "Data Protection",
  "Operations & Logistics",
  "Legal Compliance",
  "Community & Safety",
  "Ethics & Safeguarding",
]

export function WebsitePoliciesPanel() {
  const qc = useQueryClient()
  const toast = useToast()

  const [search, setSearch] = useState("")
  const [editingPolicy, setEditingPolicy] = useState<WebsitePolicy | null>(null)
  const [isCreating, setIsCreating] = useState(false)
  const [deletingPolicy, setDeletingPolicy] = useState<WebsitePolicy | null>(null)

  // Form states
  const [formSlug, setFormSlug] = useState("")
  const [formTitle, setFormTitle] = useState("")
  const [formEyebrow, setFormEyebrow] = useState("")
  const [formMeta, setFormMeta] = useState("")
  const [formSummary, setFormSummary] = useState("")
  const [formContentHtml, setFormContentHtml] = useState("")
  const [formOrder, setFormOrder] = useState(0)
  const [formIsActive, setFormIsActive] = useState(true)
  const [formShowInFooter, setFormShowInFooter] = useState(true)
  const [previewTab, setPreviewTab] = useState<"code" | "preview">("code")

  const { data: policies = [], isLoading } = useQuery({
    queryKey: ["admin-website-policies"],
    queryFn: getAdminWebsitePolicies,
  })

  const openCreateModal = () => {
    setFormSlug("")
    setFormTitle("")
    setFormEyebrow("Corporate Governance & Sustainability")
    setFormMeta("Approved by Abdullah AlSalmani, Co-Founder & CEO · " + new Date().toLocaleDateString("en-US", { day: "numeric", month: "long", year: "numeric" }))
    setFormSummary("")
    setFormContentHtml("<h2>1. Purpose and Scope</h2>\n<p>Enter policy text here...</p>")
    setFormOrder(policies.length + 1)
    setFormIsActive(true)
    setFormShowInFooter(true)
    setPreviewTab("code")
    setIsCreating(true)
  }

  const openEditModal = (p: WebsitePolicy) => {
    setEditingPolicy(p)
    setFormSlug(p.slug)
    setFormTitle(p.title)
    setFormEyebrow(p.eyebrow || "")
    setFormMeta(p.meta || "")
    setFormSummary(p.summary || "")
    setFormContentHtml(p.content_html)
    setFormOrder(p.display_order)
    setFormIsActive(p.is_active)
    setFormShowInFooter(p.show_in_footer)
    setPreviewTab("code")
  }

  const handleTitleChange = (newTitle: string) => {
    setFormTitle(newTitle)
    if (isCreating && !formSlug) {
      setFormSlug(slugify(newTitle))
    }
  }

  const createMut = useMutation({
    mutationFn: (payload: WebsitePolicyCreate) => createWebsitePolicy(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-website-policies"] })
      toast.success("Policy created successfully")
      setIsCreating(false)
    },
    onError: (e) => toast.error(getErrorMessage(e, "Could not create policy")),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: WebsitePolicyUpdate }) =>
      updateWebsitePolicy(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-website-policies"] })
      toast.success("Policy updated successfully")
      setEditingPolicy(null)
    },
    onError: (e) => toast.error(getErrorMessage(e, "Could not update policy")),
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteWebsitePolicy(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-website-policies"] })
      toast.success("Policy deleted")
      setDeletingPolicy(null)
    },
    onError: (e) => toast.error(getErrorMessage(e, "Could not delete policy")),
  })

  const handleSave = () => {
    if (!formTitle.trim()) {
      toast.error("Please enter a policy title")
      return
    }
    if (!formSlug.trim()) {
      toast.error("Please enter a valid slug")
      return
    }
    if (!formContentHtml.trim()) {
      toast.error("Policy content cannot be empty")
      return
    }

    const payload = {
      slug: slugify(formSlug.trim()),
      title: formTitle.trim(),
      eyebrow: formEyebrow.trim() || null,
      meta: formMeta.trim() || null,
      summary: formSummary.trim() || null,
      content_html: formContentHtml.trim(),
      display_order: Number(formOrder) || 0,
      is_active: formIsActive,
      show_in_footer: formShowInFooter,
    }

    if (isCreating) {
      createMut.mutate(payload)
    } else if (editingPolicy) {
      updateMut.mutate({ id: editingPolicy.id, payload })
    }
  }

  const filtered = policies.filter((p) => {
    const q = search.toLowerCase().trim()
    if (!q) return true
    return (
      p.title.toLowerCase().includes(q) ||
      p.slug.toLowerCase().includes(q) ||
      (p.eyebrow || "").toLowerCase().includes(q) ||
      (p.meta || "").toLowerCase().includes(q)
    )
  })

  return (
    <div className="flex flex-col gap-6">
      {/* Header & Action Bar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-foreground flex items-center gap-2">
            <FileText className="w-5 h-5 text-primary" />
            Website Policies & Legal Documents
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Manage public legal policies, corporate governance, codes of conduct, and their links in the marketing website footer.
          </p>
        </div>
        <button
          onClick={openCreateModal}
          className="inline-flex items-center gap-1.5 h-9 px-4 rounded-xl bg-primary text-primary-foreground font-semibold text-xs shadow hover:bg-primary/90 transition-colors"
        >
          <Plus size={15} />
          Add Policy
        </button>
      </div>

      {/* Filter / Search Bar */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search policies by title, slug, or category..."
            className="w-full h-9 pl-9 pr-3 rounded-xl border border-border bg-card text-xs text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none"
          />
        </div>
        <div className="text-xs text-muted-foreground ml-auto">
          Showing <span className="font-semibold text-foreground">{filtered.length}</span> of {policies.length} policies
        </div>
      </div>

      {/* Policies List */}
      {isLoading ? (
        <div className="py-12 flex justify-center">
          <Spinner />
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border p-12 text-center bg-card/50">
          <FileText className="w-10 h-10 text-muted-foreground/40 mx-auto mb-3" />
          <p className="text-sm font-semibold text-foreground">No policies found</p>
          <p className="text-xs text-muted-foreground mt-1 max-w-sm mx-auto">
            {search ? "No policies match your search criteria." : "Create your first policy to make it accessible on the website."}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3">
          {filtered.map((p) => {
            const publicUrl = `${WEBSITE_BASE_URL}/policies/${p.slug}`
            return (
              <div
                key={p.id}
                className="group rounded-2xl border border-border bg-card p-4 transition-all hover:border-primary/40 hover:shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4"
              >
                <div className="flex items-start gap-3 min-w-0">
                  <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary flex-shrink-0 mt-0.5">
                    <FileText size={18} />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap mb-1">
                      {p.eyebrow && (
                        <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md bg-primary/10 text-primary border border-primary/20">
                          {p.eyebrow}
                        </span>
                      )}
                      <span
                        className={cn(
                          "text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md border",
                          p.is_active
                            ? "bg-emerald-500/10 text-emerald-600 border-emerald-500/20 dark:text-emerald-400"
                            : "bg-muted text-muted-foreground border-border"
                        )}
                      >
                        {p.is_active ? "Active" : "Draft"}
                      </span>
                      {p.show_in_footer ? (
                        <span className="text-[10px] font-medium px-2 py-0.5 rounded-md bg-purple-500/10 text-purple-600 border border-purple-500/20 dark:text-purple-400">
                          Footer Legal
                        </span>
                      ) : (
                        <span className="text-[10px] font-medium px-2 py-0.5 rounded-md bg-muted text-muted-foreground border border-border">
                          Hidden in Footer
                        </span>
                      )}
                      <span className="text-[11px] text-muted-foreground">Order: #{p.display_order}</span>
                    </div>

                    <h3 className="text-sm font-semibold text-foreground truncate">{p.title}</h3>
                    
                    <div className="flex items-center gap-3 text-xs text-muted-foreground mt-1 flex-wrap">
                      <span className="font-mono text-[11px] text-primary/80">/policies/{p.slug}</span>
                      {p.meta && <span>• {p.meta}</span>}
                      {p.updated_at && (
                        <span>
                          • Rev: {new Date(p.updated_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2 self-end md:self-center flex-shrink-0">
                  <a
                    href={publicUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    title="View live page on website"
                    className="inline-flex items-center gap-1.5 h-8 px-2.5 rounded-lg border border-border text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                  >
                    <ExternalLink size={13} />
                    <span className="hidden sm:inline">View Live</span>
                  </a>

                  <button
                    onClick={() => openEditModal(p)}
                    className="inline-flex items-center gap-1.5 h-8 px-2.5 rounded-lg border border-border text-xs font-medium text-foreground hover:bg-muted transition-colors"
                  >
                    <Pencil size={13} />
                    Edit
                  </button>

                  <button
                    onClick={() => setDeletingPolicy(p)}
                    className="inline-flex items-center justify-center w-8 h-8 rounded-lg border border-border text-muted-foreground hover:text-red-500 hover:border-red-500/30 hover:bg-red-500/10 transition-colors"
                    title="Delete policy"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Create / Edit Policy Modal */}
      {(isCreating || editingPolicy) && (
        <Modal
          title={isCreating ? "Add New Policy Document" : `Edit Policy: ${editingPolicy?.title}`}
          onClose={() => {
            setIsCreating(false)
            setEditingPolicy(null)
          }}
          maxWidth="sm:max-w-4xl max-w-4xl"
        >
          <div className="flex flex-col gap-4 max-h-[70vh] overflow-y-auto pr-1">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">
                  Policy Title *
                </label>
                <input
                  type="text"
                  value={formTitle}
                  onChange={(e) => handleTitleChange(e.target.value)}
                  placeholder="e.g. Anti-Bribery & Anti-Corruption Policy"
                  className={inputCls}
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">
                  URL Slug * (spacepoint.ae/policies/...)
                </label>
                <input
                  type="text"
                  value={formSlug}
                  onChange={(e) => setFormSlug(e.target.value)}
                  placeholder="e.g. anti-bribery"
                  className={inputCls}
                />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">
                  Category / Eyebrow Badge
                </label>
                <input
                  type="text"
                  value={formEyebrow}
                  onChange={(e) => setFormEyebrow(e.target.value)}
                  placeholder="e.g. Corporate Governance & Sustainability"
                  className={inputCls}
                />
                <div className="flex items-center gap-1.5 flex-wrap mt-1.5">
                  <span className="text-[10px] text-muted-foreground">Presets:</span>
                  {CATEGORY_SUGGESTIONS.map((cat) => (
                    <button
                      key={cat}
                      type="button"
                      onClick={() => setFormEyebrow(cat)}
                      className="text-[10px] px-1.5 py-0.5 rounded bg-muted hover:bg-muted-foreground/20 text-muted-foreground hover:text-foreground transition-colors"
                    >
                      {cat.split(" ")[0]}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">
                  Approval & Revision Metadata
                </label>
                <input
                  type="text"
                  value={formMeta}
                  onChange={(e) => setFormMeta(e.target.value)}
                  placeholder="e.g. Approved by Abdullah AlSalmani, Co-Founder & CEO · 25 October 2026"
                  className={inputCls}
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">
                Summary / SEO Description
              </label>
              <input
                type="text"
                value={formSummary}
                onChange={(e) => setFormSummary(e.target.value)}
                placeholder="Short 1-2 sentence description for search engines and social cards"
                className={inputCls}
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 p-3 rounded-xl bg-card border border-border">
              <div>
                <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">
                  Display Order
                </label>
                <input
                  type="number"
                  value={formOrder}
                  onChange={(e) => setFormOrder(Number(e.target.value))}
                  className={inputCls}
                />
              </div>

              <div className="flex flex-col justify-center">
                <label className="flex items-center gap-2 cursor-pointer pt-4">
                  <input
                    type="checkbox"
                    checked={formIsActive}
                    onChange={(e) => setFormIsActive(e.target.checked)}
                    className="w-4 h-4 rounded text-primary border-border focus:ring-primary"
                  />
                  <span className="text-xs font-medium text-foreground">Active (Visible on Website)</span>
                </label>
              </div>

              <div className="flex flex-col justify-center">
                <label className="flex items-center gap-2 cursor-pointer pt-4">
                  <input
                    type="checkbox"
                    checked={formShowInFooter}
                    onChange={(e) => setFormShowInFooter(e.target.checked)}
                    className="w-4 h-4 rounded text-primary border-border focus:ring-primary"
                  />
                  <span className="text-xs font-medium text-foreground">Show in Website Footer</span>
                </label>
              </div>
            </div>

            {/* Content Editor & Live Preview */}
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  Policy Content (HTML / Rich Structure) *
                </label>
                <div className="flex items-center rounded-lg border border-border p-0.5 bg-muted/40">
                  <button
                    type="button"
                    onClick={() => setPreviewTab("code")}
                    className={cn(
                      "px-2.5 py-1 text-xs rounded-md font-medium transition-colors",
                      previewTab === "code"
                        ? "bg-card text-foreground shadow-sm"
                        : "text-muted-foreground hover:text-foreground"
                    )}
                  >
                    HTML Source
                  </button>
                  <button
                    type="button"
                    onClick={() => setPreviewTab("preview")}
                    className={cn(
                      "px-2.5 py-1 text-xs rounded-md font-medium transition-colors",
                      previewTab === "preview"
                        ? "bg-card text-foreground shadow-sm"
                        : "text-muted-foreground hover:text-foreground"
                    )}
                  >
                    Live Preview
                  </button>
                </div>
              </div>

              {previewTab === "code" ? (
                <div>
                  <textarea
                    rows={16}
                    value={formContentHtml}
                    onChange={(e) => setFormContentHtml(e.target.value)}
                    placeholder="<h2>1. Purpose and Commitment</h2><p>Policy content...</p>"
                    className={textareaCls}
                  />
                  <p className="text-[11px] text-muted-foreground mt-1">
                    Supports semantic HTML tags: <code>&lt;h2&gt;</code>, <code>&lt;p&gt;</code>, <code>&lt;ul&gt;</code>, <code>&lt;li&gt;</code>, <code>&lt;table&gt;</code>, <code>&lt;strong&gt;</code>.
                  </p>
                </div>
              ) : (
                <div className="rounded-2xl border border-border bg-[#0B0510] text-gray-200 p-6 min-h-[350px] max-h-[500px] overflow-y-auto">
                  <div className="max-w-2xl mx-auto space-y-4">
                    {formEyebrow && (
                      <span className="inline-block text-[10px] font-bold uppercase tracking-wider text-purple-400 bg-purple-500/10 px-2.5 py-1 rounded-full border border-purple-500/20">
                        {formEyebrow}
                      </span>
                    )}
                    <h1 className="text-2xl font-bold text-white">{formTitle || "Policy Title"}</h1>
                    {formMeta && <p className="text-xs font-mono text-gray-400">{formMeta}</p>}
                    <hr className="border-white/10 my-4" />
                    <div
                      className="text-sm leading-relaxed text-gray-300 space-y-4 [&_h2]:text-lg [&_h2]:font-bold [&_h2]:text-white [&_h2]:mt-6 [&_h2]:mb-2 [&_h3]:text-base [&_h3]:font-semibold [&_h3]:text-purple-300 [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:space-y-1 [&_table]:w-full [&_table]:border-collapse [&_th]:border [&_th]:border-white/10 [&_th]:p-2 [&_th]:bg-white/5 [&_td]:border [&_td]:border-white/10 [&_td]:p-2"
                      dangerouslySetInnerHTML={{ __html: formContentHtml }}
                    />
                  </div>
                </div>
              )}
            </div>
          </div>

          <ModalActions
            onCancel={() => {
              setIsCreating(false)
              setEditingPolicy(null)
            }}
            onConfirm={handleSave}
            loading={createMut.isPending || updateMut.isPending}
            label={isCreating ? "Create Policy" : "Save Changes"}
          />
        </Modal>
      )}

      {/* Delete Confirmation Modal */}
      {deletingPolicy && (
        <ConfirmDialog
          title="Delete Policy"
          description={`Are you sure you want to delete "${deletingPolicy.title}"? This will remove the policy from the website and the footer immediately.`}
          confirmLabel="Delete Policy"
          destructive
          pending={deleteMut.isPending}
          onCancel={() => setDeletingPolicy(null)}
          onConfirm={() => deleteMut.mutate(deletingPolicy.id)}
        />
      )}
    </div>
  )
}

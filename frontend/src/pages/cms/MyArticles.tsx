import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { isAxiosError } from "axios"
import { marked } from "marked"
import { FileText, Pencil, Plus, Send } from "lucide-react"
import { cn } from "@/lib/utils"
import { PageHeader, Spinner } from "@/components/ui/primitives"
import { Modal, ModalActions } from "@/pages/admin/components/common"
import { AssetField } from "@/pages/operations/website/WebsiteManagement"
import { useToast } from "@/components/ui/toast"
import { useAuth } from "@/context/AuthContext"
import {
  createArticle,
  getMyArticles,
  submitArticle,
  updateArticle,
  type ArticleStatus,
  type WebsiteArticle,
} from "@/api/articles"

const STATUS_STYLES: Record<string, string> = {
  draft: "bg-muted text-muted-foreground border-border",
  submitted: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20",
  in_review: "bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/20",
  changes_requested: "bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/20",
  published: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20",
  archived: "bg-muted text-muted-foreground border-border",
}

const STATUS_LABELS: Record<string, string> = {
  draft: "Draft",
  submitted: "Submitted",
  in_review: "In Review",
  changes_requested: "Changes Requested",
  published: "Published",
  archived: "Archived",
}

function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status
}

function errorDetail(e: unknown, fallback: string): string {
  if (isAxiosError(e)) {
    const detail = (e.response?.data as { detail?: unknown } | undefined)?.detail
    if (typeof detail === "string") return detail
  } else if (e instanceof Error) {
    return e.message
  }
  return fallback
}

/**
 * Contributor dashboard (Step 5) — draft technical articles in Markdown,
 * track them through the editorial queue, and read reviewer feedback.
 * Any authenticated portal user can author; publishing stays admin-only.
 */
export default function MyArticles() {
  const qc = useQueryClient()
  const toast = useToast()
  const { isAdmin } = useAuth()
  const [editor, setEditor] = useState<{ open: boolean; article: WebsiteArticle | null }>({
    open: false,
    article: null,
  })

  const { data: articles = [], isLoading, isError } = useQuery({
    queryKey: ["my-articles"],
    queryFn: getMyArticles,
  })

  const submit = useMutation({
    mutationFn: (id: string) => submitArticle(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["my-articles"] })
      toast.success("Submitted for review — editors will take it from here")
    },
    onError: (e) => toast.error(errorDetail(e, "Could not submit this article")),
  })

  if (isLoading) return <Spinner />
  if (isError) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader
          title="My Articles"
          subtitle="Draft technical articles and follow them through editorial review."
        />
        <p className="text-sm text-red-600 dark:text-red-400">
          Could not load your articles. Check your connection and try again.
        </p>
      </div>
    )
  }

  const submittable = (status: string) => status === "draft" || status === "changes_requested"
  const editable = (status: string) =>
    isAdmin || status === "draft" || status === "changes_requested" || status === "archived"

  return (
    <div className="flex flex-col gap-6 max-w-4xl">
      <PageHeader
        title="My Articles"
        subtitle="Draft technical articles in Markdown — editors review and publish the best ones to spacepoint.ae/insights."
        action={
          <button
            onClick={() => setEditor({ open: true, article: null })}
            className="h-10 px-5 bg-primary text-primary-foreground text-sm font-semibold rounded-xl hover:opacity-90 inline-flex items-center gap-1.5"
          >
            <Plus size={15} /> Write Article
          </button>
        }
      />

      <div className="flex flex-col gap-3">
        {articles.map((a) => (
          <article key={a.id} className="rounded-2xl border border-border bg-card p-5 flex flex-col gap-3">
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <div className="flex items-center gap-2 flex-wrap">
                <FileText size={15} className="text-muted-foreground shrink-0" />
                <h3 className="text-sm font-semibold text-foreground">{a.title}</h3>
                <span
                  className={cn(
                    "inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold tracking-wide uppercase border",
                    STATUS_STYLES[a.status] ?? STATUS_STYLES.draft,
                  )}
                >
                  {statusLabel(a.status)}
                </span>
                <span className="text-[11px] text-muted-foreground uppercase tracking-wider">
                  {a.category}
                </span>
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                {editable(a.status) && (
                  <button
                    onClick={() => setEditor({ open: true, article: a })}
                    className="h-8 px-3 border border-border text-xs font-medium rounded-lg hover:bg-muted text-foreground inline-flex items-center gap-1"
                  >
                    <Pencil size={13} /> Edit
                  </button>
                )}
                {submittable(a.status) && (
                  <button
                    onClick={() => submit.mutate(a.id)}
                    disabled={submit.isPending}
                    className="h-8 px-3 bg-primary text-primary-foreground text-xs font-semibold rounded-lg hover:opacity-90 disabled:opacity-40 inline-flex items-center gap-1"
                  >
                    <Send size={13} /> Submit
                  </button>
                )}
              </div>
            </div>

            {a.status === "changes_requested" && a.reviewer_feedback && (
              <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-xs leading-relaxed">
                <p className="font-semibold text-red-600 dark:text-red-400 mb-1">
                  Reviewer requested changes
                </p>
                <p className="text-foreground/90">{a.reviewer_feedback}</p>
              </div>
            )}

            {a.summary && (
              <p className="text-xs text-muted-foreground leading-relaxed line-clamp-2">{a.summary}</p>
            )}
            <p className="text-[11px] text-muted-foreground tabular-nums">
              Updated {new Date(a.updated_at).toLocaleString()}
              {a.status === "published" && a.published_at
                ? ` · Live since ${new Date(a.published_at).toLocaleDateString()}`
                : ""}
            </p>
          </article>
        ))}
        {articles.length === 0 && (
          <div className="rounded-2xl border border-dashed border-border p-10 text-center">
            <p className="text-sm font-semibold text-foreground">No articles yet</p>
            <p className="text-xs text-muted-foreground mt-1 mb-4">
              Write your first technical article — workshops, missions, engineering deep-dives.
            </p>
            <button
              onClick={() => setEditor({ open: true, article: null })}
              className="h-9 px-4 bg-primary text-primary-foreground text-sm font-semibold rounded-xl hover:opacity-90 inline-flex items-center gap-1.5"
            >
              <Plus size={15} /> Write Article
            </button>
          </div>
        )}
      </div>

      {editor.open && (
        <ArticleEditor
          key={editor.article?.id ?? "new"}
          article={editor.article}
          onClose={() => setEditor({ open: false, article: null })}
        />
      )}
    </div>
  )
}

function ArticleEditor({
  article,
  onClose,
}: {
  article: WebsiteArticle | null
  onClose: () => void
}) {
  const qc = useQueryClient()
  const toast = useToast()
  const { isAdmin } = useAuth()
  const [tab, setTab] = useState<"write" | "preview">("write")
  const [title, setTitle] = useState(article?.title ?? "")
  const [category, setCategory] = useState(article?.category ?? "EDUCATION")
  const [summary, setSummary] = useState(article?.summary ?? "")
  const [coverUrl, setCoverUrl] = useState(article?.cover_image_url ?? "")
  const [markdown, setMarkdown] = useState(article?.content_markdown ?? "")

  const save = useMutation({
    mutationFn: () => {
      if (!title.trim()) throw new Error("Title is required")
      if (!markdown.trim()) throw new Error("Article body is required")
      const payload = {
        title: title.trim(),
        summary: summary.trim() || null,
        content_markdown: markdown,
        category: category.trim().toUpperCase() || "EDUCATION",
        cover_image_url: coverUrl.trim() || null,
      }
      return article ? updateArticle(article.id, payload) : createArticle(payload)
    },
    onSuccess: (saved) => {
      qc.invalidateQueries({ queryKey: ["my-articles"] })
      qc.invalidateQueries({ queryKey: ["website-articles"] })
      toast.success(
        article ? "Draft updated" : `Draft “${saved.title}” created — submit it when ready`,
      )
      onClose()
    },
    onError: (e) => toast.error(errorDetail(e, "Could not save this article")),
  })

  // Mirrors the backend guard: authors edit drafts/revisions, admins anything.
  const canEdit =
    isAdmin ||
    !article ||
    ["draft", "changes_requested", "archived"].includes(article.status as ArticleStatus)

  return (
    <Modal title={article ? "Edit Draft" : "Write Article"} onClose={onClose} maxWidth="sm:max-w-3xl max-w-3xl">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <label className="flex flex-col gap-1.5 sm:col-span-2">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Title
          </span>
          <input
            type="text" value={title} onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. How We Tracked Our First Balloon Payload"
            className="h-10 px-3 bg-background border border-border rounded-xl text-sm focus:outline-none focus:border-primary text-foreground"
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Category
          </span>
          <input
            type="text" value={category} onChange={(e) => setCategory(e.target.value)}
            placeholder="EDUCATION"
            className="h-10 px-3 bg-background border border-border rounded-xl text-sm focus:outline-none focus:border-primary text-foreground uppercase"
          />
        </label>
        <AssetField
          label="Cover Image"
          value={coverUrl}
          onChange={setCoverUrl}
          accept="image/*"
          placeholder="https://… or upload cover image (optional)"
          aspect={16 / 9}
          aspectHint="16:9 Cover"
        />
        <label className="flex flex-col gap-1.5 sm:col-span-2">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Summary
          </span>
          <input
            type="text" value={summary} onChange={(e) => setSummary(e.target.value)}
            placeholder="One-line teaser shown on the article card… (optional)"
            className="h-10 px-3 bg-background border border-border rounded-xl text-sm focus:outline-none focus:border-primary text-foreground"
          />
        </label>
      </div>

      <div className="inline-flex rounded-xl bg-muted/60 p-1 ring-1 ring-border self-start">
        {(["write", "preview"] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={cn(
              "px-4 py-1.5 rounded-lg text-xs font-semibold transition-all capitalize",
              tab === t ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "write" ? (
        <textarea
          value={markdown}
          onChange={(e) => setMarkdown(e.target.value)}
          rows={14}
          placeholder={"## Heading\n\nWrite in **Markdown** — headings, *emphasis*, lists, and [links](https://…)."}
          className="w-full shrink-0 px-3 py-2 border border-border bg-background text-foreground rounded-xl text-sm resize-y font-mono"
        />
      ) : (
        <div
          className="w-full min-h-60 max-h-96 overflow-y-auto shrink-0 px-4 py-3 border border-border bg-background rounded-xl text-sm text-foreground markdown-preview"
          // Live preview of the author's own draft. The public site only
          // ever renders the server-sanitized content_html.
          dangerouslySetInnerHTML={{ __html: marked.parse(markdown || "*Nothing to preview yet…*") as string }}
        />
      )}

      {!canEdit && (
        <p className="text-xs text-amber-600 dark:text-amber-400">
          This article is already in the review pipeline — only editors can change it now.
        </p>
      )}

      <ModalActions
        onCancel={onClose}
        onConfirm={() => save.mutate()}
        loading={save.isPending}
        disabled={!title.trim() || !markdown.trim() || !canEdit}
        label={article ? "Save draft" : "Create draft"}
      />
    </Modal>
  )
}

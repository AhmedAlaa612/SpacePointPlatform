import { api } from "./client"

export type ArticleStatus =
  | "draft"
  | "submitted"
  | "in_review"
  | "changes_requested"
  | "published"
  | "archived"

export interface WebsiteArticle {
  id: string
  slug: string
  title: string
  summary: string | null
  content_html: string
  category: string
  author_display_name: string
  author_role: string | null
  author_initials: string | null
  cover_image_url: string | null
  featured_order: number
  published_at: string | null
  created_at: string
  // Contributor / admin view extras
  status: ArticleStatus | string
  content_markdown: string
  reviewer_feedback: string | null
  updated_at: string
}

export interface ArticleCreate {
  title: string
  summary?: string | null
  content_markdown: string
  category?: string
  cover_image_url?: string | null
  author_display_name?: string | null
  author_role?: string | null
  author_initials?: string | null
}

export type ArticleUpdate = Partial<
  Pick<
    WebsiteArticle,
    | "title"
    | "summary"
    | "content_markdown"
    | "category"
    | "cover_image_url"
    | "featured_order"
    | "author_display_name"
    | "author_role"
    | "author_initials"
  >
>

export type ReviewAction = "approve" | "request_changes" | "unpublish"

// ── Contributor ─────────────────────────────────────────────────────────────

export const getMyArticles = () =>
  api.get<WebsiteArticle[]>("/articles/me").then((r) => r.data)

export const createArticle = (payload: ArticleCreate) =>
  api.post<WebsiteArticle>("/articles", payload).then((r) => r.data)

export const updateArticle = (id: string, payload: ArticleUpdate) =>
  api.put<WebsiteArticle>(`/articles/${id}`, payload).then((r) => r.data)

export const submitArticle = (id: string) =>
  api.post<WebsiteArticle>(`/articles/${id}/submit`).then((r) => r.data)

// ── Admin editorial queue ───────────────────────────────────────────────────

export const getAllArticles = () =>
  api.get<WebsiteArticle[]>("/admin/website/articles").then((r) => r.data)

export const reviewArticle = (id: string, action: ReviewAction, feedback?: string) =>
  api
    .post<WebsiteArticle>(`/admin/website/articles/${id}/review`, { action, feedback })
    .then((r) => r.data)

export const unpublishArticle = (id: string) =>
  api.post<WebsiteArticle>(`/admin/website/articles/${id}/unpublish`).then((r) => r.data)

export const deleteArticle = (id: string) =>
  api.delete(`/admin/website/articles/${id}`).then((r) => r.data)

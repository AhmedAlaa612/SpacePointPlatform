import { api } from "./client"

// ── FAQs ────────────────────────────────────────────────────────────────────

export interface WebsiteFaq {
  id: string
  category: string
  question: string
  answer: string
  display_order: number
  is_active: boolean
  created_at: string
  updated_at: string
}

export type WebsiteFaqCreate = Pick<
  WebsiteFaq,
  "category" | "question" | "answer" | "display_order" | "is_active"
>

export type WebsiteFaqUpdate = Partial<
  Pick<WebsiteFaq, "category" | "question" | "answer" | "display_order" | "is_active">
>

export const getWebsiteFaqs = () =>
  api.get<WebsiteFaq[]>("/admin/website/faqs").then((r) => r.data)

export const createWebsiteFaq = (payload: WebsiteFaqCreate) =>
  api.post<WebsiteFaq>("/admin/website/faqs", payload).then((r) => r.data)

export const updateWebsiteFaq = (id: string, payload: WebsiteFaqUpdate) =>
  api.put<WebsiteFaq>(`/admin/website/faqs/${id}`, payload).then((r) => r.data)

export const deleteWebsiteFaq = (id: string) =>
  api.delete(`/admin/website/faqs/${id}`).then((r) => r.data)

// ── Media clippings ─────────────────────────────────────────────────────────

export interface WebsiteMediaClipping {
  id: string
  publisher_name: string
  article_title: string
  article_url: string
  published_date: string
  logo_url: string | null
  is_arabic: boolean
  snippet: string | null
  display_order: number
  is_active: boolean
  created_at: string
  updated_at: string
}

export type WebsiteMediaCreate = Pick<
  WebsiteMediaClipping,
  | "publisher_name"
  | "article_title"
  | "article_url"
  | "published_date"
  | "logo_url"
  | "is_arabic"
  | "snippet"
  | "display_order"
  | "is_active"
>

export type WebsiteMediaUpdate = Partial<
  Pick<
    WebsiteMediaClipping,
    | "publisher_name"
    | "article_title"
    | "article_url"
    | "published_date"
    | "logo_url"
    | "is_arabic"
    | "snippet"
    | "display_order"
    | "is_active"
  >
>

export const getWebsiteMedia = () =>
  api.get<WebsiteMediaClipping[]>("/admin/website/media").then((r) => r.data)

export const createWebsiteMedia = (payload: WebsiteMediaCreate) =>
  api.post<WebsiteMediaClipping>("/admin/website/media", payload).then((r) => r.data)

export const updateWebsiteMedia = (id: string, payload: WebsiteMediaUpdate) =>
  api.put<WebsiteMediaClipping>(`/admin/website/media/${id}`, payload).then((r) => r.data)

export const deleteWebsiteMedia = (id: string) =>
  api.delete(`/admin/website/media/${id}`).then((r) => r.data)

// ── Newsletters ─────────────────────────────────────────────────────────────

export interface WebsiteNewsletter {
  id: string
  title: string
  issue_date: string
  cover_url: string | null
  file_url: string
  display_order: number
  is_active: boolean
  created_at: string
  updated_at: string
}

export type WebsiteNewsletterCreate = Pick<
  WebsiteNewsletter,
  "title" | "issue_date" | "cover_url" | "file_url" | "display_order" | "is_active"
>

export type WebsiteNewsletterUpdate = Partial<
  Pick<
    WebsiteNewsletter,
    "title" | "issue_date" | "cover_url" | "file_url" | "display_order" | "is_active"
  >
>

export const getWebsiteNewsletters = () =>
  api.get<WebsiteNewsletter[]>("/admin/website/newsletters").then((r) => r.data)

export const createWebsiteNewsletter = (payload: WebsiteNewsletterCreate) =>
  api.post<WebsiteNewsletter>("/admin/website/newsletters", payload).then((r) => r.data)

export const updateWebsiteNewsletter = (id: string, payload: WebsiteNewsletterUpdate) =>
  api.put<WebsiteNewsletter>(`/admin/website/newsletters/${id}`, payload).then((r) => r.data)

export const deleteWebsiteNewsletter = (id: string) =>
  api.delete(`/admin/website/newsletters/${id}`).then((r) => r.data)

// ── Leads ───────────────────────────────────────────────────────────────────

export interface WebsiteLead {
  id: string
  email: string
  lead_type: string
  status: string
  created_at: string
}

export const getWebsiteLeads = (type: string = "newsletter") =>
  api.get<WebsiteLead[]>("/admin/website/leads", { params: { type } }).then((r) => r.data)

import { api } from "./client"

export interface WebsitePolicy {
  id: string
  slug: string
  title: string
  eyebrow?: string | null
  meta?: string | null
  summary?: string | null
  content_html: string
  display_order: number
  is_active: boolean
  show_in_footer: boolean
  created_at: string
  updated_at: string
}

export interface WebsitePolicySummary {
  id: string
  slug: string
  title: string
  eyebrow?: string | null
  meta?: string | null
  summary?: string | null
  display_order: number
  is_active: boolean
  show_in_footer: boolean
  updated_at: string
}

export interface WebsitePolicyCreate {
  slug: string
  title: string
  eyebrow?: string | null
  meta?: string | null
  summary?: string | null
  content_html: string
  display_order?: number
  is_active?: boolean
  show_in_footer?: boolean
}

export interface WebsitePolicyUpdate {
  slug?: string
  title?: string
  eyebrow?: string | null
  meta?: string | null
  summary?: string | null
  content_html?: string
  display_order?: number
  is_active?: boolean
  show_in_footer?: boolean
}

export const getAdminWebsitePolicies = () =>
  api.get<WebsitePolicy[]>("/admin/website/policies").then((r) => r.data)

export const getAdminWebsitePolicy = (id: string) =>
  api.get<WebsitePolicy>(`/admin/website/policies/${id}`).then((r) => r.data)

export const createWebsitePolicy = (payload: WebsitePolicyCreate) =>
  api.post<WebsitePolicy>("/admin/website/policies", payload).then((r) => r.data)

export const updateWebsitePolicy = (id: string, payload: WebsitePolicyUpdate) =>
  api.put<WebsitePolicy>(`/admin/website/policies/${id}`, payload).then((r) => r.data)

export const deleteWebsitePolicy = (id: string) =>
  api.delete(`/admin/website/policies/${id}`).then((r) => r.data)

export const getPublicWebsitePolicies = () =>
  api.get<WebsitePolicySummary[]>("/public/website/policies").then((r) => r.data)

export const getPublicWebsitePolicy = (slug: string) =>
  api.get<WebsitePolicy>(`/public/website/policies/${slug}`).then((r) => r.data)

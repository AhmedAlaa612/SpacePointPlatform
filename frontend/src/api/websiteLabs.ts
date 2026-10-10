import { api } from "./client"

export interface WebsiteLabProject {
  id: string
  title: string
  slug: string
  badges: string[]
  description: string
  project_url: string
  cta_label: string
  cover_image_url: string | null
  display_order: number
  is_active: boolean
  created_at: string
  updated_at: string
}

export type WebsiteLabCreate = Omit<
  Pick<
    WebsiteLabProject,
    | "title"
    | "slug"
    | "badges"
    | "description"
    | "project_url"
    | "cta_label"
    | "cover_image_url"
    | "display_order"
    | "is_active"
  >,
  "slug"
> & { slug?: string }

export type WebsiteLabUpdate = Partial<
  Pick<
    WebsiteLabProject,
    | "title"
    | "slug"
    | "badges"
    | "description"
    | "project_url"
    | "cta_label"
    | "cover_image_url"
    | "display_order"
    | "is_active"
  >
>

export const getWebsiteLabs = () =>
  api.get<WebsiteLabProject[]>("/admin/website/labs").then((r) => r.data)

export const createWebsiteLab = (payload: WebsiteLabCreate) =>
  api.post<WebsiteLabProject>("/admin/website/labs", payload).then((r) => r.data)

export const updateWebsiteLab = (id: string, payload: WebsiteLabUpdate) =>
  api.put<WebsiteLabProject>(`/admin/website/labs/${id}`, payload).then((r) => r.data)

export const deleteWebsiteLab = (id: string) =>
  api.delete(`/admin/website/labs/${id}`).then((r) => r.data)

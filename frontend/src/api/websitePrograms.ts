import { api } from "./client"

export interface WebsiteProgram {
  id: string
  slug: string
  title: string
  tagline: string | null
  category: string
  level: string
  duration: string
  price_aed: number
  compare_at_price_aed: number | null
  badge_text: string | null
  features_list: string[]
  syllabus_url: string | null
  display_order: number
  is_published: boolean
  created_at: string
  updated_at: string
}

export type WebsiteProgramUpdate = Partial<
  Pick<
    WebsiteProgram,
    | "title"
    | "tagline"
    | "category"
    | "level"
    | "duration"
    | "price_aed"
    | "compare_at_price_aed"
    | "badge_text"
    | "features_list"
    | "syllabus_url"
    | "display_order"
    | "is_published"
  >
>

export const getWebsitePrograms = () =>
  api.get<WebsiteProgram[]>("/admin/website/programs").then((r) => r.data)

export const updateWebsiteProgram = (id: string, payload: WebsiteProgramUpdate) =>
  api.put<WebsiteProgram>(`/admin/website/programs/${id}`, payload).then((r) => r.data)

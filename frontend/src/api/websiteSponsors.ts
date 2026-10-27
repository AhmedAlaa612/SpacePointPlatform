import { api } from "./client"

export type SponsorTier = "client" | "partner" | "supporter" | "academic" | "industry_leader"

export interface WebsiteSponsor {
  id: string
  name: string
  logo_url: string
  logo_hover_url?: string | null
  website_url: string | null
  tier: SponsorTier | string
  display_order: number
  is_active: boolean
  created_at: string
  updated_at: string
}

export type WebsiteSponsorCreate = Pick<
  WebsiteSponsor,
  "name" | "logo_url" | "logo_hover_url" | "tier" | "website_url" | "display_order" | "is_active"
>

export type WebsiteSponsorUpdate = Partial<
  Pick<
    WebsiteSponsor,
    "name" | "logo_url" | "logo_hover_url" | "tier" | "website_url" | "display_order" | "is_active"
  >
>

export const SPONSOR_TIERS: { value: SponsorTier; label: string }[] = [
  { value: "client", label: "Clients" },
  { value: "partner", label: "Partners" },
  { value: "supporter", label: "Backed by Industry Leaders & Innovators" },
]

export const getWebsiteSponsors = () =>
  api.get<WebsiteSponsor[]>("/admin/website/sponsors").then((r) => r.data)

export const createWebsiteSponsor = (payload: WebsiteSponsorCreate) =>
  api.post<WebsiteSponsor>("/admin/website/sponsors", payload).then((r) => r.data)

export const updateWebsiteSponsor = (id: string, payload: WebsiteSponsorUpdate) =>
  api.put<WebsiteSponsor>(`/admin/website/sponsors/${id}`, payload).then((r) => r.data)

export const deleteWebsiteSponsor = (id: string) =>
  api.delete(`/admin/website/sponsors/${id}`).then((r) => r.data)

import { api } from "./client"

export interface WebsiteConfig {
  id: number
  students_count: string
  workshops_count: string
  partners_count: string
  satellites_flown_count: string
  instructor_invite_code: string | null
  intern_invite_code: string | null
  contact_email: string
  contact_phone: string
  contact_whatsapp: string | null
  office_address: string
  social_linkedin: string | null
  social_x: string | null
  social_instagram: string | null
  social_youtube: string | null
  updated_at: string
}

export type WebsiteConfigUpdate = Partial<
  Pick<
    WebsiteConfig,
    | "students_count"
    | "workshops_count"
    | "partners_count"
    | "satellites_flown_count"
    | "instructor_invite_code"
    | "intern_invite_code"
    | "contact_email"
    | "contact_phone"
    | "contact_whatsapp"
    | "office_address"
    | "social_linkedin"
    | "social_x"
    | "social_instagram"
    | "social_youtube"
  >
>

export const getWebsiteConfig = () =>
  api.get<WebsiteConfig>("/admin/website/config").then((r) => r.data)

export const updateWebsiteConfig = (payload: WebsiteConfigUpdate) =>
  api.put<WebsiteConfig>("/admin/website/config", payload).then((r) => r.data)

export const uploadWebsiteAsset = (file: File) => {
  const formData = new FormData()
  formData.append("file", file)
  return api
    .post<{ url: string; filename: string }>("/public/website/upload", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    })
    .then((r) => r.data)
}


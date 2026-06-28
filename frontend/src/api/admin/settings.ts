import { api } from "@/api/client"

export const getSettingsApi = () => api.get<Record<string, string>>("/admin/settings").then((r) => r.data)

export const upsertSettingApi = (key: string, value: string) =>
  api.post("/admin/settings", { key, value }).then((r) => r.data)

export const uploadAdminSignatureApi = (file: File) => {
  const form = new FormData()
  form.append("file", file)
  return api.post<{ admin_signature_url: string }>("/admin/settings/admin-signature", form).then((r) => r.data)
}

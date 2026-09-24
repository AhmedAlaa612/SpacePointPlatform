import { api } from "@/api/client"
import type { User } from "@/types/shared"

export const getUsersApi = () =>
  api.get<User[]>("/admin/users").then((r) => r.data)

export const createUserApi = (data: {
  full_name: string
  email: string
  password: string
  roles: string[]
  phone?: string
}) => api.post<User>("/admin/users", data).then((r) => r.data)

export const updateUserApi = (
  id: string,
  data: Partial<{
    full_name: string; email: string; password: string; phone: string; roles: string[];
    nickname: string; avatar: string; status: string;
  }>
) => api.patch<User>(`/admin/users/${id}`, data).then((r) => r.data)

export const deleteUserApi = (id: string) =>
  api.delete(`/admin/users/${id}`).then((r) => r.data)

export interface DossierItem {
  category: string
  label: string
  date: string | null
  url: string | null
  meta: string | null
  id: string | null
}

export const getUserDossierApi = (id: string) =>
  api.get<{ items: DossierItem[] }>(`/admin/users/${id}/documents`).then((r) => r.data)

export interface IdCardView {
  card_id: string | null
  front_b64: string | null
  back_b64: string | null
}

export const getUserIdCardApi = (id: string, role: string) =>
  api.get<IdCardView>(`/admin/users/${id}/id-card`, { params: { role } }).then((r) => r.data)

export const downloadUserDocumentsZipApi = async (
  id: string,
  name?: string,
  includeGenerated = false
) => {
  try {
    const res = await api.get(`/admin/users/${id}/documents/zip`, {
      params: includeGenerated ? { include_generated: true } : undefined,
      responseType: "blob",
    })
    const blob = res.data as Blob
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    const safeName = (name || id).replace(/[^a-z0-9_-]+/gi, "_")
    a.download = `${safeName}_documents.zip`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    return { ok: true }
  } catch (err: any) {
    let msg = "Failed to download documents"
    if (err?.response?.data instanceof Blob) {
      try {
        const text = await err.response.data.text()
        const json = JSON.parse(text)
        if (json.detail) msg = json.detail
      } catch {
        // fallback
      }
    } else if (err?.response?.data?.detail) {
      msg = err.response.data.detail
    }
    throw new Error(msg)
  }
}


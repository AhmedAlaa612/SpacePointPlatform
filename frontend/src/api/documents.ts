import { api } from "@/api/client"
import type { MyDocuments, DocumentItem, DocumentRequest } from "@/types/documents"

export const getMyDocumentsApi = () =>
  api.get<MyDocuments>("/documents/me").then((r) => r.data)

export const generateRecommendationLetterApi = (data: {
  user_id: string
  recommendation_text: string
  signatory_name?: string
  signatory_title?: string
}) =>
  api.post<DocumentItem>("/documents/recommendation-letters", data).then((r) => r.data)

export const listRecommendationLettersApi = (userId: string) =>
  api.get<DocumentItem[]>(`/documents/recommendation-letters?user_id=${userId}`).then((r) => r.data)

export const createDocumentRequestApi = (data: { type: string; requested_role?: string; notes?: string }) =>
  api.post<DocumentRequest>("/documents/requests", data).then((r) => r.data)

export const getMyDocumentRequestsApi = () =>
  api.get<DocumentRequest[]>("/documents/requests/me").then((r) => r.data)

export const listDocumentRequestsApi = (status?: string) => {
  const query = status ? `?status=${status}` : ""
  return api.get<DocumentRequest[]>(`/documents/requests${query}`).then((r) => r.data)
}

export const generateDocumentRequestApi = (
  id: string,
  data: { signatory_name?: string; signatory_title?: string; recommendation_text?: string; date?: string; title?: string },
) =>
  api.post<DocumentRequest>(`/documents/requests/${id}/generate`, data).then((r) => r.data)

export const approveDocumentRequestApi = (id: string) =>
  api.post<DocumentRequest>(`/documents/requests/${id}/approve`).then((r) => r.data)

export const regenerateDocumentRequestApi = (id: string) =>
  api.post<DocumentRequest>(`/documents/requests/${id}/regenerate`).then((r) => r.data)

export const rejectDocumentRequestApi = (id: string, data: { admin_notes?: string }) =>
  api.post<DocumentRequest>(`/documents/requests/${id}/reject`, { status: "rejected", admin_notes: data.admin_notes }).then((r) => r.data)

import type { IdCard } from "@/types/instructors"

export const getIdCardApi = (role: string) =>
  api.get<IdCard | null>(`/documents/id-card?role=${role}`).then((r) => r.data)

export const updateIdCardApi = (role: string, photo?: File, linkedinUrl?: string) => {
  const form = new FormData()
  if (photo) form.append("photo", photo)
  const params = new URLSearchParams()
  params.set("role", role)
  if (linkedinUrl !== undefined) params.set("linkedin_url", linkedinUrl)
  const qs = params.toString() ? `?${params.toString()}` : ""
  return api.post<IdCard>(`/documents/id-card${qs}`, form).then((r) => r.data)
}

export const downloadIdCardPdfApi = (role: string) =>
  api.get(`/documents/id-card/pdf?role=${role}`, { responseType: "blob" }).then((r) => r.data as Blob)

export const getAvailableTemplatesApi = (role: string) =>
  api.get<{ id: string; key: string; name: string; roles: string[] }[]>(`/documents/templates/available?role=${role}`).then((r) => r.data)

export const listBucketsApi = () =>
  api.get<string[]>("/documents/admin/storage/buckets").then((r) => r.data)

export const listBucketFilesApi = (bucket: string, path: string = "") =>
  api.get<{ name: string; size?: number; mimetype?: string; last_modified?: string; signed_url?: string; owner_name?: string; document_type_label?: string }[]>(
    `/documents/admin/storage/files?bucket=${encodeURIComponent(bucket)}&path=${encodeURIComponent(path)}`
  ).then((r) => r.data)

export const deleteBucketFileApi = (bucket: string, path: string) =>
  api.delete(`/documents/admin/storage/files?bucket=${encodeURIComponent(bucket)}&path=${encodeURIComponent(path)}`).then((r) => r.data)

export const listAdminTemplatesApi = () =>
  api.get<{ id: string; key: string; name: string; roles: string[]; body_text?: string; template_file_url?: string; updated_at: string }[]>(
    "/documents/admin/templates"
  ).then((r) => r.data)

export const updateDocumentTemplateApi = (id: string, name?: string, roles?: string[], bodyText?: string, file?: File, type?: string) => {
  const form = new FormData()
  if (name !== undefined) form.append("name", name)
  if (roles !== undefined) form.append("roles", JSON.stringify(roles))
  if (bodyText !== undefined) form.append("body_text", bodyText)
  if (type !== undefined) form.append("type", type)
  if (file) form.append("file", file)
  return api.put<{ id: string; key: string; name: string; roles: string[]; body_text?: string; template_file_url?: string }>(
    `/documents/admin/templates/${id}`, form
  ).then((r) => r.data)
}

export const createDocumentTemplateApi = (data: { key: string; name: string; roles: string[]; body_text?: string; type?: string }) =>
  api.post<{ id: string; key: string; name: string; roles: string[]; body_text?: string }>("/documents/admin/templates", data).then((r) => r.data)

export const deleteDocumentTemplateApi = (id: string) =>
  api.delete(`/documents/admin/templates/${id}`).then((r) => r.data)

export const adminGenerateDocumentApi = (data: {
  user_id: string
  template_key: string
  body_text: string
  signatory_name?: string
  signatory_title?: string
  date?: string
  title?: string
}) =>
  api.post<{ file_url: string }>("/documents/admin/generate", data).then((r) => r.data)

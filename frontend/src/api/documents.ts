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

import type { IdCard, InstructorDocument } from "@/types/instructors"

// Personal document vault — generic per-user, works for any role (endpoint predates the
// multi-role platform and lives under /instructors for historical reasons only).
export const listDocumentsApi = () =>
  api.get<InstructorDocument[]>("/instructors/documents").then((r) => r.data)

export const uploadDocumentApi = (documentType: string, file: File) => {
  const form = new FormData()
  form.append("file", file)
  return api.post<InstructorDocument>(
    `/instructors/documents?document_type=${encodeURIComponent(documentType)}`, form
  ).then((r) => r.data)
}

export const deleteDocumentApi = (docId: string) =>
  api.delete(`/instructors/documents/${docId}`).then((r) => r.data)

// Admin-only: delete a generated letter (Recommendation/Confirmation/Completion/
// template-based) — distinct from deleteDocumentApi above (instructor's own vault).
export const deleteGeneratedDocumentApi = (documentId: string) =>
  api.delete(`/documents/${documentId}`).then((r) => r.data)

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

/** Default test values for the placeholders THIS specific template's own
 *  issuance code actually substitutes — scoped by `key` (the two system
 *  certificates are rendered by their own bespoke code with a small fixed
 *  token set each; everything else falls back to the generic admin-generate
 *  set). Editable in the UI — these are just starting values. */
export const listPlaceholderTestValuesApi = ({ key, type }: { key?: string; type: "letter" | "certificate" }) =>
  api.get<Record<string, string>>("/documents/admin/templates/placeholders", { params: { key, type } })
    .then((r) => r.data)

/** Renders `bodyText` with placeholders filled and hands back the PDF —
 *  nothing is persisted, safe to call before a template is even saved.
 *  `values` is whatever the admin edited the test values to; an override
 *  always wins over this template's own scoped default. Returns an object
 *  URL the caller must revoke. */
export const previewDocumentTemplateApi = async ({ bodyText, type, key, title, templateId, values, file }: {
  bodyText: string
  type: "letter" | "certificate"
  key?: string
  /** Letters only — mirrors real generation's `body.title or template.name`.
   *  Send whatever the Template Name field currently holds. */
  title?: string
  templateId?: string
  values?: Record<string, string>
  file?: File | null
}) => {
  const form = new FormData()
  form.append("body_text", bodyText)
  form.append("type", type)
  if (key) form.append("key", key)
  if (title) form.append("title", title)
  if (templateId) form.append("template_id", templateId)
  if (values) form.append("values", JSON.stringify(values))
  if (file) form.append("file", file)
  const res = await api.post("/documents/admin/templates/preview", form, { responseType: "blob" })
  return URL.createObjectURL(res.data as Blob)
}

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

import { api } from "@/api/client"
import type { PaymentLetter, PaymentSessionRole } from "@/types/instructors"

export interface PaymentBatch {
  id: string
  name: string
  description: string | null
  letter_count: number
}

export interface Certificate {
  id: string
  user_id: string
  instructor_name: string | null
  instructor_email: string | null
  type: string
  workshop_name: string | null
  workshop_date: string | null
  location: string | null
  file_url: string
}

export interface BulkImportPreview {
  instructor_count: number
  session_count: number
  addon_count: number
  unmatched_emails: string[]
  errors: string[]
}

export const listBatchesApi = () => api.get<PaymentBatch[]>("/instructors/admin/payments/batches").then((r) => r.data)
export const createBatchApi = (data: { name: string; description?: string }) =>
  api.post<PaymentBatch>("/instructors/admin/payments/batches", data).then((r) => r.data)
export const deleteBatchApi = (id: string) => api.delete(`/instructors/admin/payments/batches/${id}`).then((r) => r.data)

export const listAdminLettersApi = (params?: { batch_id?: string; status?: string }) =>
  api.get<PaymentLetter[]>("/instructors/admin/payments/letters", { params }).then((r) => r.data)

export const createLetterApi = (data: { instructor_user_id: string; batch_id?: string; reference?: string }) =>
  api.post<PaymentLetter>("/instructors/admin/payments/letters", data).then((r) => r.data)

export const deleteLetterApi = (id: string) => api.delete(`/instructors/admin/payments/letters/${id}`).then((r) => r.data)

export const addSessionApi = (letterId: string, data: {
  workshop_description: string; role: PaymentSessionRole; session_date?: string
  location?: string; duration_hours?: number; compensation_aed: number
}) => api.post<PaymentLetter>(`/instructors/admin/payments/letters/${letterId}/sessions`, data).then((r) => r.data)

export const deleteSessionApi = (sessionId: string) => api.delete(`/instructors/admin/payments/sessions/${sessionId}`).then((r) => r.data)

export const addAddonApi = (letterId: string, data: { description: string; amount_aed: number; notes?: string }) =>
  api.post<PaymentLetter>(`/instructors/admin/payments/letters/${letterId}/addons`, data).then((r) => r.data)

export const deleteAddonApi = (addonId: string) => api.delete(`/instructors/admin/payments/addons/${addonId}`).then((r) => r.data)

export const generateLetterPdfApi = (letterId: string) =>
  api.post<PaymentLetter>(`/instructors/admin/payments/letters/${letterId}/generate-pdf`).then((r) => r.data)

export const publishLetterApi = (letterId: string) =>
  api.post<PaymentLetter>(`/instructors/admin/payments/letters/${letterId}/publish`).then((r) => r.data)

export const markPaidApi = (letterId: string) =>
  api.post<PaymentLetter>(`/instructors/admin/payments/letters/${letterId}/mark-paid`).then((r) => r.data)

export const bulkImportPreviewApi = (file: File) => {
  const form = new FormData()
  form.append("file", file)
  return api.post<BulkImportPreview>("/instructors/admin/payments/bulk-import/preview", form).then((r) => r.data)
}

export const bulkImportConfirmApi = (file: File, batchId?: string) => {
  const form = new FormData()
  form.append("file", file)
  const qs = batchId ? `?batch_id=${batchId}` : ""
  return api.post<{ created_letters: number; errors: string[] }>(`/instructors/admin/payments/bulk-import/confirm${qs}`, form).then((r) => r.data)
}

export const downloadBulkImportTemplateApi = async () => {
  const res = await api.get("/instructors/admin/payments/bulk-import/template", { responseType: "blob" })
  const url = URL.createObjectURL(res.data as Blob)
  const a = document.createElement("a")
  a.href = url
  a.download = "bulk_import_template.xlsx"
  a.click()
  URL.revokeObjectURL(url)
}

export const paymentsInstructorDropdownApi = () =>
  api.get<{ id: string; full_name: string; email: string }[]>("/instructors/admin/payments/instructors").then((r) => r.data)

export const listCertificatesApi = () => api.get<Certificate[]>("/instructors/admin/payments/certificates").then((r) => r.data)

export const createCertificateApi = (data: {
  instructor_user_id: string; workshop_name: string; workshop_date: string; location: string; send_email?: boolean
}) => api.post<Certificate>("/instructors/admin/payments/certificates", data).then((r) => r.data)

export const deleteCertificateApi = (id: string) =>
  api.delete(`/instructors/admin/payments/certificates/${id}`).then((r) => r.data)

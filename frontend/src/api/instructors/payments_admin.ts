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

/** Partial (I5-1): omitted fields are left alone, so the table can save one
 *  cell. Refused with 409 once the letter is signed. */
export const updateSessionApi = (sessionId: string, data: {
  workshop_description?: string; role?: PaymentSessionRole; session_date?: string | null
  location?: string | null; duration_hours?: number | null; compensation_aed?: number
  /** Cohort rows (2026-08-24): the number of ops-approved days and the
   *  per-session rate behind the total. Together they print as "n x rate" in
   *  the document's units column. */
  session_count?: number | null; rate_aed?: number | null
  sort_order?: number
}) => api.patch<PaymentLetter>(`/instructors/admin/payments/sessions/${sessionId}`, data).then((r) => r.data)

export const deleteSessionApi = (sessionId: string) => api.delete(`/instructors/admin/payments/sessions/${sessionId}`).then((r) => r.data)

export const addAddonApi = (letterId: string, data: { description: string; amount_aed: number; notes?: string }) =>
  api.post<PaymentLetter>(`/instructors/admin/payments/letters/${letterId}/addons`, data).then((r) => r.data)

export const updateAddonApi = (addonId: string, data: {
  description?: string; amount_aed?: number; notes?: string | null; sort_order?: number
}) => api.patch<PaymentLetter>(`/instructors/admin/payments/addons/${addonId}`, data).then((r) => r.data)

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

export interface PendingPaymentInstructor {
  instructor_user_id: string
  full_name: string
  email: string
  /** How many letter rows this would produce — normally one per cohort
   *  (2026-08-24). */
  pending_cohort_count: number
  /** The days behind those rows. */
  pending_session_count: number
  earliest_date: string
  latest_date: string
}

/** Instructors with completed sessions not yet on any payment letter — the
 *  to-do list, so admin doesn't have to already know who to check. */
export const paymentsTodoApi = () =>
  api.get<PendingPaymentInstructor[]>("/instructors/admin/payments/todo").then((r) => r.data)

/** Exactly what "Create letter" on this to-do card would pull in, before
 *  committing to it — same lines `UnbilledSession` describes below. */
export const previewPendingPaymentApi = (instructorUserId: string) =>
  api.get<UnbilledSession[]>(`/instructors/admin/payments/todo/${instructorUserId}/preview`).then((r) => r.data)

export const listCertificatesApi = () => api.get<Certificate[]>("/instructors/admin/payments/certificates").then((r) => r.data)

export const createCertificateApi = (data: {
  instructor_user_id: string; workshop_name: string; workshop_date: string; location: string; send_email?: boolean
}) => api.post<Certificate>("/instructors/admin/payments/certificates", data).then((r) => r.data)

export const deleteCertificateApi = (id: string) =>
  api.delete(`/instructors/admin/payments/certificates/${id}`).then((r) => r.data)

export const emailCertificateApi = (id: string) =>
  api.post<{ status: string; to: string }>(`/instructors/admin/payments/certificates/${id}/email`).then((r) => r.data)

/* ── I5-7 / I5-8 ───────────────────────────────────────────────────────── */

/** One draft payment line for delivered work not yet paid for.
 *
 *  Since 2026-08-24 a line is normally a whole *cohort*: `cohort_id` set,
 *  `session_id` null, and `session_date` holding the cohort's date range
 *  rather than one date. Work delivered outside any cohort assignment still
 *  produces the original one-row-per-session shape.
 *
 *  Send `line_id` back to bill it — the cohort id for a cohort line, the
 *  session id for a single one. */
export interface UnbilledSession {
  cohort_id: string | null
  session_id: string | null
  line_id: string
  /** Every session this line pays for. */
  session_ids: string[]
  session_date: string
  workshop_description: string
  role: string
  location: string | null
  duration_hours: number | null
  cohort_name: string | null
  session_count: number
  rate_aed: number | null
  /** Pre-computed from the agreed rate x ops-approved days. Still a draft —
   *  ops edits it on the letter before publishing. */
  compensation_aed: number
  rate_basis: string
}

/** The certificate checkbox, plus admin notes. Allowed on a signed letter —
 *  neither changes what the instructor put their name to. */
export const updateLetterApi = ({ id, ...body }: {
  id: string
  issue_certificates?: boolean
  admin_notes?: string | null
  batch_id?: string | null
}) => api.patch<PaymentLetter>(`/instructors/admin/payments/letters/${id}`, body).then((r) => r.data)

export const getBillableSessionsApi = (letterId: string) =>
  api.get<UnbilledSession[]>(`/instructors/admin/payments/letters/${letterId}/billable`)
    .then((r) => r.data)

/** Turns chosen billable lines into letter rows, prefilled from real data.
 *
 *  `lineIds` are `UnbilledSession.line_id` values. The amount now arrives
 *  computed from the rate agreed at staffing time rather than at 0 — ops still
 *  sees every figure and can edit any cell until the letter is published, so
 *  the money is still their decision; they just no longer retype a number the
 *  system already knows. */
export const billSessionsApi = ({ letterId, lineIds }: {
  letterId: string
  lineIds: string[]
}) => api.post<PaymentLetter>(`/instructors/admin/payments/letters/${letterId}/bill-sessions`,
  { line_ids: lineIds }).then((r) => r.data)

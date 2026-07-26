import { api } from "@/api/client"
import type { ImportBatch, ImportBatchListItem } from "@/types/sessions"

export const downloadImportTemplateApi = () =>
  api.get("/sessions/imports/template", { responseType: "blob" }).then((r) => r.data as Blob)

export const listImportBatchesApi = (cohortId: string) =>
  api.get<ImportBatchListItem[]>("/sessions/imports", { params: { cohort_id: cohortId } }).then((r) => r.data)

export const dryRunImportApi = (data: {
  cohortId: string
  file: File
  source: "b2b_sheet" | "backfill"
  paymentStatus?: string
  setContactOrganization?: boolean
  sendEmails?: boolean
}) => {
  const form = new FormData()
  form.append("cohort_id", data.cohortId)
  form.append("source", data.source)
  if (data.paymentStatus) form.append("payment_status", data.paymentStatus)
  form.append("set_contact_organization", String(!!data.setContactOrganization))
  form.append("send_emails", String(!!data.sendEmails))
  form.append("file", data.file)
  // No explicit Content-Type here — axios sets multipart/form-data with the
  // correct boundary automatically when the body is a FormData instance;
  // hardcoding the header strips that boundary and breaks parsing.
  return api.post<ImportBatch>("/sessions/imports/dry-run", form).then((r) => r.data)
}

export const commitImportBatchApi = (batchId: string) =>
  api.post<ImportBatch>(`/sessions/imports/${batchId}/commit`).then((r) => r.data)

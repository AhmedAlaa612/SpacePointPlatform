import { api } from "@/api/client"
import type { BankDetails } from "@/types/instructors"

export interface DistributionEntry {
  name: string
  count: number
}

export interface SignupTrendEntry {
  month: string
  count: number
}

export interface AdminOverview {
  pending_applications: number
  pending_payment_signatures: number
  total_instructors: number
  total_applicants: number
  total_facilitators: number
  active_users_30d: number
  university_distribution: DistributionEntry[]
  city_distribution: DistributionEntry[]
  signup_trend: SignupTrendEntry[]
}

export interface ApplicantListItem {
  id: string
  full_name: string
  email: string
  status: string
  feedback: string | null
  university: string | null
  city_of_residence: string | null
  referred_by_ambassador_id: string | null
  created_at: string
  submitted_at: string | null
  also_grant_role: string | null
}

export interface InvitationCode {
  id: string
  code: string
  is_active: boolean
  expires_at: string | null
  max_uses: number
  used_count: number
  created_at: string
}

export interface InstructorDocumentsComplianceSummary {
  is_complete: boolean
  is_uae_resident: boolean
  uploaded_count: number
  total_required: number
  missing_docs: string[]
}

export interface InstructorChecklistItem {
  key: string
  label: string
  desc: string
  mandatory: boolean
  uploaded: boolean
  exempt: boolean
  exemption_reason: string | null
  document_id: string | null
  document_type: string | null
  file_url: string | null
  uploaded_at: string | null
}

export interface InstructorOtherDocument {
  id: string
  document_type: string
  file_name?: string | null
  file_url: string | null
  uploaded_at: string | null
}

export interface InstructorDocumentsComplianceDetail extends InstructorDocumentsComplianceSummary {
  checklist: InstructorChecklistItem[]
  other_documents: InstructorOtherDocument[]
}

export interface InstructorListItem {
  id: string
  full_name: string
  email: string
  status: string
  linkedin_url: string | null
  created_at: string
  // Residence city from users.city_id. `city_id` is null (and `city_name`
  // carries the free-text "Other" value) for countries with no SpacePoint
  // city — such rows can be shown but not filtered by id.
  city_id: string | null
  city_name: string | null
  // Open-to-work cities from ApplicantProfile.deliver_city_ids. Empty for
  // instructors with no applicant profile. ids and names are index-aligned
  // here — the backend drops deleted cities from BOTH.
  deliver_city_ids: string[]
  deliver_city_names: string[]
  // Whether all four bank fields are filled in — not the values themselves,
  // those are fetched on demand via getAdminInstructorBankDetailsApi.
  bank_details_complete: boolean
  // Documents compliance summary
  docs_compliance?: InstructorDocumentsComplianceSummary
}

export const getAdminOverviewApi = () => api.get<AdminOverview>("/instructors/admin/overview").then((r) => r.data)

export const listApplicantsApi = () => api.get<ApplicantListItem[]>("/instructors/admin/applicants").then((r) => r.data)

export interface AssessmentSubmissionDetail {
  file_url: string | null
  google_drive_link: string | null
  comments: string | null
  submitted_at: string | null
}

export const getApplicantDetailApi = (userId: string) =>
  api.get(`/instructors/admin/applicants/${userId}`).then((r) => r.data as {
    id: string
    full_name: string
    email: string
    phone: string | null
    invite_code_used: string | null
    cv_url: string | null
    profile: Record<string, unknown> | null
    review: { status: string; feedback: string | null } | null
    videos: unknown[]
    presentation_link: string | null
    assessment: AssessmentSubmissionDetail | null
    modules: unknown[]
  })

export const reviewApplicantApi = (userId: string, status: string, feedback?: string) =>
  api.put(`/instructors/admin/applicants/${userId}/review`, { status, feedback }).then((r) => r.data)

export const reviewModuleSubmissionApi = (userId: string, moduleId: string, status: string, feedback?: string) =>
  api.put(`/instructors/admin/applicants/${userId}/modules/${moduleId}/review`, { status, feedback }).then((r) => r.data)

export const deleteApplicantApi = (userId: string) =>
  api.delete(`/instructors/admin/applicants/${userId}`).then((r) => r.data)

export const exportApplicantDossierApi = async (userId: string, name: string) => {
  const res = await api.get(`/instructors/admin/applicants/${userId}/dossier`, { responseType: "blob" })
  const url = URL.createObjectURL(res.data as Blob)
  const a = document.createElement("a")
  a.href = url
  a.download = `dossier_${name.replace(/[^a-z0-9]+/gi, "_")}.pdf`
  a.click()
  URL.revokeObjectURL(url)
}

export const listInvitationsApi = () => api.get<InvitationCode[]>("/instructors/admin/invitations").then((r) => r.data)

export const createInvitationApi = (data: { code: string; max_uses?: number; is_active?: boolean }) =>
  api.post<InvitationCode>("/instructors/admin/invitations", data).then((r) => r.data)

export const updateInvitationApi = (id: string, data: { is_active?: boolean; max_uses?: number }) =>
  api.put<InvitationCode>(`/instructors/admin/invitations/${id}`, data).then((r) => r.data)

export const deleteInvitationApi = (id: string) => api.delete(`/instructors/admin/invitations/${id}`).then((r) => r.data)

export const listAdminFacilitatorsApi = () =>
  api.get<{ id: string; full_name: string; email: string; created_at: string }[]>("/instructors/admin/facilitators").then((r) => r.data)

export const createFacilitatorApi = (data: { full_name: string; email: string; password: string }) =>
  api.post("/instructors/admin/facilitators", data).then((r) => r.data)

export const listAdminInstructorsApi = () =>
  api.get<InstructorListItem[]>("/instructors/admin/instructors").then((r) => r.data)

export const getAdminInstructorDetailApi = (userId: string) =>
  api.get(`/instructors/admin/instructors/${userId}`).then((r) => r.data)

export const getAdminInstructorBankDetailsApi = (userId: string) =>
  api.get<BankDetails>(`/instructors/admin/instructors/${userId}/bank-details`).then((r) => r.data)

export const getAdminInstructorDocumentsComplianceApi = (userId: string) =>
  api.get<InstructorDocumentsComplianceDetail>(`/instructors/admin/instructors/${userId}/documents-compliance`).then((r) => r.data)

export const getSettingsApi = () => api.get<Record<string, string>>("/instructors/admin/settings").then((r) => r.data)

export const upsertSettingApi = (key: string, value: string) =>
  api.post("/instructors/admin/settings", { key, value }).then((r) => r.data)

export const uploadAdminSignatureApi = (file: File) => {
  const form = new FormData()
  form.append("file", file)
  return api.post<{ admin_signature_url: string }>("/instructors/admin/settings/admin-signature", form).then((r) => r.data)
}

export { downloadUserDocumentsZipApi as downloadInstructorDocumentsZipApi } from "@/api/admin/users"

export const downloadBatchInstructorDocumentsZipApi = async (
  userIds: string[],
  includeGenerated = false,
  documentTypes?: string[]
) => {
  try {
    const res = await api.post(
      "/instructors/admin/instructors/documents/batch-zip",
      {
        user_ids: userIds,
        include_generated: includeGenerated,
        document_types: documentTypes && documentTypes.length > 0 ? documentTypes : undefined,
      },
      { responseType: "blob" }
    )
    const blob = res.data as Blob
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `instructors_documents_${new Date().toISOString().slice(0, 10)}.zip`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    return { ok: true }
  } catch (err: any) {
    let msg = "Failed to download batch documents"
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


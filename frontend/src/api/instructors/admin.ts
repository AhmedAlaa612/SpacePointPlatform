import { api } from "@/api/client"

export interface AdminOverview {
  pending_applications: number
  pending_payment_signatures: number
  total_instructors: number
  total_applicants: number
}

export interface ApplicantListItem {
  id: string
  full_name: string
  email: string
  status: string
  feedback: string | null
  university: string | null
  referred_by_ambassador_id: string | null
  created_at: string
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

export interface InstructorListItem {
  id: string
  full_name: string
  email: string
  status: string
  linkedin_url: string | null
  created_at: string
}

export const getAdminOverviewApi = () => api.get<AdminOverview>("/instructors/admin/overview").then((r) => r.data)

export const listApplicantsApi = () => api.get<ApplicantListItem[]>("/instructors/admin/applicants").then((r) => r.data)

export const getApplicantDetailApi = (userId: string) =>
  api.get(`/instructors/admin/applicants/${userId}`).then((r) => r.data)

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

export const getSettingsApi = () => api.get<Record<string, string>>("/instructors/admin/settings").then((r) => r.data)

export const upsertSettingApi = (key: string, value: string) =>
  api.post("/instructors/admin/settings", { key, value }).then((r) => r.data)

export const uploadAdminSignatureApi = (file: File) => {
  const form = new FormData()
  form.append("file", file)
  return api.post<{ admin_signature_url: string }>("/instructors/admin/settings/admin-signature", form).then((r) => r.data)
}

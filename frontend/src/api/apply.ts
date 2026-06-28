import { api } from "./client"

export interface ApplyQuestion {
  id: string
  question_text: string
  question_type: "text" | "number" | "radio" | "multiple_choice"
  required: boolean
  order: number
  options: string[]
}

export interface ApplicationOut {
  id: string
  role: string
  status: "pending" | "approved" | "rejected"
  full_name: string
  email: string
  phone: string | null
  country: string | null
  invite_code: string | null
  has_cv: boolean
  answers: Record<string, unknown>
  admin_notes: string | null
  created_at: string | null
  reviewed_at: string | null
  cv_signed_url?: string
}

export const getApplyQuestionsApi = (role: string) =>
  api.get<ApplyQuestion[]>(`/apply/${role}/questions`).then((r) => r.data)

export const submitApplicationApi = (role: string, form: FormData) =>
  api.post<{ id: string; status: string }>(`/apply/${role}`, form).then((r) => r.data)

// Admin
export const listApplicationsApi = (params?: { role?: string; status?: string }) =>
  api.get<ApplicationOut[]>("/admin/applications", { params }).then((r) => r.data)

export const getApplicationApi = (id: string) =>
  api.get<ApplicationOut>(`/admin/applications/${id}`).then((r) => r.data)

export const approveApplicationApi = (id: string, admin_notes?: string) =>
  api.post(`/admin/applications/${id}/approve`, { admin_notes }).then((r) => r.data)

export const rejectApplicationApi = (id: string, admin_notes?: string) =>
  api.post(`/admin/applications/${id}/reject`, { admin_notes }).then((r) => r.data)

export const getApplicationCountsApi = () =>
  api.get<Record<string, Record<string, number>>>("/admin/applications/counts").then((r) => r.data)

// Questions
export const listQuestionsAdminApi = (audience: string) =>
  api.get<ApplyQuestion[]>("/admin/applications/questions/list", { params: { audience } }).then((r) => r.data)

export const createQuestionApi = (data: {
  audience: string; question_text: string; question_type: string; required: boolean; options: string[]
}) => api.post<ApplyQuestion>("/admin/applications/questions", data).then((r) => r.data)

export const updateQuestionApi = (id: string, data: Partial<ApplyQuestion>) =>
  api.patch<ApplyQuestion>(`/admin/applications/questions/${id}`, data).then((r) => r.data)

export const deleteQuestionApi = (id: string) =>
  api.delete(`/admin/applications/questions/${id}`).then((r) => r.data)

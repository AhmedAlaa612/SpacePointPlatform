import { api } from "./client"
import type { InternProfile } from "@/types/internship"
import type { InternshipApproveBody } from "./internship"

export type ApplyQuestionType =
  | "text"
  | "textarea"
  | "number"
  | "date"
  | "url"
  | "radio"
  | "multiple_choice"

export interface ApplyQuestion {
  id: string
  question_text: string
  question_type: ApplyQuestionType
  required: boolean
  enabled?: boolean
  order: number
  options: string[]
}

export interface FormFieldConfig {
  key: string
  label: string
  enabled: boolean
  required: boolean
  locked: boolean
  section?: string
}

export interface RoleFormConfig {
  role: string
  has_custom_override: boolean
  fields: FormFieldConfig[]
  questions: ApplyQuestion[]
}

export interface ResolvedAnswer {
  key: string
  label: string
  question_type: string
  value: unknown
  is_deleted?: boolean
  is_legacy?: boolean
}

export interface PlatformFootprint {
  existing_user?: {
    id: string
    full_name: string
    email: string
    roles: string[]
    status: string
    phone: string | null
    country: string | null
    city: string | null
    birthdate: string | null
    card_id: string | null
    student_id: string | null
    created_at: string | null
    last_login_at: string | null
  } | null
  spine_contact?: {
    id: string
    full_name: string
    contact_roles: string[]
    lifecycle_stage: string
    primary_phone: string | null
    whatsapp: string | null
    country: string | null
    city: string | null
    nationality: string | null
    student_id: string | null
    organization_name: string | null
    notes: string | null
    created_at: string | null
  } | null
  other_applications: Array<{
    id: string
    role: string
    status: string
    full_name: string
    country: string | null
    created_at: string | null
    reviewed_at: string | null
    admin_notes: string | null
  }>
  role_requests: Array<{
    id: string
    target_role: string
    status: string
    created_at: string | null
    reviewed_at: string | null
    admin_notes: string | null
  }>
  instructor_onboarding?: {
    user_id: string
    status: string | null
    feedback: string | null
    submitted_at: string | null
    reviewed_at: string | null
    also_grant_role: string | null
    nationality: string | null
    work_status: string | null
  } | null
  intern_profile?: (InternProfile & {
    work_city?: string | null
    letter_date?: string | null
    has_letter?: boolean
    has_signed_letter?: boolean
  }) | null
}

export interface ApplicationOut {
  id: string
  role: string
  status: "pending" | "approved" | "rejected" | "onboarding"
  full_name: string
  email: string
  phone: string | null
  country: string | null
  city: string | null
  city_id?: string | null
  city_other?: string | null
  birthdate?: string | null
  invite_code: string | null
  invited_by?: { id: string; full_name: string; email: string } | null
  has_cv: boolean
  answers: Record<string, unknown>
  resolved_answers?: ResolvedAnswer[]
  intern_details?: {
    university: string | null
    major: string | null
    university_id_number: string | null
    preferred_city_id: string | null
    preferred_city_name: string | null
    requested_start_date: string | null
    requested_duration_weeks: number | null
  } | null
  organization_details?: {
    organization_id: string | null
    organization_name: string | null
    organization_name_arabic: string | null
    organization_type: string | null
    city: string | null
    website: string | null
    is_approved: boolean | null
  } | null
  admin_notes: string | null
  reviewed_by_name?: string | null
  created_at: string | null
  reviewed_at: string | null
  cv_signed_url?: string
  platform_footprint?: PlatformFootprint | null
}

export const getApplyQuestionsApi = (role: string) =>
  api.get<ApplyQuestion[]>(`/apply/${role}/questions`).then((r) => r.data)

export const getPublicFormConfigApi = (role: string) =>
  api.get<RoleFormConfig>(`/apply/${role}/form-config`).then((r) => r.data)

export const submitApplicationApi = (role: string, form: FormData) =>
  api.post<{ id: string; status: string }>(`/apply/${role}`, form).then((r) => r.data)

// Admin
export const listApplicationsApi = (params?: { role?: string; status?: string }) =>
  api.get<ApplicationOut[]>("/admin/applications", { params }).then((r) => r.data)

export const getApplicationApi = (id: string) =>
  api.get<ApplicationOut>(`/admin/applications/${id}`).then((r) => r.data)

// `internship` is required by the backend when the application's role is
// "intern" — see AdminApplications.tsx's InternshipLetterFields and
// HANDOFF_INTERNSHIP.md.
export const approveApplicationApi = (id: string, admin_notes?: string, internship?: InternshipApproveBody) =>
  api.post(`/admin/applications/${id}/approve`, { admin_notes, internship }).then((r) => r.data)

export const rejectApplicationApi = (id: string, admin_notes?: string) =>
  api.post(`/admin/applications/${id}/reject`, { admin_notes }).then((r) => r.data)

export const sendToOnboardingApi = (id: string, admin_notes?: string, internship?: InternshipApproveBody) =>
  api.post(`/admin/applications/${id}/onboard`, { admin_notes, internship }).then((r) => r.data)

export const getApplicationCountsApi = () =>
  api.get<Record<string, Record<string, number>>>("/admin/applications/counts").then((r) => r.data)

// Form Config & Questions
export const getAdminFormConfigApi = (audience: string) =>
  api.get<RoleFormConfig>(`/admin/applications/form-config/${audience}`).then((r) => r.data)

export const updateAdminFormConfigApi = (
  audience: string,
  fields: Array<{ key: string; enabled: boolean; required: boolean }>,
) => api.put<RoleFormConfig>(`/admin/applications/form-config/${audience}`, { fields }).then((r) => r.data)

export const listQuestionsAdminApi = (audience: string) =>
  api.get<ApplyQuestion[]>("/admin/applications/questions/list", { params: { audience } }).then((r) => r.data)

export const createQuestionApi = (data: {
  audience: string; question_text: string; question_type: string; required: boolean; options: string[]
}) => api.post<ApplyQuestion>("/admin/applications/questions", data).then((r) => r.data)

export const updateQuestionApi = (id: string, data: Partial<ApplyQuestion>) =>
  api.patch<ApplyQuestion>(`/admin/applications/questions/${id}`, data).then((r) => r.data)

export const reorderQuestionsApi = (audience: string, ordered_ids: string[]) =>
  api.post<ApplyQuestion[]>("/admin/applications/questions/reorder", { audience, ordered_ids }).then((r) => r.data)

export const deleteQuestionApi = (id: string) =>
  api.delete(`/admin/applications/questions/${id}`).then((r) => r.data)

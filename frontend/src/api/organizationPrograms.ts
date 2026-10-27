import { api } from "./client"

export interface OrgCohortSummary {
  id: string
  name: string
  code: string
  start_date: string
  end_date: string
  location: string | null
  capacity: number
  active_students_count: number
  active_observers_count: number
  is_public: boolean
  program_id: string
  program_name: string
  program_type?: string
  checklist_title_override: string | null
  linked_event_id: string | null
  linked_event_slug: string | null
}

export interface OrgProgramSummary {
  id: string
  name: string
  code: string
  program_type: string
  description: string | null
  default_capacity?: number | null
  pricing_model?: string
  price?: number | null
  completion_rule_type?: string
  completion_rule_value?: number
  keep_course_access_after_completion?: boolean
  lms_program_id?: string | null
  cohorts_count: number
  cohorts: OrgCohortSummary[]
  created_at?: string
}

export interface OrgQuotas {
  programs_count: number
  max_programs: number | null
  cohorts_count: number
  max_cohorts: number | null
  events_count: number
  max_events: number | null
  max_students_per_cohort: number | null
  max_observers_per_cohort: number | null
}

export interface OrgProgramsOverview {
  organization: {
    id: string
    name_latin: string
    name_arabic: string | null
    org_type: string
    country: string | null
    city: string | null
    is_approved: boolean
    can_publish_events: boolean
    can_author_courses: boolean
    can_publish_courses: boolean
    course_scope_all: boolean
    allowed_course_ids: string[]
    max_events: number | null
    max_programs: number | null
    max_cohorts: number | null
    max_students_per_cohort: number | null
    max_observers_per_cohort: number | null
  }
  programs: OrgProgramSummary[]
  quotas: OrgQuotas
}

export interface OrgCohortDetail extends OrgCohortSummary {
  org_capacity_limit?: number | null
  org_observer_limit?: number | null
  sessions: OrgSessionItem[]
  linked_events: {
    id: string
    slug: string
    title: string
    is_published: boolean
  }[]
  registrations_count: number
}

export interface OrgSessionItem {
  id: string
  title: string
  session_type: string
  date: string
  start_time: string
  end_time: string
  location?: string | null
}

export interface OrgRegistrationItem {
  id: string
  status: string
  created_at: string
  student_name: string
  student_email: string | null
  student_phone: string | null
  city: string | null
  gender: string | null
  date_of_birth: string | null
  grade: string | null
  school_name: string | null
  has_lms_account: boolean
}

export interface CreateOrgProgramInput {
  name: string
  code?: string
  program_type?: string
  description?: string
  default_capacity?: number | null
  pricing_model?: "free" | "paid"
  price?: number | null
  completion_rule_type?: "percentage" | "session_count"
  completion_rule_value?: number
  keep_course_access_after_completion?: boolean
}

export interface CreateOrgCohortInput {
  program_id: string
  name: string
  code: string
  start_date: string
  end_date: string
  location?: string | null
  capacity?: number
  is_public?: boolean
  checklist_title_override?: string | null
}

export interface DuplicateOrgCohortInput {
  name: string
  code: string
  start_date: string
  end_date: string
  capacity?: number
  is_public?: boolean
  duplicate_curriculum?: boolean
}

export interface OrgDeskRegisterInput {
  student_name: string
  email?: string
  phone?: string
  date_of_birth?: string
  city?: string
  grade?: string
  gender?: string
  school_name?: string
  create_lms_account?: boolean
  send_welcome_email?: boolean
}

export interface OrgBulkImportRow {
  student_name: string
  email?: string
  phone?: string
  city?: string
  date_of_birth?: string
  grade?: string
  gender?: string
  school_name?: string
}

// ── API Functions ────────────────────────────────────────────────────────────

export const getOrgProgramsOverviewApi = () =>
  api.get<OrgProgramsOverview>("/organization/programs-overview").then((r) => r.data)

export const createOrgProgramApi = (data: CreateOrgProgramInput) =>
  api.post<OrgProgramSummary>("/organization/programs", data).then((r) => r.data)

export const updateOrgProgramApi = (programId: string, data: Partial<CreateOrgProgramInput>) =>
  api.put<OrgProgramSummary>(`/organization/programs/${programId}`, data).then((r) => r.data)

export const deleteOrgProgramApi = (programId: string) =>
  api.delete(`/organization/programs/${programId}`)

export const getOrgCohortDetailApi = (cohortId: string) =>
  api.get<OrgCohortDetail>(`/organization/cohorts/${cohortId}`).then((r) => r.data)

export const createOrgCohortApi = (data: CreateOrgCohortInput) =>
  api.post<OrgCohortDetail>("/organization/cohorts", data).then((r) => r.data)

export const updateOrgCohortApi = (cohortId: string, data: Partial<CreateOrgCohortInput>) =>
  api.put<OrgCohortDetail>(`/organization/cohorts/${cohortId}`, data).then((r) => r.data)

export const duplicateOrgCohortApi = (cohortId: string, data: DuplicateOrgCohortInput) =>
  api.post<OrgCohortDetail>(`/organization/cohorts/${cohortId}/duplicate`, data).then((r) => r.data)

export const getOrgCohortRegistrationsApi = (cohortId: string) =>
  api.get<OrgRegistrationItem[]>(`/organization/cohorts/${cohortId}/registrations`).then((r) => r.data)

export const registerOrgStudentApi = (cohortId: string, data: OrgDeskRegisterInput) =>
  api.post<{ registration_id: string; contact_id: string; student_name: string }>(
    `/organization/cohorts/${cohortId}/registrations`,
    data
  ).then((r) => r.data)

export const bulkImportOrgStudentsApi = (cohortId: string, students: OrgBulkImportRow[]) =>
  api.post<{
    imported: number
    failed: number
    errors: { row: number; reason: string }[]
  }>(`/organization/cohorts/${cohortId}/registrations/bulk-import`, { students }).then((r) => r.data)

export const cancelOrgRegistrationApi = (cohortId: string, registrationId: string) =>
  api.delete(`/organization/cohorts/${cohortId}/registrations/${registrationId}`)

export const createOrgSessionApi = (cohortId: string, data: Omit<OrgSessionItem, "id">) =>
  api.post<OrgSessionItem>(`/organization/cohorts/${cohortId}/sessions`, data).then((r) => r.data)

export const updateOrgSessionApi = (cohortId: string, sessionId: string, data: Partial<Omit<OrgSessionItem, "id">>) =>
  api.put<OrgSessionItem>(`/organization/cohorts/${cohortId}/sessions/${sessionId}`, data).then((r) => r.data)

export const deleteOrgSessionApi = (cohortId: string, sessionId: string) =>
  api.delete(`/organization/cohorts/${cohortId}/sessions/${sessionId}`)

export interface OrgCohortObserver {
  id: string
  user_id: string
  full_name: string
  email: string
  phone?: string | null
  assigned_at?: string | null
}

export const getOrgCohortObserversApi = (cohortId: string) =>
  api.get<OrgCohortObserver[]>(`/organization/cohorts/${cohortId}/observers`).then((r) => r.data)

export const addOrgCohortObserverApi = (cohortId: string, userId: string) =>
  api.post<OrgCohortObserver>(`/organization/cohorts/${cohortId}/observers`, { user_id: userId }).then((r) => r.data)

export const removeOrgCohortObserverApi = (cohortId: string, userId: string) =>
  api.delete(`/organization/cohorts/${cohortId}/observers/${userId}`)

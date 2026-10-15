import { api } from "@/api/client"
import type { Program, ProgramType, PricingModel, CompletionRuleType } from "@/types/sessions"

export const getProgramsApi = () =>
  api.get<Program[]>("/sessions/programs").then((r) => r.data)

export const getProgramApi = (id: string) =>
  api.get<Program>(`/sessions/programs/${id}`).then((r) => r.data)

export const createProgramApi = (data: {
  code: string
  name: string
  program_type: ProgramType
  pricing_model: PricingModel
  description?: string
  price?: number
  default_capacity?: number
  active?: boolean
  completion_rule_type?: CompletionRuleType
  completion_rule_value?: number
  default_assessment_config_id?: string | null
  keep_course_access_after_completion?: boolean
}) => api.post<Program>("/sessions/programs", data).then((r) => r.data)

export const updateProgramApi = (
  id: string,
  data: Partial<{
    code: string
    name: string
    program_type: ProgramType
    pricing_model: PricingModel
    description: string | null
    price: number | null
    default_capacity: number | null
    active: boolean
    completion_rule_type: CompletionRuleType
    completion_rule_value: number
    default_assessment_config_id: string | null
    keep_course_access_after_completion: boolean
  }>
) => api.patch<Program>(`/sessions/programs/${id}`, data).then((r) => r.data)

/** 409 if the program still has cohorts — the API refuses rather than
 *  cascading them (and their registrations) away silently. */
export const deleteProgramApi = (id: string) =>
  api.delete<void>(`/sessions/programs/${id}`).then((r) => r.data)

export const cloneProgramApi = (sourceId: string, data: {
  name: string
  code: string
  carry: string[]
}) => api.post<Program>(`/sessions/programs/${sourceId}/clone`, data).then(r => r.data)

export interface TemplateDay {
  id: string
  cohort_id: string
  day_number: number
  title?: string | null
  duration_hours?: number | null
  meeting_date?: string | null
}

export interface ProgramTemplate {
  program_id: string
  template_cohort_id: string
  days_count: number
  sessions: TemplateDay[]
}

export const getProgramTemplateApi = (programId: string) =>
  api.get<ProgramTemplate>(`/sessions/programs/${programId}/template`).then((r) => r.data)

export const addProgramTemplateDayApi = (
  programId: string,
  data?: { title?: string; duration_hours?: number },
) =>
  api.post<TemplateDay>(`/sessions/programs/${programId}/template-days`, data ?? {}).then((r) => r.data)

export const updateProgramTemplateDayApi = (
  programId: string,
  sessionId: string,
  data: { title?: string; duration_hours?: number },
) =>
  api.patch<TemplateDay>(`/sessions/programs/${programId}/template-days/${sessionId}`, data).then((r) => r.data)

export const deleteProgramTemplateDayApi = (programId: string, sessionId: string) =>
  api.delete<void>(`/sessions/programs/${programId}/template-days/${sessionId}`).then((r) => r.data)


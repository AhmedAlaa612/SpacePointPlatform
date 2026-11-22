import { api } from "@/api/client"
import type {
  Program,
  ProgramType,
  PricingModel,
  CompletionRuleType,
  ProgramVariation,
  ProgramVariationDay,
} from "@/types/sessions"

export const getProgramsApi = () =>
  api.get<Program[]>("/sessions/programs").then((r) => r.data)

export const getFilteredProgramsApi = (params?: {
  organization_id?: string
  include_org_programs?: boolean
}) =>
  api.get<Program[]>("/sessions/programs", { params }).then((r) => r.data)

export const getProgramApi = (id: string) =>
  api.get<Program>(`/sessions/programs/${id}`).then((r) => r.data)

export const createProgramApi = (data: {
  code: string
  name: string
  program_type: ProgramType
  pricing_model: PricingModel
  description?: string
  price?: number
  duration_hours?: number | null
  default_capacity?: number
  active?: boolean
  completion_rule_type?: CompletionRuleType
  completion_rule_value?: number
  default_assessment_config_id?: string | null
  organization_id?: string | null
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
    duration_hours: number | null
    default_capacity: number | null
    active: boolean
    completion_rule_type: CompletionRuleType
    completion_rule_value: number
    default_assessment_config_id: string | null
    poster_template_url?: string | null
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
  template_cohort_id: string | null
  days_count: number
  sessions: TemplateDay[]
}

export const getProgramTemplateApi = (programId: string, variationId?: string | null) =>
  api.get<ProgramTemplate>(`/sessions/programs/${programId}/template`, {
    params: variationId ? { variation_id: variationId } : undefined,
  }).then((r) => r.data)

export const addProgramTemplateDayApi = (
  programId: string,
  data?: { title?: string; duration_hours?: number },
  variationId?: string | null,
) =>
  api.post<TemplateDay>(`/sessions/programs/${programId}/template-days`, data ?? {}, {
    params: variationId ? { variation_id: variationId } : undefined,
  }).then((r) => r.data)

export const updateProgramTemplateDayApi = (
  programId: string,
  sessionId: string,
  data: { title?: string; duration_hours?: number },
) =>
  api.patch<TemplateDay>(`/sessions/programs/${programId}/template-days/${sessionId}`, data).then((r) => r.data)

export const deleteProgramTemplateDayApi = (programId: string, sessionId: string) =>
  api.delete<void>(`/sessions/programs/${programId}/template-days/${sessionId}`).then((r) => r.data)

/* ── Program Variations ──────────────────────────────────────────────────── */

export type VariationCarryBucket =
  | "days"
  | "roles"
  | "pre_quiz"
  | "lms"
  | "component_config"
  | "hints"
  | "materials"
  | "assessment"
  | "certificate"
  | "rubric"
  | "scalars"

export const listProgramVariationsApi = (programId: string, activeOnly = false) =>
  api.get<ProgramVariation[]>(`/sessions/programs/${programId}/variations`, {
    params: activeOnly ? { active_only: true } : undefined,
  }).then((r) => r.data)

export const createProgramVariationApi = (
  programId: string,
  data: {
    name: string
    description?: string | null
    is_default?: boolean
    is_active?: boolean
    mode?: "blank" | "duplicate" | "from_cohort"
    source_variation_id?: string | null
    source_cohort_id?: string | null
    carry?: VariationCarryBucket[]
    duration_hours?: number | null
    default_capacity?: number | null
    poster_template_url?: string | null
    keep_course_access_after_completion?: boolean | null
    pricing_model?: PricingModel | null
    price?: number | null
    completion_rule_type?: CompletionRuleType | null
    completion_rule_value?: number | null
    default_assessment_config_id?: string | null
  },
) => api.post<ProgramVariation>(`/sessions/programs/${programId}/variations`, data).then((r) => r.data)

export const updateProgramVariationApi = (
  programId: string,
  variationId: string,
  data: Partial<{
    name: string
    description: string | null
    is_default: boolean
    is_active: boolean
    sort_order: number
    duration_hours: number | null
    default_capacity: number | null
    poster_template_url: string | null
    keep_course_access_after_completion: boolean | null
    pricing_model: PricingModel | null
    price: number | null
    completion_rule_type: CompletionRuleType | null
    completion_rule_value: number | null
    default_assessment_config_id: string | null
  }>,
) => api.patch<ProgramVariation>(`/sessions/programs/${programId}/variations/${variationId}`, data).then((r) => r.data)

export const deleteProgramVariationApi = (programId: string, variationId: string) =>
  api.delete<void>(`/sessions/programs/${programId}/variations/${variationId}`).then((r) => r.data)

export const addVariationDayApi = (
  programId: string,
  variationId: string,
  data?: { title?: string; duration_hours?: number | null; starts_at?: string | null; day_number?: number },
) => api.post<ProgramVariationDay>(`/sessions/programs/${programId}/variations/${variationId}/days`, data ?? {}).then((r) => r.data)

export const updateVariationDayApi = (
  programId: string,
  variationId: string,
  dayId: string,
  data: { title?: string | null; duration_hours?: number | null; starts_at?: string | null; day_number?: number },
) => api.patch<ProgramVariationDay>(`/sessions/programs/${programId}/variations/${variationId}/days/${dayId}`, data).then((r) => r.data)

export const deleteVariationDayApi = (programId: string, variationId: string, dayId: string) =>
  api.delete<void>(`/sessions/programs/${programId}/variations/${variationId}/days/${dayId}`).then((r) => r.data)

export const reorderVariationDaysApi = (programId: string, variationId: string, dayIds: string[]) =>
  api.post<ProgramVariationDay[]>(`/sessions/programs/${programId}/variations/${variationId}/days/reorder`, {
    day_ids: dayIds,
  }).then((r) => r.data)


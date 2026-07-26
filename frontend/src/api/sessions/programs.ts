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
  }>
) => api.patch<Program>(`/sessions/programs/${id}`, data).then((r) => r.data)

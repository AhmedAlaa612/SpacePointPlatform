import { api } from "@/api/client"
import type { WebsiteEvent, WebsiteEventInput } from "@/api/websiteEvents"

export interface LiveFieldState<T = any> {
  live: T
  override: T | null
  effective: T
  source: "live" | "override" | "manual"
}

export interface ProgramLandingStep {
  cohort_id: string
  name: string
  starts_on: string | null
  ends_on: string | null
  date_label: string | null
  city: string | null
  venue: string | null
  status: string
  capacity: number | null
  enrolled_count: number
  seats_left: number | null
  sessions_count: number
  hidden?: boolean
}

export interface ProgramLandingCurriculumItem {
  chapter_num: string
  title: string
  icon?: string
}

export interface ProgramLandingPage extends WebsiteEvent {
  program_id?: string | null
  live_linked?: boolean
  overrides?: Record<string, any>
  hidden_cohort_ids?: string[]
  hidden_sections?: string[]
  preview_token?: string | null
  submitted_for_review_at?: string | null
  steps?: ProgramLandingStep[]
  curriculum_chapters?: ProgramLandingCurriculumItem[]
  live_steps?: ProgramLandingStep[]
  field_states?: Record<string, LiveFieldState>
  org_access?: "ops" | "direct" | "review" | "disabled" | null
}

export interface ProgramLandingPageUpdate extends Partial<WebsiteEventInput> {
  live_linked?: boolean
  overrides?: Record<string, any>
  hidden_cohort_ids?: string[]
  hidden_sections?: string[]
}

export interface HybridCaseStudy {
  id: string
  slug: string
  title: string
  subtitle?: string | null
  category: string
  card_summary: string
  cover_image_url: string
  partner_logo_url?: string | null
  partner_name?: string | null
  source_type: string
  program_id?: string | null
  cohort_id?: string | null
  cohort_ids?: string[]
  partners: { name: string; logo_url?: string; role?: string | null }[]
  overview_text?: string | null
  metrics: { value: string; label: string; is_hero?: boolean }[]
  hero_metric_value?: string | null
  hero_metric_label?: string | null
  hero_metric_enabled?: boolean
  card_metrics: { value: string; label: string; is_hero?: boolean }[]
  gallery_images: string[]
  highlights: { title: string; description?: string; icon?: string }[]
  curriculum_chapters: { chapter_num: string; title: string; icon?: string }[]
  structure_title?: string | null
  structure_sections: {
    id?: string | null
    badge?: string | null
    title: string
    subtitle?: string | null
    image_url?: string | null
    images?: string[]
    items?: { title: string; description?: string; milestones?: string[] }[]
    days?: { day_title: string; description?: string; milestones: string[] }[]
  }[]
  visibility_stats: { value: string; label: string; icon?: string }[]
  spotlights: any[]
  testimonials: { quote: string; author_name: string; author_role?: string; author_photo_url?: string; badge?: string }[]
  cta_label?: string | null
  cta_url?: string | null
  display_order: number
  is_featured: boolean
  is_published: boolean
  live_linked?: boolean
  overrides?: Record<string, any>
  hidden_sections?: string[]
  preview_token?: string | null
  field_states?: Record<string, LiveFieldState>
  created_at: string
  updated_at: string
}

// ── Program Landing Pages (Unified on WebsiteEvent) ──────────────────────────

export async function getProgramLandingPageApi(programId: string): Promise<ProgramLandingPage | null> {
  const { data } = await api.get<ProgramLandingPage | null>(`/sessions/programs/${programId}/landing-page`)
  return data
}

export async function createProgramLandingPageApi(programId: string): Promise<ProgramLandingPage> {
  const { data } = await api.post<ProgramLandingPage>(`/sessions/programs/${programId}/landing-page`)
  return data
}

export async function updateProgramLandingPageApi(
  programId: string,
  payload: ProgramLandingPageUpdate,
): Promise<ProgramLandingPage> {
  const { data } = await api.put<ProgramLandingPage>(
    `/sessions/programs/${programId}/landing-page`,
    payload,
  )
  return data
}

export async function resetProgramLandingFieldApi(
  programId: string,
  field: string,
): Promise<ProgramLandingPage> {
  const { data } = await api.post<ProgramLandingPage>(
    `/sessions/programs/${programId}/landing-page/reset-field`,
    { field },
  )
  return data
}

export async function publishProgramLandingPageApi(programId: string): Promise<ProgramLandingPage> {
  const { data } = await api.post<ProgramLandingPage>(
    `/sessions/programs/${programId}/landing-page/publish`,
  )
  return data
}

export async function unpublishProgramLandingPageApi(programId: string): Promise<ProgramLandingPage> {
  const { data } = await api.post<ProgramLandingPage>(
    `/sessions/programs/${programId}/landing-page/unpublish`,
  )
  return data
}

export async function regenerateProgramLandingTokenApi(
  programId: string,
): Promise<ProgramLandingPage> {
  const { data } = await api.post<ProgramLandingPage>(
    `/sessions/programs/${programId}/landing-page/preview-token/regenerate`,
  )
  return data
}

// ── Case Studies (Ops-Only, Multi-Cohort Hybrid-Live) ────────────────────────

export async function listProgramCaseStudiesApi(programId?: string): Promise<HybridCaseStudy[]> {
  const { data } = await api.get<HybridCaseStudy[]>("/admin/website/case-studies", {
    params: programId ? { program_id: programId } : undefined,
  })
  return data
}

export async function getCaseStudyDetailApi(caseStudyId: string): Promise<HybridCaseStudy> {
  const { data } = await api.get<HybridCaseStudy>(`/admin/website/case-studies/${caseStudyId}`)
  return data
}

export async function createCaseStudyFromProgramApi(payload: {
  program_id: string
  cohort_ids: string[]
  title?: string
  include_buckets?: string[]
}): Promise<HybridCaseStudy> {
  const { data } = await api.post<HybridCaseStudy>(
    "/admin/website/case-studies/from-program",
    payload,
  )
  return data
}

export async function updateCaseStudyApi(
  caseStudyId: string,
  payload: Partial<HybridCaseStudy>,
): Promise<HybridCaseStudy> {
  const { data } = await api.put<HybridCaseStudy>(
    `/admin/website/case-studies/${caseStudyId}`,
    payload,
  )
  return data
}

export async function resetCaseStudyFieldApi(
  caseStudyId: string,
  field: string,
): Promise<HybridCaseStudy> {
  const { data } = await api.post<HybridCaseStudy>(
    `/admin/website/case-studies/${caseStudyId}/reset-field`,
    { field },
  )
  return data
}

export async function publishCaseStudyApi(caseStudyId: string): Promise<HybridCaseStudy> {
  const { data } = await api.post<HybridCaseStudy>(
    `/admin/website/case-studies/${caseStudyId}/publish`,
  )
  return data
}

export async function unpublishCaseStudyApi(caseStudyId: string): Promise<HybridCaseStudy> {
  const { data } = await api.post<HybridCaseStudy>(
    `/admin/website/case-studies/${caseStudyId}/unpublish`,
  )
  return data
}

export async function regenerateCaseStudyTokenApi(caseStudyId: string): Promise<HybridCaseStudy> {
  const { data } = await api.post<HybridCaseStudy>(
    `/admin/website/case-studies/${caseStudyId}/preview-token/regenerate`,
  )
  return data
}

export async function deleteCaseStudyApi(caseStudyId: string): Promise<void> {
  await api.delete(`/admin/website/case-studies/${caseStudyId}`)
}

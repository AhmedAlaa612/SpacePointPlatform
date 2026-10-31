import { api } from "./client"

export interface CaseStudyPartnerItem {
  name: string
  logo_url: string
  role?: string | null
}

export interface CaseStudyMetricItem {
  value: string
  label: string
  is_hero?: boolean
}

export interface CaseStudyHighlightItem {
  title: string
  description: string
  icon?: string | null
}

export interface CaseStudyCurriculumChapter {
  chapter_num: string
  title: string
  icon?: string | null
}

export interface CaseStudyStructureSection {
  id?: string | null
  badge?: string | null
  title: string
  subtitle?: string | null
  description?: string | null
  image_url?: string | null
  items?: Array<{ title: string; description?: string | null }>
  days?: Array<{ day_title: string; milestones: string[] }>
}

export interface CaseStudyVisibilityStat {
  value: string
  label: string
  icon?: string | null
}

export interface CaseStudySpotlightItem {
  type: string // "showcase" | "spotlight" | "future_mission"
  title: string
  subtitle?: string | null
  tag?: string | null
  logo_url?: string | null
  images?: string[]
  content?: string | null
}

export interface CaseStudyTestimonialItem {
  quote: string
  author_name: string
  author_role: string
  author_photo_url?: string | null
  badge?: string | null
}

export interface WebsiteCaseStudy {
  id: string
  slug: string
  title: string
  subtitle?: string | null
  category: string
  card_summary: string
  cover_image_url: string
  partner_logo_url?: string | null
  partner_name?: string | null

  source_type: string // "manual" | "cohort" | "multi_cohort" | "program"
  program_id?: string | null
  cohort_id?: string | null
  cohort_ids?: string[]

  partners: CaseStudyPartnerItem[]
  overview_text?: string | null
  metrics: CaseStudyMetricItem[]
  hero_metric_value?: string | null
  hero_metric_label?: string | null
  hero_metric_enabled: boolean
  card_metrics: CaseStudyMetricItem[]

  gallery_images: string[]
  highlights: CaseStudyHighlightItem[]
  curriculum_chapters: CaseStudyCurriculumChapter[]

  structure_title?: string | null
  structure_sections: CaseStudyStructureSection[]

  visibility_stats: CaseStudyVisibilityStat[]
  spotlights: CaseStudySpotlightItem[]

  testimonials: CaseStudyTestimonialItem[]
  cta_label?: string | null
  cta_url?: string | null

  display_order: number
  is_featured: boolean
  is_published: boolean
  created_at: string
  updated_at: string
}

export type WebsiteCaseStudyCreate = Omit<WebsiteCaseStudy, "id" | "slug" | "created_at" | "updated_at"> & {
  slug?: string
}

export type WebsiteCaseStudyUpdate = Partial<WebsiteCaseStudyCreate>

export interface CaseStudySnapshotRequest {
  source_type: "cohort" | "multi_cohort" | "program"
  cohort_id?: string | null
  cohort_ids?: string[]
  program_id?: string | null
}

export interface CaseStudySnapshotOut {
  title?: string | null
  subtitle?: string | null
  category?: string | null
  card_summary?: string | null
  overview_text?: string | null
  partner_name?: string | null
  partner_logo_url?: string | null
  partners: CaseStudyPartnerItem[]
  metrics: CaseStudyMetricItem[]
  card_metrics: CaseStudyMetricItem[]
  curriculum_chapters: CaseStudyCurriculumChapter[]
  structure_sections: CaseStudyStructureSection[]
}

export const getWebsiteCaseStudies = () =>
  api.get<WebsiteCaseStudy[]>("/admin/website/case-studies").then((r) => r.data)

export const createWebsiteCaseStudy = (payload: WebsiteCaseStudyCreate) =>
  api.post<WebsiteCaseStudy>("/admin/website/case-studies", payload).then((r) => r.data)

export const updateWebsiteCaseStudy = (id: string, payload: WebsiteCaseStudyUpdate) =>
  api.put<WebsiteCaseStudy>(`/admin/website/case-studies/${id}`, payload).then((r) => r.data)

export const deleteWebsiteCaseStudy = (id: string) =>
  api.delete(`/admin/website/case-studies/${id}`).then((r) => r.data)

export const pullCaseStudySnapshot = (payload: CaseStudySnapshotRequest) =>
  api.post<CaseStudySnapshotOut>("/admin/website/case-studies/pull-snapshot", payload).then((r) => r.data)

export interface CaseStudiesHeaderStatItem {
  value: string
  label: string
}

export interface CaseStudiesHeaderPartnerItem {
  name: string
  logo_url: string
  website_url?: string | null
}

export interface WebsiteCaseStudiesHeader {
  id: number
  stats: CaseStudiesHeaderStatItem[]
  partners: CaseStudiesHeaderPartnerItem[]
  updated_at?: string | null
}

export interface WebsiteCaseStudiesHeaderUpdate {
  stats?: CaseStudiesHeaderStatItem[] | null
  partners?: CaseStudiesHeaderPartnerItem[] | null
}

export const getCaseStudiesHeader = () =>
  api.get<WebsiteCaseStudiesHeader>("/admin/website/case-studies-header").then((r) => r.data)

export const updateCaseStudiesHeader = (payload: WebsiteCaseStudiesHeaderUpdate) =>
  api.put<WebsiteCaseStudiesHeader>("/admin/website/case-studies-header", payload).then((r) => r.data)


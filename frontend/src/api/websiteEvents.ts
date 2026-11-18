import { api, tokens } from "./client"
import type { User } from "@/types/shared"

export interface EventBenefitItem {
  title: string
  description: string
}

export interface EventGlanceItem {
  highlight: string
  details: string
}

export interface EventEligibilityRow {
  label: string
  requirement: string
}

export interface EventJourneyStage {
  stage: string
  title: string
  description: string
}

export interface EventTimelineRow {
  date: string
  milestone: string
}

export interface EventDeliverablePhase {
  phase: string
  deadline: string
  items: string[]
}

export interface EventFaqItem {
  question: string
  answer: string
}

export interface EventPartnerItem {
  name: string
  role: string
  logo_url: string
}

export interface EventContactItem {
  name: string
  role: string
  organization?: string
  org?: string
  email: string
  phone?: string
}

export interface EventContactMetaItem {
  label: string
  value: string
  url: string
}

export interface MegaEventCoordinatorInfo {
  name?: string
  role?: string
  email?: string
  note?: string
}

export interface MegaEvent {
  id: string
  slug: string
  country: string
  title: string
  title_ar: string | null
  subtitle: string | null
  tagline: string | null
  banner_url: string | null
  top_banner_url?: string | null
  date_label: string | null
  about_text: string | null
  official_note: string | null
  official_url: string | null
  primary_cta_label: string | null
  primary_cta_url: string | null
  at_a_glance: EventGlanceItem[]
  host_steps: EventJourneyStage[]
  coordinator_info: MegaEventCoordinatorInfo
  partners: EventPartnerItem[]
  faqs: EventFaqItem[]
  display_order: number
  is_published: boolean
  default_language?: string
  ar_content?: Record<string, any>
  events_count: number
  created_at: string
  updated_at: string
}

export type MegaEventCreateInput = Partial<Omit<MegaEvent, "id" | "events_count" | "created_at" | "updated_at">> & {
  title: string
}

export interface WebsiteEvent {
  id: string
  slug: string
  mega_event_id: string | null
  mega_event_slug: string | null
  mega_event_title: string | null
  cohort_id?: string | null
  organization_id: string | null
  organization_name: string | null
  created_by_user_id: string | null

  country: string
  city: string | null
  event_type: string
  audience: string | null
  venue_type: string | null

  // 1. Hero
  title: string
  title_ar: string | null
  subtitle: string | null
  tagline: string | null
  banner_url: string | null
  top_banner_url?: string | null
  host_org_name: string | null
  date_label: string | null
  location: string | null
  registration_url: string | null
  guidelines_url: string | null
  wsw_official_url: string | null

  // 2. About & Benefits
  about_text: string | null
  benefits: EventBenefitItem[]

  // 3. At a Glance
  at_a_glance: EventGlanceItem[]

  // 4. Eligibility
  eligibility_intro: string | null
  eligibility_rows: EventEligibilityRow[]
  eligibility_note: string | null

  // 5. Journey
  journey_stages: EventJourneyStage[]

  // 6. Timeline
  timeline: EventTimelineRow[]
  timeline_note: string | null

  // 7. Deliverables
  deliverables: EventDeliverablePhase[]
  deliverables_note: string | null

  // 8. Final Showcase & Awards
  awards_text: string | null

  // 9. Registration
  registration_text: string | null
  registration_deadline: string | null
  whatsapp_url: string | null
  registration_note: string | null

  // 10. FAQs
  faqs: EventFaqItem[]

  // 11. Partners
  partners: EventPartnerItem[]
  partners_note: string | null

  // 12. Contacts
  contacts: EventContactItem[]
  contact_meta: EventContactMetaItem[]

  display_order: number
  is_published: boolean
  default_language?: string
  ar_content?: Record<string, any>
  created_at: string
  updated_at: string
}

export type WebsiteEventInput = Partial<
  Omit<
    WebsiteEvent,
    | "id"
    | "mega_event_slug"
    | "mega_event_title"
    | "organization_name"
    | "created_by_user_id"
    | "created_at"
    | "updated_at"
  >
> & {
  title: string
}

export interface OrganizationAccountSummary {
  id: string
  name_latin: string
  name_arabic: string | null
  org_type: string
  country: string | null
  city: string | null
  created_at?: string | null
  owner_user_id: string | null
  owner_email: string | null
  owner_name: string | null
  owner_phone?: string | null
  owner_status?: string | null
  owner_card_id?: string | null
  logo_url?: string | null
  events_count: number
  published_events_count?: number
  members_count: number
  programs_count?: number
  cohorts_count?: number
  running_cohorts_count?: number
  enrolled_students_count?: number
  highest_cohort_students?: number
  highest_cohort_name?: string | null
  highest_cohort_observers?: number
  highest_observers_cohort_name?: string | null
  authored_courses_count?: number
  pending_review_courses_count?: number
  shared_courses_count?: number
  invite_batches_active_count?: number
  invite_used_count?: number
  invite_max_count?: number
  quiz_templates_authored_count?: number
  quiz_questions_authored_count?: number
  is_approved: boolean
  can_publish_events: boolean
  can_author_courses: boolean
  can_publish_courses: boolean
  course_scope_all: boolean
  allowed_course_ids: string[]
  quiz_scope?: string
  allowed_quiz_template_ids?: string[]
  max_events?: number | null
  max_programs?: number | null
  max_cohorts?: number | null
  max_students_per_cohort?: number | null
  max_observers_per_cohort?: number | null
}

export interface OrgProgramChecklistItem {
  id: string
  position: number
  title: string
  item_type: string
  optional: boolean
  scope: string
}

export interface OrgProgramDetail {
  id: string
  name: string
  program_type: string
  active: boolean
  lms_program_id: string | null
  checklist_name: string | null
  certificate_required: boolean
  cohorts_count: number
  checklist_items: OrgProgramChecklistItem[]
}

export interface OrgCohortDetail {
  id: string
  program_id: string
  program_name: string
  name: string
  status: string
  starts_on: string | null
  ends_on: string | null
  enrolled_count: number
  capacity: number | null
  observers_count: number
  sessions_count: number
  completion_pct: number
}

export interface OrgInviteBatch {
  id: string
  code: string
  label: string | null
  kind: string
  granted_target: string | null
  used_count: number
  max_uses: number
  expires_at: string | null
  is_active: boolean
}

export interface OrgStudentDetail {
  registration_id: string
  contact_id: string
  user_id: string | null
  full_name: string
  email: string
  phone: string | null
  cohort_id: string
  cohort_name: string
  status: string
  enrolled_at: string | null
  completion_pct: number
}

export interface OrgAuthoredCourse {
  id: string
  title: string
  track: string | null
  is_published: boolean
  submitted_for_review_at: string | null
  modules_count: number
  enrolled_count: number
  created_at: string | null
}

export interface OrgSharedCourse {
  id: string
  title: string
  track: string | null
  level: string | null
  modules_count: number
  is_published: boolean
}

export interface OrgQuizTemplate {
  id: string
  name: string
  questions_count: number
  is_active: boolean
  linked_cohorts: string[]
  created_at: string | null
}

export interface OrgLandingPage {
  id: string
  title: string
  slug: string
  country: string
  is_published: boolean
  cohort_id: string | null
  cohort_name: string | null
  registrations_count: number
  updated_at: string | null
}

export interface OrgTeamMemberDetail {
  user_id: string
  full_name: string
  email: string
  phone: string | null
  role: string
  org_role: OrgSandboxRole
  card_id: string | null
  status: string
  invite_pending: boolean
  observer_cohorts: string[]
}

export interface OrganizationDetail {
  organization: OrganizationAccountSummary
  programs: OrgProgramDetail[]
  cohorts: OrgCohortDetail[]
  invite_batches: OrgInviteBatch[]
  students: OrgStudentDetail[]
  authored_courses: OrgAuthoredCourse[]
  shared_courses: OrgSharedCourse[]
  quiz_templates: OrgQuizTemplate[]
  landing_pages: OrgLandingPage[]
  team: OrgTeamMemberDetail[]
}

export interface OrganizationAccountCreatePayload {
  org_name_latin: string
  org_name_arabic?: string | null
  org_type: string
  country: string
  city?: string | null
  full_name: string
  email: string
  phone?: string | null
  password: string
  is_approved?: boolean
  can_publish_events?: boolean
  can_author_courses?: boolean
  can_publish_courses?: boolean
  course_scope_all?: boolean
  allowed_course_ids?: string[]
  quiz_scope?: string
  allowed_quiz_template_ids?: string[]
  max_events?: number | null
  max_programs?: number | null
  max_cohorts?: number | null
  max_students_per_cohort?: number | null
  max_observers_per_cohort?: number | null
}

export interface OrganizationAccountUpdatePayload {
  org_name_latin?: string
  org_name_arabic?: string | null
  org_type?: string
  country?: string | null
  city?: string | null
  full_name?: string
  email?: string
  phone?: string | null
  password?: string
  is_approved?: boolean
  can_publish_events?: boolean
  can_author_courses?: boolean
  can_publish_courses?: boolean
  course_scope_all?: boolean
  allowed_course_ids?: string[]
  quiz_scope?: string
  allowed_quiz_template_ids?: string[]
  max_events?: number | null
  max_programs?: number | null
  max_cohorts?: number | null
  max_students_per_cohort?: number | null
  max_observers_per_cohort?: number | null
}

export type OrgSandboxRole = "owner" | "coordinator" | "instructor" | "judge" | "observer"
export const ORG_ASSIGNABLE_ROLES: { value: Exclude<OrgSandboxRole, "owner">; label: string; hint: string }[] = [
  { value: "coordinator", label: "Coordinator", hint: "Runs programs, cohorts, students and the team" },
  { value: "instructor", label: "Instructor", hint: "Delivers assigned sessions, takes attendance" },
  { value: "judge", label: "Judge", hint: "Scores competition teams for assigned cohorts" },
  { value: "observer", label: "Observer", hint: "Read-only view of assigned cohorts" },
]

export interface OrgTeamMember {
  id: string
  email: string
  full_name: string
  phone?: string | null
  is_active?: boolean
  status?: string
  is_owner: boolean
  org_role?: OrgSandboxRole
  created_at?: string
  invite_email_sent?: boolean
  invite_pending?: boolean
  existing_account?: boolean
}

// ── Admin Endpoints ──────────────────────────────────────────────────────────
export const getAdminMegaEvents = () =>
  api.get<MegaEvent[]>("/admin/website/mega-events").then((r) => r.data)

export const createAdminMegaEvent = (payload: MegaEventCreateInput) =>
  api.post<MegaEvent>("/admin/website/mega-events", payload).then((r) => r.data)

export const updateAdminMegaEvent = (id: string, payload: Partial<MegaEventCreateInput>) =>
  api.put<MegaEvent>(`/admin/website/mega-events/${id}`, payload).then((r) => r.data)

export const deleteAdminMegaEvent = (id: string) =>
  api.delete(`/admin/website/mega-events/${id}`)

export const getAdminWebsiteEvents = () =>
  api.get<WebsiteEvent[]>("/admin/website/events").then((r) => r.data)

export const createAdminWebsiteEvent = (payload: WebsiteEventInput) =>
  api.post<WebsiteEvent>("/admin/website/events", payload).then((r) => r.data)

export const updateAdminWebsiteEvent = (id: string, payload: Partial<WebsiteEventInput>) =>
  api.put<WebsiteEvent>(`/admin/website/events/${id}`, payload).then((r) => r.data)

export const togglePublishWebsiteEvent = (id: string, is_published: boolean) =>
  api.post<WebsiteEvent>(`/admin/website/events/${id}/publish`, { is_published }).then((r) => r.data)

export const deleteAdminWebsiteEvent = (id: string) =>
  api.delete(`/admin/website/events/${id}`)

export const getAdminEventOrganizations = () =>
  api.get<OrganizationAccountSummary[]>("/admin/website/organizations").then((r) => r.data)

export const createAdminOrganizationAccount = (payload: OrganizationAccountCreatePayload) =>
  api.post<OrganizationAccountSummary>("/admin/website/organizations/account", payload).then((r) => r.data)

export const updateAdminOrganizationAccount = (orgId: string, payload: OrganizationAccountUpdatePayload) =>
  api.put<OrganizationAccountSummary>(`/admin/website/organizations/${orgId}`, payload).then((r) => r.data)

export const deleteAdminOrganizationAccount = (orgId: string) =>
  api.delete(`/admin/website/organizations/${orgId}`)

export interface OrgCredentialsLinkResponse {
  organization_id: string
  user_id: string
  email: string
  reset_url: string
  email_sent: boolean
}

export const getAdminOrganizationResetLink = (orgId: string) =>
  api
    .post<OrgCredentialsLinkResponse>(`/admin/website/organizations/${orgId}/reset-link`)
    .then((r) => r.data)

export const getAdminOrganizationDetail = (orgId: string) =>
  api.get<OrganizationDetail>(`/admin/website/organizations/${orgId}/detail`).then((r) => r.data)

export const createOrganizationMemberResetLink = (orgId: string, userId: string) =>
  api
    .post<OrgCredentialsLinkResponse>(
      `/admin/website/organizations/${orgId}/members/${userId}/reset-link`
    )
    .then((r) => r.data)

export const createOrganizationMember = (
  orgId: string,
  payload: { full_name: string; email: string; phone?: string | null; org_role?: string }
) =>
  api
    .post<OrgTeamMember>(`/admin/website/organizations/${orgId}/members`, payload)
    .then((r) => r.data)

export const updateOrganizationMember = (orgId: string, userId: string, org_role: string) =>
  api
    .patch<OrgTeamMember>(`/admin/website/organizations/${orgId}/members/${userId}`, { org_role })
    .then((r) => r.data)

export const removeOrganizationMember = (orgId: string, userId: string) =>
  api.delete(`/admin/website/organizations/${orgId}/members/${userId}`)

export const toggleOrganizationCoursePublish = (orgId: string, courseId: string, is_published: boolean) =>
  api
    .post<{ id: string; is_published: boolean }>(
      `/admin/website/organizations/${orgId}/courses/${courseId}/publish`,
      { is_published }
    )
    .then((r) => r.data)

// ── Organization Self-Service Endpoints ──────────────────────────────────────
export interface MyOrganizationContext {
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
    max_events?: number | null
    max_programs?: number | null
    max_cohorts?: number | null
    max_students_per_cohort?: number | null
    max_observers_per_cohort?: number | null
  } | null
  mega_events: MegaEvent[]
}

export const getMyOrganizationContext = () =>
  api.get<MyOrganizationContext>("/organization/me").then((r) => r.data)

export const getOrganizationTeamApi = () =>
  api.get<OrgTeamMember[]>("/organization/team").then((r) => r.data)

export const addOrganizationTeamMemberApi = (payload: {
  email: string
  full_name: string
  password?: string
  phone?: string | null
  org_role?: string
}) => api.post<OrgTeamMember>("/organization/team", payload).then((r) => r.data)

export const updateOrganizationTeamMemberApi = (userId: string, org_role: string) =>
  api.patch<OrgTeamMember>(`/organization/team/${userId}`, { org_role }).then((r) => r.data)

export const removeOrganizationTeamMemberApi = (userId: string) =>
  api.delete(`/organization/team/${userId}`)

export const getOrganizationMemberResetLinkApi = (userId: string) =>
  api
    .post<{
      organization_id: string
      user_id: string
      email: string
      reset_url: string
      email_sent: boolean
    }>(`/organization/team/${userId}/reset-link`)
    .then((r) => r.data)

export const getMyOrganizationEvents = () =>
  api.get<WebsiteEvent[]>("/organization/events").then((r) => r.data)

export const createMyOrganizationEvent = (payload: WebsiteEventInput) =>
  api.post<WebsiteEvent>("/organization/events", payload).then((r) => r.data)

export const updateMyOrganizationEvent = (id: string, payload: Partial<WebsiteEventInput>) =>
  api.put<WebsiteEvent>(`/organization/events/${id}`, payload).then((r) => r.data)

export const deleteMyOrganizationEvent = (id: string) =>
  api.delete(`/organization/events/${id}`)

export async function organizationSignupApi(
  payload: OrganizationAccountCreatePayload & { phone: string; answers?: Record<string, unknown> },
): Promise<User> {
  const { data } = await api.post<{
    access_token: string
    refresh_token: string
    user: User
  }>("/auth/organization-signup", payload)
  tokens.set(data)
  return data.user
}

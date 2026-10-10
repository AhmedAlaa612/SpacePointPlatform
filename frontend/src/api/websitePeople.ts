import { api } from "./client"

// ── Team ────────────────────────────────────────────────────────────────────

export interface WebsiteTeamMember {
  id: string
  name: string
  role: string
  department: string
  bio: string | null
  photo_url: string
  linkedin_url: string | null
  display_order: number
  is_active: boolean
  created_at: string
  updated_at: string
}

export type WebsiteTeamCreate = Pick<
  WebsiteTeamMember,
  "name" | "role" | "department" | "bio" | "photo_url" | "linkedin_url" | "display_order" | "is_active"
>

export type WebsiteTeamUpdate = Partial<
  Pick<
    WebsiteTeamMember,
    "name" | "role" | "department" | "bio" | "photo_url" | "linkedin_url" | "display_order" | "is_active"
  >
>

export const getWebsiteTeam = () =>
  api.get<WebsiteTeamMember[]>("/admin/website/team").then((r) => r.data)

export const createWebsiteTeamMember = (payload: WebsiteTeamCreate) =>
  api.post<WebsiteTeamMember>("/admin/website/team", payload).then((r) => r.data)

export const updateWebsiteTeamMember = (id: string, payload: WebsiteTeamUpdate) =>
  api.put<WebsiteTeamMember>(`/admin/website/team/${id}`, payload).then((r) => r.data)

export const deleteWebsiteTeamMember = (id: string) =>
  api.delete(`/admin/website/team/${id}`).then((r) => r.data)

// ── Ambassadors ─────────────────────────────────────────────────────────────

export interface WebsiteAmbassador {
  id: string
  name: string
  university: string
  major: string | null
  year: string | null
  bio: string | null
  photo_url: string
  badge: string | null
  linkedin_url: string | null
  display_order: number
  is_active: boolean
  created_at: string
  updated_at: string
}

export type WebsiteAmbassadorCreate = Pick<
  WebsiteAmbassador,
  | "name"
  | "university"
  | "major"
  | "year"
  | "bio"
  | "photo_url"
  | "badge"
  | "linkedin_url"
  | "display_order"
  | "is_active"
>

export type WebsiteAmbassadorUpdate = Partial<
  Pick<
    WebsiteAmbassador,
    | "name"
    | "university"
    | "major"
    | "year"
    | "bio"
    | "photo_url"
    | "badge"
    | "linkedin_url"
    | "display_order"
    | "is_active"
  >
>

export const getWebsiteAmbassadors = () =>
  api.get<WebsiteAmbassador[]>("/admin/website/ambassadors").then((r) => r.data)

export const createWebsiteAmbassador = (payload: WebsiteAmbassadorCreate) =>
  api.post<WebsiteAmbassador>("/admin/website/ambassadors", payload).then((r) => r.data)

export const updateWebsiteAmbassador = (id: string, payload: WebsiteAmbassadorUpdate) =>
  api.put<WebsiteAmbassador>(`/admin/website/ambassadors/${id}`, payload).then((r) => r.data)

export const deleteWebsiteAmbassador = (id: string) =>
  api.delete(`/admin/website/ambassadors/${id}`).then((r) => r.data)

// ── Alumni ──────────────────────────────────────────────────────────────────

export interface WebsiteAlumni {
  id: string
  name: string
  program_completed: string
  current_role: string
  testimonial: string | null
  photo_url: string
  linkedin_url: string | null
  display_order: number
  is_active: boolean
  created_at: string
  updated_at: string
}

export type WebsiteAlumniCreate = Pick<
  WebsiteAlumni,
  | "name"
  | "program_completed"
  | "current_role"
  | "testimonial"
  | "photo_url"
  | "linkedin_url"
  | "display_order"
  | "is_active"
>

export type WebsiteAlumniUpdate = Partial<
  Pick<
    WebsiteAlumni,
    | "name"
    | "program_completed"
    | "current_role"
    | "testimonial"
    | "photo_url"
    | "linkedin_url"
    | "display_order"
    | "is_active"
  >
>

export const getWebsiteAlumni = () =>
  api.get<WebsiteAlumni[]>("/admin/website/alumni").then((r) => r.data)

export const createWebsiteAlumni = (payload: WebsiteAlumniCreate) =>
  api.post<WebsiteAlumni>("/admin/website/alumni", payload).then((r) => r.data)

export const updateWebsiteAlumni = (id: string, payload: WebsiteAlumniUpdate) =>
  api.put<WebsiteAlumni>(`/admin/website/alumni/${id}`, payload).then((r) => r.data)

export const deleteWebsiteAlumni = (id: string) =>
  api.delete(`/admin/website/alumni/${id}`).then((r) => r.data)

// ── Student missions ────────────────────────────────────────────────────────

export interface WebsiteStudentMission {
  id: string
  student_name: string
  project_title: string
  category: string
  description: string
  docx_url: string | null
  photo_url: string | null
  metrics_json: Record<string, string> | null
  display_order: number
  is_active: boolean
  created_at: string
  updated_at: string
}

export type WebsiteStudentMissionCreate = Pick<
  WebsiteStudentMission,
  | "student_name"
  | "project_title"
  | "category"
  | "description"
  | "docx_url"
  | "photo_url"
  | "metrics_json"
  | "display_order"
  | "is_active"
>

export type WebsiteStudentMissionUpdate = Partial<
  Pick<
    WebsiteStudentMission,
    | "student_name"
    | "project_title"
    | "category"
    | "description"
    | "docx_url"
    | "photo_url"
    | "metrics_json"
    | "display_order"
    | "is_active"
  >
>

export const getWebsiteStudentMissions = () =>
  api.get<WebsiteStudentMission[]>("/admin/website/student-missions").then((r) => r.data)

export const createWebsiteStudentMission = (payload: WebsiteStudentMissionCreate) =>
  api.post<WebsiteStudentMission>("/admin/website/student-missions", payload).then((r) => r.data)

export const updateWebsiteStudentMission = (id: string, payload: WebsiteStudentMissionUpdate) =>
  api.put<WebsiteStudentMission>(`/admin/website/student-missions/${id}`, payload).then((r) => r.data)

export const deleteWebsiteStudentMission = (id: string) =>
  api.delete(`/admin/website/student-missions/${id}`).then((r) => r.data)

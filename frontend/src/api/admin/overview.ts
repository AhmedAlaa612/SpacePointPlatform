import { api } from "@/api/client"

export interface PendingRequestsSummary {
  applications: number
  role_requests: number
  documents: number
}

export interface OnboardingSummary {
  pending: number
  to_be_reviewed: number
  phase1_in_progress: number
  phase2_in_progress: number
  phase3_in_progress: number
  phase2_or_3_in_progress: number
}

export interface PaymentsStatusSummary {
  pending: number
  published: number
  signed: number
}

export type AdminActionKind = "app" | "role_request" | "doc_request" | "applicant" | "payment"
export type AdminActionTone = "emerald" | "purple" | "rose" | "neutral"

export interface AdminActionQueueItem {
  id: string
  kind: AdminActionKind
  tag: string
  tone: AdminActionTone
  title: string
  subtitle: string
  cta: string
  href: string
  created_at: string | null
}

export interface BusinessOverview {
  total_users: number
  students: number
  instructors: number
  interns: number
  organizations: number
  ambassadors: number
  mentors: number
  facilitators: number
  applicants: number
  org_members: number
  ops_admin: number
}

export interface AdminCommandOverview {
  pending_requests: PendingRequestsSummary
  onboarding: OnboardingSummary
  payments: PaymentsStatusSummary
  actions: AdminActionQueueItem[]
  business: BusinessOverview
}

export const getAdminOverviewApi = () =>
  api.get<AdminCommandOverview>("/admin/overview").then((r) => r.data)

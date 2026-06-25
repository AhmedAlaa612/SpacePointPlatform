// Instructors domain types (applicant pipeline — Phase 3.2)

export type ApplicationStatus = "in_progress" | "under_review" | "phase_1_approved" | "approved" | "rejected"
export type VideoStatus = "draft" | "submitted"
export type ModuleSubmissionStatus = "submitted" | "approved" | "rejected"

export interface VideoSubmission {
  id: string
  video_no: number
  youtube_url: string | null
  summary_text: string | null
  word_count: number
  status: VideoStatus
  submitted_at: string | null
}

export interface ChecklistItemProgress {
  id: string
  item_code: string
  title: string
  description: string | null
  is_required: boolean
  is_completed: boolean
}

export interface ModuleSection {
  id: string | null
  title: string | null
  items: ChecklistItemProgress[]
}

export interface ChecklistModule {
  id: string
  title: string
  sort_order: number
  sections: ModuleSection[]
  item_count: number
  completed_count: number
  submission_status: ModuleSubmissionStatus | null
  submission_feedback: string | null
}

export interface ApplicationStatusOut {
  status: ApplicationStatus
  feedback: string | null
  reviewed_at: string | null
  presentation_video_link: string | null
}

export const STATUS_LABEL: Record<ApplicationStatus, string> = {
  in_progress: "In progress",
  under_review: "Under review",
  phase_1_approved: "Phase 1 approved",
  approved: "Approved",
  rejected: "Not approved",
}

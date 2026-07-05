// Instructors domain types (applicant pipeline — Phase 3.2)

export type ApplicationStatus = "in_progress" | "under_review" | "phase_1_approved" | "research_approved" | "approved" | "rejected"
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
  research_approved: "Research approved",
  approved: "Approved",
  rejected: "Not approved",
}

// Instructor portal (Phase 3.3/3.4)

export interface InstructorProfile {
  user_id: string
  linkedin_url: string | null
  photo_url: string | null
  contract_url: string | null
  signed_contract_url: string | null
}

export interface IdCard {
  card_id: string | null
  front_b64: string | null   // base64-encoded PNG
  back_b64: string | null    // base64-encoded PNG
  generated_at: string | null
  has_photo: boolean
  has_linkedin: boolean
  photo_url?: string | null
  linkedin_url?: string | null
}

export interface BankDetails {
  account_holder_name: string | null
  bank_name: string | null
  iban: string | null
  swift_bic: string | null
}

export interface InstructorDocument {
  id: string
  document_type: string
  file_url: string
  uploaded_at: string
}

export interface TrainingVideo {
  id: string
  title: string
  description: string | null
  notes: string | null
  video_url: string
  sort_order: number
  is_completed: boolean
}

export interface TrainingModule {
  id: string
  title: string
  description: string | null
  sort_order: number
  videos: TrainingVideo[]
}

export interface LibraryResource {
  id: string
  title: string
  description: string | null
  format: string
  file_url: string   // signed URL for files, raw URL for links
  resource_type: "link" | "file"
}

export interface LibraryModule {
  id: string
  name: string
  description: string | null
  resources: LibraryResource[]
}

// Facilitator — Application Content management

export interface ApplicationVideoConfig {
  video_no: number
  title: string
  url: string
}

export interface ApplicationChecklistItem {
  id: string
  module_id: string
  section_id: string | null
  item_code: string
  title: string
  description: string | null
  sort_order: number
  is_required: boolean
}

export interface ApplicationModule {
  id: string
  title: string
  sort_order: number
  created_at: string | null
  items: ApplicationChecklistItem[]
}

export type PaymentLetterStatus = "draft" | "published" | "signed" | "paid"
export type PaymentSessionRole = "Lead Facilitator" | "Facilitator" | "Assistant Facilitator"

export interface PaymentSession {
  id: string
  session_date: string | null
  workshop_description: string
  role: PaymentSessionRole
  location: string | null
  duration_hours: number | null
  compensation_aed: number
}

export interface PaymentAddon {
  id: string
  description: string
  amount_aed: number
  notes: string | null
}

export interface PaymentLetter {
  id: string
  instructor_user_id?: string | null
  instructor_name?: string | null
  batch_id?: string | null
  letter_date: string | null
  reference: string
  status: PaymentLetterStatus
  is_published: boolean
  pdf_url: string | null
  signed_pdf_url: string | null
  admin_notes?: string | null
  sessions: PaymentSession[]
  addons: PaymentAddon[]
}

export interface PaymentSummary {
  total_earned_aed: number
  total_hours: number
  total_sessions: number
  pending_signature: number
}

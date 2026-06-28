// Shared documents (PLAN §4.5/§8.2 — Phase 4)

export interface Certificate {
  id: string
  user_id: string
  instructor_name?: string | null
  type: "workshop_delivery" | "internship_completion" | "instructor_completion"
  workshop_name?: string | null
  workshop_date?: string | null
  location?: string | null
  file_url: string
  generated_at?: string | null
}

export interface DocumentItem {
  id: string
  label: string
  file_url: string
  generated_at: string
}

export interface MyDocuments {
  certificates: Certificate[]
  documents: DocumentItem[]
}

export interface DocumentRequest {
  id: string
  user_id: string
  user_name?: string
  user_email?: string
  type: "recommendation_letter" | "confirmation_letter" | "completion_letter" | "certificate"
  status: "pending" | "approved" | "rejected"
  requested_role?: string | null
  notes?: string | null
  admin_notes?: string | null
  file_url?: string | null
  user_created_at?: string
  created_at: string
  updated_at: string
}

export interface DocumentTemplate {
  id: string
  key: string
  name: string
  roles: string[]
  body_text?: string | null
  template_file_url?: string | null
  type?: "letter" | "certificate"
  is_system?: boolean
  updated_at: string
}

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
}

export interface RecommendationLetter {
  id: string
  user_id: string
  signatory_name: string
  signatory_title: string
  file_url: string
  generated_at: string
}

export interface InternLetter {
  id: string
  user_id: string
  type: "confirmation" | "completion"
  file_url: string
  generated_at: string
}

export interface MyDocuments {
  certificates: Certificate[]
  recommendation_letters: RecommendationLetter[]
  intern_letters: InternLetter[]
}

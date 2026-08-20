export interface RoleRequest {
  id: string
  requester_user_id: string
  requester_name: string | null
  requester_email: string | null
  target_role: string
  status: "pending" | "approved" | "rejected"
  details: Record<string, unknown>
  resolution: Record<string, unknown>
  admin_notes: string | null
  reviewed_by: string | null
  reviewed_at: string | null
  created_at: string
}

export interface InternProfile {
  user_id: string
  ref_number: string | null
  university_id_number: string | null
  department: string | null
  start_date: string | null
  duration_weeks: number | null
  hours_per_week: number | null
  work_city_id: string | null
  supervisor_name: string | null
  supervisor_email: string | null
  supervisor_phone: string | null
  letter_url: string | null
  signed_letter_url: string | null
  letter_signed_at: string | null
}

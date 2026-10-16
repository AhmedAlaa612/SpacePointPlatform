export interface MentorDomain {
  id: string;
  name: string;
  slug: string;
  category?: string | null;
  display_order: number;
  is_active: boolean;
  created_at: string;
}

export interface MentorProfile {
  id: string;
  user_id: string;
  slug: string;
  headline?: string | null;
  company?: string | null;
  bio?: string | null;
  missions_history?: string | null;
  what_i_can_help_with?: string | null;
  contact_mode: "email" | "calendar";
  google_meet_url?: string | null;
  status: "applied" | "approved" | "rejected" | "suspended";
  is_active: boolean;
  is_published?: boolean;
  invite_code?: string | null;
  photo_url?: string | null;
  contact_email?: string | null;
  show_contact_button?: boolean;
  linkedin_url?: string | null;
  session_duration_minutes: number;
  total_completed_minutes: number;
  completed_sessions_count: number;
  domains: MentorDomain[];
  created_at: string;
  user_full_name?: string | null;
  user_email?: string | null;
  user_photo_url?: string | null;
  user_country?: string | null;
}

export interface MentorAvailability {
  id: string;
  mentor_id: string;
  day_of_week?: number | null; // 0=Mon, 6=Sun
  specific_date?: string | null;
  start_time: string; // "HH:MM:SS" or "HH:MM"
  end_time: string;
  timezone: string;
  is_active: boolean;
}

export interface AvailableSlot {
  start: string; // ISO
  end: string;   // ISO
  available: boolean;
}

export interface MentorBooking {
  id: string;
  mentor_id: string;
  mentee_name: string;
  mentee_email: string;
  topics: string;
  booking_type: "session" | "inquiry";
  scheduled_start?: string | null;
  scheduled_end?: string | null;
  status: "confirmed" | "completed" | "cancelled";
  created_at: string;
  mentor_name?: string | null;
}

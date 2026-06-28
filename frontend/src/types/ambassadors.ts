// Ambassador domain types

export interface Lead {
  id: string
  ambassador_id: string
  contact_name: string
  company: string | null
  type: string
  status: string
  notes: string | null
  created_at: string
  ambassador_name?: string | null
  ambassador_email?: string | null
}

export interface LeadComment {
  id: string
  lead_id: string
  author_id: string | null
  body: string
  created_at: string
  author_name: string | null
  author_role: string | null
}

export interface Task {
  id: string
  assigned_to: string
  created_by: string | null
  title: string
  description: string | null
  deadline: string | null
  status: string
  points_reward: number
  edit_notes: string | null
  submission: string | null
  points_awarded?: boolean
  created_at: string
}

export interface AssignableUser {
  id: string
  full_name: string
  email: string
  roles: string[]
  country: string | null
}

export interface Teacher {
  id: string
  full_name: string
  email: string
  status: string
  created_at: string
}

export interface Instructor {
  id: string
  invited_by_id: string
  full_name: string
  email: string
  status: string
  created_at: string
}

export interface TeacherSession {
  id: string
  teacher_id: string
  title: string
  description: string | null
  date: string
  status: string
  status_note?: string | null
  material_sent: boolean
  material_link: string | null
  planned_students: number
  attended_students: number
  created_at: string
  teacher_name?: string | null
  teacher_email?: string | null
  ambassador_name?: string | null
}

export interface Title {
  id: string
  name: string
  min_points: number
  icon: string | null
  color: string | null
  sort_order: number
  audience: "ambassador" | "teacher"
}

export interface TitleBrief {
  id: string
  name: string
  min_points: number
  icon: string | null
  color: string | null
}

export interface Badge {
  id: string
  code: string
  label: string
  description: string | null
  icon: string | null
  criteria_type: string
  threshold: number
  sort_order: number
  audience: "ambassador" | "teacher"
}

export interface Material {
  id: string
  created_by: string | null
  title: string
  description: string | null
  link: string
  category: string | null
  created_at: string
  created_by_name?: string | null
}

export interface Achievement {
  code: string
  label: string
  description: string
  icon: string
  earned: boolean
  earned_at: string | null
}

export interface PointsTransaction {
  id: string
  ambassador_id: string
  amount: number
  type: string
  reason: string
  created_at: string
  ambassador_name?: string | null
  ambassador_email?: string | null
}

export interface LeaderboardEntry {
  id: string
  name: string
  country: string
  points: number
  teachers: number
  instructors: number
  sessions_done: number
  converted_leads: number
  students_reached: number
}

export interface DashboardStats {
  active_teachers: number
  pending_teachers: number
  active_instructors: number
  pending_instructors: number
  total_leads: number
  pending_leads: number
  converted_leads: number
  pending_tasks: number
  completed_tasks: number
  sessions_done: number
  sessions_pending: number
  students_reached: number
  points_balance: number
  season_points: number
  my_rank: number
  leaderboard: LeaderboardEntry[]
  season_leaderboard: LeaderboardEntry[]
  achievements: Achievement[]
  current_title: TitleBrief | null
  next_title: TitleBrief | null
  points_to_next: number
  progress_to_next: number
}

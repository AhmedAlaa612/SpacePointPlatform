import type { User } from "@/types/shared";

// Interns reuse the platform User (roles[]); re-export so ported code's
// `import { User } from "@/types/interns"` keeps working.
export type { User };

export type Role = "admin" | "leader" | "intern";
export type WorkStatus = "todo" | "in_progress" | "done";
export type SubmissionStatus = "submitted" | "reviewed";
export type ProjectStatus = "active" | "completed";

/** The interns-relevant single role for a user (admin > leader > intern). */
export function userRole(u: { roles: string[] }): Role {
  if (u.roles.includes("admin")) return "admin";
  if (u.roles.includes("leader")) return "leader";
  return "intern";
}

export interface Team {
  id: string;
  name: string;
  leader_id: string;
  members: User[];
}

export interface Project {
  id: string;
  title: string;
  description: string | null;
  status: ProjectStatus;
  created_by: string | null;
  created_at: string;
}

export interface TaskBrief {
  id: string;
  title: string;
  status: WorkStatus;
  due_date: string | null;
  expected_time: number | null;
  actual_time: number | null;
  assignee_count: number;
  assignees: User[];
}

export interface Module {
  id: string;
  epic_id: string;
  title: string;
  description: string | null;
  created_at: string;
  tasks: TaskBrief[];
}

export interface Epic {
  id: string;
  project_id: string;
  team_id: string;
  title: string;
  description: string | null;
  status: WorkStatus;
  created_by: string | null;
  created_at: string;
  modules: Module[];
  team_name: string | null;
  leader_name: string | null;
}

export interface Submission {
  id: string;
  task_id: string;
  submitted_by: string;
  submitter_name: string | null;
  link: string;
  note: string | null;
  status: SubmissionStatus;
  score: number | null;
  review_comment: string | null;
  submitted_at: string;
  reviewed_at: string | null;
}

export interface Task {
  id: string;
  module_id: string;
  title: string;
  description: string | null;
  status: WorkStatus;
  due_date: string | null;
  expected_time: number | null;
  actual_time: number | null;
  created_by: string | null;
  created_at: string;
  assignees: User[];
  submissions: Submission[];
  module_title: string | null;
  module_description: string | null;
  epic_id: string | null;
  epic_title: string | null;
  epic_description: string | null;
  project_id: string | null;
}

export interface Proposal {
  id: string;
  epic_id: string;
  proposed_by: string;
  proposer_name: string | null;
  title: string;
  description: string | null;
  status: "pending" | "accepted" | "rejected";
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string;
}

export interface Notification {
  id: string;
  user_id: string;
  title: string;
  body: string | null;
  is_read: boolean;
  created_at: string;
}

export interface BoardCard {
  id: string;
  title: string;
  epic_id: string | null;
  epic_title: string | null;
  epic_description: string | null;
  module_title: string | null;
  module_description: string | null;
  project_title: string | null;
  status: WorkStatus;
  due_date: string | null;
  description: string | null;
  expected_time: number | null;
  actual_time: number | null;
  assignees: User[];
  submissions: Submission[];
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

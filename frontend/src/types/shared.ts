/** The eight roles in the unified platform (PLAN §1). */
export type Role =
  | "admin"
  | "intern"
  | "leader"
  | "applicant"
  | "instructor"
  | "facilitator"
  | "ambassador"
  | "teacher";

/** Which navbar domain a role routes into. */
export type Domain = "interns" | "instructors" | "ambassadors" | "admin";

export const ROLE_DOMAIN: Record<Role, Domain> = {
  admin: "admin",
  intern: "interns",
  leader: "interns",
  applicant: "instructors",
  instructor: "instructors",
  facilitator: "instructors",
  ambassador: "ambassadors",
  teacher: "ambassadors",
};

export const ROLE_LABEL: Record<Role, string> = {
  admin: "Admin",
  intern: "Intern",
  leader: "Team Leader",
  applicant: "Applicant",
  instructor: "Instructor",
  facilitator: "Facilitator",
  ambassador: "Ambassador",
  teacher: "Teacher",
};

export interface User {
  id: string;
  full_name: string;
  email: string;
  roles: Role[];
  status: string;
  phone?: string | null;
  country?: string | null;
  invite_code?: string | null;
  photo_url?: string | null;
  linkedin_url?: string | null;
  must_change_password?: boolean;
  created_at?: string;
  last_login_at?: string | null;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface Notification {
  id: string;
  user_id: string;
  title: string;
  body: string | null;
  type?: string | null;
  is_read: boolean;
  created_at: string;
}

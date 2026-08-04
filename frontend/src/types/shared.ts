/** The eight roles in the unified platform (PLAN §1). */
export type Role =
  | "admin"
  | "intern"
  | "leader"
  | "applicant"
  | "instructor"
  | "facilitator"
  | "ambassador"
  | "teacher"
  | "operations"
  // Inventory phase (I0-2). NOTE: neither has a frontend home yet — the pages
  // they need land in I1-4. Assignable so an admin can prepare accounts, but
  // a user holding only one of these has nowhere useful to be redirected to
  // until then. See INVENTORY_EXECUTION_PLAN.md.
  | "coo"
  | "storekeeper"
  // LMS phase (LM0-2). Students live at /learn/* — a separate surface with its
  // own shell, login and navbar, mounted outside the portal's auth layout. A
  // student who lands on "/" is redirected there by `indexRoute.beforeLoad`;
  // they have no portal home and are not meant to.
  | "student";

/**
 * There is deliberately no `ROLE_DOMAIN` map. One existed until I0-1
 * (2026-07-28) but nothing ever imported it, so it drifted and the plan's
 * decision register ended up citing a constant that did nothing.
 *
 * Role → domain routing actually lives in two places, and those are the ones to
 * edit:
 *   - `router.tsx` `indexRoute.beforeLoad` — where "/" sends each active role.
 *   - `components/layout/Sidebar.tsx` `getNavItems(pathname, activeRole)` —
 *     which nav set renders, chosen by URL path first and active role second.
 */

export const ROLE_LABEL: Record<Role, string> = {
  admin: "Admin",
  intern: "Intern",
  leader: "Team Leader",
  applicant: "Applicant",
  instructor: "Instructor",
  facilitator: "Facilitator",
  ambassador: "Ambassador",
  teacher: "Teacher",
  operations: "Operations",
  coo: "COO",
  storekeeper: "Storekeeper",
  student: "Student",
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
  // Applicant-derived fields (instructors/facilitators/applicants). Null/absent
  // when the user has no applicant_profile.
  city_of_residence?: string | null;
  deliver_cities?: string[] | null;
  has_own_transportation?: boolean | null;
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

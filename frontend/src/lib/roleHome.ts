import type { OrgSandboxRole, Role } from "@/types/shared";

export function orgRoleHomePath(orgRole: OrgSandboxRole | null): string {
  switch (orgRole) {
    case "instructor":
      return "/organization/my-sessions";
    case "judge":
      return "/organization/judging";
    case "owner":
    case "coordinator":
    case "observer":
    case null:
    default:
      return "/organization/programs";
  }
}

/** Where a role lands on "/" (see router.tsx's indexRoute) — the single
 * source of truth for "what is this role's portal home", so LearnNav's
 * "Back to portal" link and the index redirect can't drift apart. */
export function roleHomePath(role: Role | null, orgRole: OrgSandboxRole | null = null): string {
  switch (role) {
    case "admin": return "/admin";
    case "ambassador": return "/ambassadors";
    case "teacher": return "/ambassadors/teacher-portal";
    case "applicant": return "/instructors/status";
    case "instructor": return "/instructors/dashboard";
    case "facilitator": return "/instructors/facilitator/training";
    case "operations": return "/operations/dashboard";
    case "coo": return "/operations/inventory";
    case "storekeeper": return "/operations/inventory/stock";
    // Students have no portal home — /learn is theirs. Any other/unset
    // role (intern, leader, null) falls back to the interns landing, same
    // as the index redirect's final `else`.
    case "student": return "/learn";
    // Competition domain (2026-08-24) — judges have no portal home either,
    // same reasoning as students: /judge is a separate surface.
    case "judge": return "/judge";
    case "lms_author": return "/lms-authoring/courses";
    case "organization": return orgRoleHomePath(orgRole);
    case "mentor": return "/mentor/settings";
    // Safety net only — activeRole should never be observer (see
    // resolveActiveRole + RoleSwitcher filtering). Observers run the
    // student engine, so /learn is the sane landing if it ever happens.
    case "observer": return "/learn";
    case null: return "/learn";
    default: return "/interns";
  }
}

const STUDENT_ONLY_ROLES: ReadonlySet<Role> = new Set(["student", "observer", "applicant"]);

/**
 * True when the user is a student (or observer/student-applicant) with no
 * instructor, intern, or staff/portal roles — used to gate student-only
 * internship and instructor intake actions.
 */
export function isStudentOnlyAccount(roles?: readonly Role[] | null): boolean {
  if (!roles || roles.length === 0) return false;
  const hasStudentSurface = roles.some((r) => r === "student" || r === "observer");
  if (!hasStudentSurface) return false;
  return roles.every((r) => STUDENT_ONLY_ROLES.has(r));
}

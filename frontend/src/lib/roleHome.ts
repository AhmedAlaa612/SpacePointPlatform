import type { Role } from "@/types/shared";

/** Where a role lands on "/" (see router.tsx's indexRoute) — the single
 * source of truth for "what is this role's portal home", so LearnNav's
 * "Back to portal" link and the index redirect can't drift apart. */
export function roleHomePath(role: Role | null): string {
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
    default: return "/interns";
  }
}

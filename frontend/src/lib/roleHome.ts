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
    // Competition domain (2026-08-24) — judges have no portal home either,
    // same reasoning as students: /judge is a separate surface.
    case "judge": return "/judge";
    case "lms_author": return "/lms-authoring/courses";
    case "organization": return "/organization/events";
    case "mentor": return "/mentor/profile";
    // Safety net only — activeRole should never be observer (see
    // resolveActiveRole + RoleSwitcher filtering). Observers run the
    // student engine, so /learn is the sane landing if it ever happens.
    case "observer": return "/learn";
    default: return "/interns";
  }
}

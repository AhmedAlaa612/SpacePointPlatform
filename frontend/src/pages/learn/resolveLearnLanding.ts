import { fetchMyChecklists } from "@/api/lms";

/** Where a just-authenticated student should land — their latest program's
 * board if they have one (`/lms/programs` is already ordered newest-first,
 * see `services/lms/program.py::list_student_assignments`), the general
 * `/learn` dashboard otherwise. Only used at the login/signup moment: the
 * sidebar's own "Home" link always goes to `/learn` regardless, so a
 * program student can still reach the general dashboard on purpose — this
 * only decides the *default* first stop. Never blocks auth on itself: any
 * failure here just falls back to `/learn`. */
export async function resolveLearnLanding(): Promise<string> {
  try {
    const checklists = await fetchMyChecklists();
    if (checklists.length > 0) return `/learn/checklists/${checklists[0].assignment_id}`;
  } catch {
    /* fall through to the general dashboard */
  }
  return "/learn";
}

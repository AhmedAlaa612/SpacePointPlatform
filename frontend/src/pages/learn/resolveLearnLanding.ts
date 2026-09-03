import { fetchMyChecklists } from "@/api/lms";

/** Where a just-authenticated student should land — their latest program's
 * board if they have one (`/lms/programs` is already ordered newest-first,
 * see `services/lms/program.py::list_student_assignments`), the general
 * `/learn` dashboard otherwise. Also re-run by `learnLandingRoute`'s own
 * `beforeLoad` on every fresh visit to bare `/learn` (typed URL, refresh,
 * a bookmark) — "opening the site" should land a program student on their
 * board. The sidebar/tab-bar Home link deliberately goes to `/learn/home`
 * instead, a plain route with no such redirect, so a program student can
 * still reach the general dashboard on purpose by clicking Home. Never
 * blocks auth on itself: any failure here just falls back to `/learn`. */
export async function resolveLearnLanding(): Promise<string> {
  try {
    const checklists = await fetchMyChecklists();
    if (checklists.length > 0) return `/learn/checklists/${checklists[0].assignment_id}`;
  } catch {
    /* fall through to the general dashboard */
  }
  return "/learn";
}

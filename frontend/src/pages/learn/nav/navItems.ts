import { Home, GraduationCap, Gamepad2, Trophy, ClipboardCheck, Rocket } from "lucide-react";
// import { Rocket } from "lucide-react"; // Missions icon — restore alongside the NAV_ITEMS entry below

/** `catalog`, `paths` and `profile` are still reachable pages — they just
 * aren't nav entries any more (2026-08-12): discovery moved onto the landing
 * page's rails, and Profile was a duplicate of the avatar menu top-right.
 * They keep their keys so those pages can still mark themselves active.
 * `home` joined them on the *desktop* sidebar too (2026-09) — see the
 * Roadmap board redesign: the old navbar dropped it in favor of the logo
 * link, but a fixed sidebar has no logo-as-home affordance, so the sidebar
 * shows all six the same as the mobile tab bar always has. */
export type LearnNavActive = "home" | "catalog" | "missions" | "paths" | "checklists" | "my-courses" | "games" | "arcade" | "leaderboard" | "profile";

export const NAV_ITEMS: { key: LearnNavActive; label: string; to: string; icon: typeof Home }[] = [
  { key: "home", label: "Home", to: "/learn/home", icon: Home },
  { key: "my-courses", label: "My Learning", to: "/learn/my-courses", icon: GraduationCap },
  { key: "checklists", label: "Programs", to: "/learn/checklists", icon: ClipboardCheck },
  // Missions tab hidden temporarily per management request; re-enable by uncommenting.
  // { key: "missions", label: "Missions", to: "/learn/missions", icon: Rocket },
  { key: "games", label: "Live Quiz", to: "/learn/games", icon: Gamepad2 },
  { key: "arcade", label: "Arcade", to: "/learn/arcade", icon: Rocket },
  { key: "leaderboard", label: "Leaderboard", to: "/learn/leaderboard", icon: Trophy },
];

/** One row of 5 on mobile — Home lives in the profile row instead (see
 * LearnMobileTabBar). Unchanged by the sidebar redesign (2026-09). */
// Missions tab hidden temporarily per management request; re-enable by uncommenting NAV_ITEMS
// above and restoring "missions" here in its original slot: ["my-courses", "checklists", "missions", "games", "leaderboard"].
export const MOBILE_TAB_ITEMS: LearnNavActive[] = ["my-courses", "checklists", "games", "arcade", "leaderboard"];

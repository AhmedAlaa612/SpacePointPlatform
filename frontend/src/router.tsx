import {
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  redirect,
  useLocation,
} from "@tanstack/react-router";
import { AppShell, ApplicantShell } from "@/components/layout/Sidebar";
import { Login } from "@/pages/auth/Login";
import { tokens } from "@/api/client";
import { roleHomePath } from "@/lib/roleHome";
import type { Role } from "@/types/shared";

// Shared pages
import SharedProfile from "@/pages/shared/Profile";

// Interns domain pages
import Dashboard from "@/pages/interns/Dashboard";
import ProposeMission from "@/pages/interns/ProposeMission";
import ManageMissions from "@/pages/interns/ManageMissions";
import Tracker from "@/pages/interns/Tracker";
import Calendar from "@/pages/interns/Calendar";
import Leaderboard from "@/pages/interns/Leaderboard";
import Admin from "@/pages/interns/Admin";
import MindMap from "@/pages/interns/MindMap";
import ProjectMindMap from "@/pages/interns/ProjectMindMap";

// Ambassadors domain pages
import AmbassadorDashboard from "@/pages/ambassadors/Dashboard";
import AmbassadorLeads from "@/pages/ambassadors/Leads";
import AmbassadorTasks from "@/pages/ambassadors/Tasks";
import AmbassadorNetwork from "@/pages/ambassadors/Network";
import AmbassadorTeacherProfile from "@/pages/ambassadors/TeacherProfile";
import AmbassadorLeaderboard from "@/pages/ambassadors/Leaderboard";
import AmbassadorMaterials from "@/pages/ambassadors/Materials";
import AmbassadorTeacherPortal from "@/pages/ambassadors/TeacherPortal";
import AmbassadorsAdminNetwork from "@/pages/ambassadors/admin/Network";
import AmbassadorsAdminTasks from "@/pages/ambassadors/admin/Tasks";
import AmbassadorsAdminLeads from "@/pages/ambassadors/admin/Leads";
import AmbassadorsAdminSessions from "@/pages/ambassadors/admin/Sessions";
import AmbassadorsAdminTitles from "@/pages/ambassadors/admin/Titles";
import AmbassadorsAdminBadges from "@/pages/ambassadors/admin/Badges";
import AmbassadorsAdminSettings from "@/pages/ambassadors/admin/Settings";
import AdminAmbassador from "@/pages/ambassadors/AdminAmbassador";

// Instructors domain pages
import InstructorStatus from "@/pages/instructors/Status";
import InstructorVideos from "@/pages/instructors/pipeline/Videos";
import InstructorModules from "@/pages/instructors/pipeline/Modules";
import InstructorModuleDetail from "@/pages/instructors/pipeline/ModuleDetail";
import InstructorApply from "@/pages/instructors/apply/InstructorApply";
import InstructorDashboard from "@/pages/instructors/Dashboard";
import InstructorTraining from "@/pages/instructors/Training";
import InstructorTrainingPlayer from "@/pages/instructors/TrainingPlayer";
import InstructorLibrary from "@/pages/instructors/Library";
import UserDocuments from "@/pages/shared/UserDocuments";
import PersonalDocuments from "@/pages/shared/PersonalDocuments";
import ProfileCard from "@/pages/shared/ProfileCard";
import InstructorPersonalDocuments from "@/pages/instructors/PersonalDocuments";
import InstructorIdCard from "@/pages/instructors/ProfileCard";
import InstructorPayments from "@/pages/instructors/Payments";
import InstructorsAdminOverview from "@/pages/instructors/admin/Overview";
import InstructorsAdminApplicants from "@/pages/instructors/admin/Applicants";
import InstructorsAdminInvitations from "@/pages/instructors/admin/Invitations";
import InstructorsAdminInstructors from "@/pages/instructors/admin/Instructors";
import InstructorsAdminFacilitators from "@/pages/instructors/admin/Facilitators";
import InstructorsAdminPayments from "@/pages/instructors/admin/Payments";
import InstructorsAdminCertificates from "@/pages/instructors/admin/Certificates";
import ApplicantReviewPage from "@/pages/instructors/ApplicantReview";
import FacilitatorTraining from "@/pages/instructors/facilitator/Training";
import FacilitatorLibrary from "@/pages/instructors/facilitator/Library";
import FacilitatorApplication from "@/pages/instructors/facilitator/Application";
import InstructorAvailableSessions from "@/pages/instructors/AvailableSessions";
import InstructorMySessions from "@/pages/instructors/MySessions";
import InstructorSessionDetail from "@/pages/instructors/SessionDetail";
import GameLiveConsole from "@/pages/instructors/GameLiveConsole";
import InstructorMyHoldings from "@/pages/instructors/MyHoldings";

// Admin hub
import AdminHub from "@/pages/admin/Dashboard";
import AdminUsers from "@/pages/admin/Users";
import AdminDocuments from "@/pages/admin/Documents";
import AdminApplications from "@/pages/admin/Applications";
import Settings from "@/pages/admin/Settings";

// Sessions/spine domain pages (V2 R2-3/R2-4/R2-5)
import AdminPrograms from "@/pages/admin/Programs";
import AdminCohorts from "@/pages/admin/Cohorts";
import AdminCohortDetail from "@/pages/admin/CohortDetail";
import AdminSessionDetail from "@/pages/admin/SessionDetail";
import SessionGameAssignmentDetail from "@/pages/admin/SessionGameAssignmentDetail";
import AdminContacts from "@/pages/admin/Contacts";
import AdminMergeReviews from "@/pages/admin/MergeReviews";
import AdminCheckIn from "@/pages/admin/CheckIn";
import SessionsCalendar from "@/pages/sessions/Calendar";
import OpsDashboard from "@/pages/sessions/OpsDashboard";
import ThisWeek from "@/pages/sessions/ThisWeek";

// Inventory (I1-4)
import InventoryKits from "@/pages/operations/inventory/Kits";
import InventoryKitDetail from "@/pages/operations/inventory/KitDetail";
import InventoryLocationDetail from "@/pages/operations/inventory/LocationDetail";
import InventoryStock from "@/pages/operations/inventory/Stock";
import InventoryCatalog from "@/pages/operations/inventory/Catalog";
import InventoryFulfilment from "@/pages/operations/inventory/Fulfilment";
import DeliverySettings from "@/pages/operations/DeliverySettings";

// Unified apply flow
import ApplyFlow from "@/pages/apply/ApplyFlow";

// Public landing pages (no auth) — shown at bare /instructors and /interns when logged out
import InstructorsLanding from "@/pages/public/InstructorsLanding";
import InternsLanding from "@/pages/public/InternsLanding";
import Ticket from "@/pages/public/Ticket";
import KitScan from "@/pages/public/KitScan";

// LMS student surface (LMS D1) — a separate surface in the same app: own shell,
// own login/signup, no portal chrome. See pages/learn/LearnShell.tsx.
import { LearnShell } from "@/pages/learn/LearnShell";
import LearnLogin from "@/pages/learn/LearnLogin";
import LearnSignup from "@/pages/learn/LearnSignup";
import LearnSetPassword from "@/pages/learn/LearnSetPassword";
import LearnLanding from "@/pages/learn/LearnLanding";
import LearnCatalog from "@/pages/learn/LearnCatalog";
import LearnMyCourses from "@/pages/learn/LearnMyCourses";
import LearnCourse from "@/pages/learn/LearnCourse";
import LearnPlayer from "@/pages/learn/LearnPlayer";
import LearnPaths from "@/pages/learn/LearnPaths";
import LearnPath from "@/pages/learn/LearnPath";
import LearnProfile from "@/pages/learn/LearnProfile";
import LearnLeaderboard from "@/pages/learn/LearnLeaderboard";
import LearnGames from "@/pages/learn/LearnGames";
import GamePlay from "@/pages/learn/GamePlay";
import LearnProgram from "@/pages/learn/LearnProgram";
import MissionCatalog from "@/pages/learn/MissionCatalog";
import MissionPage from "@/pages/learn/MissionPage";
import DesignMissionPage from "@/pages/learn/DesignMissionPage";
import OperateMissionPage from "@/pages/learn/OperateMissionPage";
import OperateBriefingPage from "@/pages/learn/OperateBriefingPage";
import DesignBriefingPage from "@/pages/learn/DesignBriefingPage";

// LMS authoring surface (LM1-13) — shared by operations + facilitator
// (backend's require_lms_content), own top-level path so one URL space works
// for both roles rather than duplicating pages under /operations and /instructors.
import LmsCourses from "@/pages/lms-authoring/LmsCourses";
import LmsCourseDetail from "@/pages/lms-authoring/LmsCourseDetail";
import LmsModuleDetail from "@/pages/lms-authoring/LmsModuleDetail";
import LmsCurriculum from "@/pages/lms-authoring/LmsCurriculum";
import LmsLearningPaths from "@/pages/lms-authoring/LmsLearningPaths";
import LmsLearningPathDetail from "@/pages/lms-authoring/LmsLearningPathDetail";
import LmsProgressGrid from "@/pages/lms-authoring/LmsProgressGrid";
import LmsMissions from "@/pages/lms-authoring/LmsMissions";
import LmsDesignLibrary from "@/pages/lms-authoring/LmsDesignLibrary";
import LmsMissionDetail from "@/pages/lms-authoring/LmsMissionDetail";
import LmsStudents from "@/pages/lms-authoring/LmsStudents";
import LmsStudentDetail from "@/pages/lms-authoring/LmsStudentDetail";
import LmsInviteCodes from "@/pages/lms-authoring/LmsInviteCodes";
import LmsGames from "@/pages/lms-authoring/LmsGames";
import LmsGameDetail from "@/pages/lms-authoring/LmsGameDetail";

const rootRoute = createRootRoute({ component: () => <Outlet /> });

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  component: Login,
});

/** Public ticket page. Sits at the root (not under the auth shell) because a
 * student holding a QR code has no account — the token in the path is the
 * credential, exactly as it is when staff scan the same code at the door. */
const ticketRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/t/$ticketToken",
  component: Ticket,
});

/** Public kit scan (I2-6). Same reasoning as the ticket page above: whoever is
 *  holding the box has the code, and the page tells them nothing they can't
 *  already read off the sticker. */
const kitScanRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/k/$kitToken",
  component: KitScan,
});

import { useAuth } from "@/context/AuthContext";

/** Bare /instructors and /interns are the only public routes nested in this
 * layout — marketing landing pages for logged-out visitors. Every other
 * nested route still requires a token. */
const PUBLIC_UNAUTHED_PATHS = new Set(["/instructors", "/interns"]);

/** Authenticated shell (PLAN §7 `_auth`): redirect to /login when no token. */
const authLayoutRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: "auth",
  beforeLoad: ({ location }) => {
    if (!tokens.access && !PUBLIC_UNAUTHED_PATHS.has(location.pathname)) {
      throw redirect({ to: "/login" });
    }
  },
  component: () => {
    const { currentUser, isLoading, activeRole } = useAuth();
    const { pathname } = useLocation();

    if (isLoading) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-background text-foreground">
          <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" />
        </div>
      );
    }

    if (!currentUser) {
      if (pathname === "/instructors") return <InstructorsLanding />;
      if (pathname === "/interns") return <InternsLanding />;
      return null;
    }

    return (
      <div className="min-h-screen bg-background text-foreground">
        {activeRole === "applicant" ? (
          <ApplicantShell>
            <Outlet />
          </ApplicantShell>
        ) : (
          <AppShell>
            <Outlet />
          </AppShell>
        )}
      </div>
    );
  },
});

const indexRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/",
  beforeLoad: () => {
    // roleHomePath is the single source of truth for "what is this role's
    // portal home" — LearnNav's "Back to portal" link reuses it too, so the
    // two can't drift apart.
    throw redirect({ to: roleHomePath(localStorage.getItem("active_role") as Role | null) });
  },
});

const internsLayoutRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/interns",
  beforeLoad: () => {
    // No token means bare /interns (a path the parent authLayoutRoute lets
    // through unauthenticated) — defer to authLayoutRoute's component, which
    // renders the public InternsLanding page directly instead of this subtree.
    if (!tokens.access) return;
    const role = localStorage.getItem("active_role");
    if (role !== "intern" && role !== "leader" && role !== "admin") {
      throw redirect({ to: "/" });
    }
  },
  component: () => <Outlet />,
});

const p = () => internsLayoutRoute;
const internsRoutes = [
  createRoute({ getParentRoute: p, path: "/", component: Dashboard }),
  createRoute({ getParentRoute: p, path: "/tracker", component: Tracker }),
  createRoute({ getParentRoute: p, path: "/calendar", component: Calendar }),
  createRoute({ getParentRoute: p, path: "/leaderboard", component: Leaderboard }),
  createRoute({ getParentRoute: p, path: "/profile", component: SharedProfile }),
  createRoute({ getParentRoute: p, path: "/documents", component: PersonalDocuments }),
  createRoute({ getParentRoute: p, path: "/id-card", component: ProfileCard }),
  createRoute({
    getParentRoute: p,
    path: "/admin",
    beforeLoad: () => {
      const role = localStorage.getItem("active_role");
      if (role !== "admin") {
        throw redirect({ to: "/" });
      }
    },
    component: Admin,
  }),
  createRoute({ getParentRoute: p, path: "/mind-map/$epicId", component: MindMap }),
  createRoute({ getParentRoute: p, path: "/mind-map/project/$projectId", component: ProjectMindMap }),
  createRoute({ getParentRoute: p, path: "/propose-mission", component: ProposeMission }),
  createRoute({ getParentRoute: p, path: "/manage-missions", component: ManageMissions }),
];

const ambassadorsLayoutRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/ambassadors",
  beforeLoad: () => {
    const role = localStorage.getItem("active_role");
    if (role !== "ambassador" && role !== "teacher" && role !== "admin") {
      throw redirect({ to: "/" });
    }
  },
  component: () => <Outlet />,
});

const pa = () => ambassadorsLayoutRoute;
const ambassadorsRoutes = [
  createRoute({
    getParentRoute: pa,
    path: "/",
    beforeLoad: () => {
      const role = localStorage.getItem("active_role");
      if (role === "teacher") {
        throw redirect({ to: "/ambassadors/teacher-portal" });
      }
    },
    component: AmbassadorDashboard,
  }),
  createRoute({
    getParentRoute: pa,
    path: "/leads",
    beforeLoad: () => {
      const role = localStorage.getItem("active_role");
      if (role !== "ambassador" && role !== "admin") {
        throw redirect({ to: "/" });
      }
    },
    component: AmbassadorLeads,
  }),
  createRoute({ getParentRoute: pa, path: "/tasks", component: AmbassadorTasks }),
  createRoute({
    getParentRoute: pa,
    path: "/network",
    beforeLoad: () => {
      const role = localStorage.getItem("active_role");
      if (role !== "ambassador" && role !== "admin") {
        throw redirect({ to: "/" });
      }
    },
    component: AmbassadorNetwork,
  }),
  createRoute({
    getParentRoute: pa,
    path: "/network/teacher/$teacherId",
    beforeLoad: () => {
      const role = localStorage.getItem("active_role");
      if (role !== "ambassador" && role !== "admin") {
        throw redirect({ to: "/" });
      }
    },
    component: AmbassadorTeacherProfile,
  }),
  createRoute({ getParentRoute: pa, path: "/leaderboard", component: AmbassadorLeaderboard }),
  createRoute({ getParentRoute: pa, path: "/profile", component: SharedProfile }),
  createRoute({ getParentRoute: pa, path: "/documents", component: PersonalDocuments }),
  createRoute({ getParentRoute: pa, path: "/id-card", component: ProfileCard }),
  createRoute({ getParentRoute: pa, path: "/materials", component: AmbassadorMaterials }),
  createRoute({ getParentRoute: pa, path: "/teacher-portal", component: AmbassadorTeacherPortal }),
  createRoute({
    getParentRoute: pa,
    path: "/admin",
    beforeLoad: () => {
      const role = localStorage.getItem("active_role");
      if (role !== "admin") {
        throw redirect({ to: "/" });
      }
      throw redirect({ to: "/ambassadors/admin/network" });
    },
  }),
  createRoute({
    getParentRoute: pa,
    path: "/admin/network",
    beforeLoad: () => {
      const role = localStorage.getItem("active_role");
      if (role !== "admin") {
        throw redirect({ to: "/" });
      }
    },
    component: AmbassadorsAdminNetwork,
  }),
  createRoute({
    getParentRoute: pa,
    path: "/admin/tasks",
    beforeLoad: () => {
      const role = localStorage.getItem("active_role");
      if (role !== "admin") {
        throw redirect({ to: "/" });
      }
    },
    component: AmbassadorsAdminTasks,
  }),
  createRoute({
    getParentRoute: pa,
    path: "/admin/leads",
    beforeLoad: () => {
      const role = localStorage.getItem("active_role");
      if (role !== "admin") {
        throw redirect({ to: "/" });
      }
    },
    component: AmbassadorsAdminLeads,
  }),
  createRoute({
    getParentRoute: pa,
    path: "/admin/sessions",
    beforeLoad: () => {
      const role = localStorage.getItem("active_role");
      if (role !== "admin") {
        throw redirect({ to: "/" });
      }
    },
    component: AmbassadorsAdminSessions,
  }),
  createRoute({
    getParentRoute: pa,
    path: "/admin/titles",
    beforeLoad: () => {
      const role = localStorage.getItem("active_role");
      if (role !== "admin") {
        throw redirect({ to: "/" });
      }
    },
    component: AmbassadorsAdminTitles,
  }),
  createRoute({
    getParentRoute: pa,
    path: "/admin/badges",
    beforeLoad: () => {
      const role = localStorage.getItem("active_role");
      if (role !== "admin") {
        throw redirect({ to: "/" });
      }
    },
    component: AmbassadorsAdminBadges,
  }),
  createRoute({
    getParentRoute: pa,
    path: "/admin/settings",
    beforeLoad: () => {
      const role = localStorage.getItem("active_role");
      if (role !== "admin") {
        throw redirect({ to: "/" });
      }
    },
    component: AmbassadorsAdminSettings,
  }),
  createRoute({
    getParentRoute: pa,
    path: "/admin/ambassador/$ambassadorId",
    beforeLoad: () => {
      const role = localStorage.getItem("active_role");
      if (role !== "admin") {
        throw redirect({ to: "/" });
      }
    },
    component: AdminAmbassador,
  }),
];

const instructorsLayoutRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/instructors",
  beforeLoad: () => {
    // No token means bare /instructors (the only path the parent authLayoutRoute
    // lets through unauthenticated) — defer to authLayoutRoute's component, which
    // renders the public InstructorsLanding page directly instead of this subtree.
    if (!tokens.access) return;
    const role = localStorage.getItem("active_role");
    if (role !== "instructor" && role !== "facilitator" && role !== "applicant" && role !== "admin") {
      throw redirect({ to: "/" });
    }
  },
  component: () => <Outlet />,
});

const pi = () => instructorsLayoutRoute;
const instructorsRoutes = [
  createRoute({
    getParentRoute: pi,
    path: "/",
    beforeLoad: () => {
      if (!tokens.access) return; // unreachable render-wise; see instructorsLayoutRoute above
      const role = localStorage.getItem("active_role");
      if (role === "facilitator") {
        throw redirect({ to: "/instructors/facilitator/training" });
      } else if (role === "applicant") {
        throw redirect({ to: "/instructors/status" });
      } else if (role === "admin") {
        throw redirect({ to: "/instructors/admin" });
      } else {
        throw redirect({ to: "/instructors/dashboard" });
      }
    },
  }),
  createRoute({ getParentRoute: pi, path: "/status", component: InstructorStatus }),
  createRoute({ getParentRoute: pi, path: "/videos", component: InstructorVideos }),
  createRoute({ getParentRoute: pi, path: "/modules", component: InstructorModules }),
  createRoute({ getParentRoute: pi, path: "/modules/$moduleId", component: InstructorModuleDetail }),
  createRoute({ getParentRoute: pi, path: "/dashboard", component: InstructorDashboard }),
  createRoute({ getParentRoute: pi, path: "/training", component: InstructorTraining }),
  createRoute({ getParentRoute: pi, path: "/training/player/$videoId", component: InstructorTrainingPlayer }),
  createRoute({ getParentRoute: pi, path: "/library", component: InstructorLibrary }),
  createRoute({ getParentRoute: pi, path: "/documents", component: UserDocuments }),
  createRoute({ getParentRoute: pi, path: "/personal-documents", component: InstructorPersonalDocuments }),
  createRoute({ getParentRoute: pi, path: "/id-card", component: InstructorIdCard }),
  createRoute({ getParentRoute: pi, path: "/profile", component: SharedProfile }),
  createRoute({ getParentRoute: pi, path: "/payments", component: InstructorPayments }),
  createRoute({ getParentRoute: pi, path: "/facilitator/training", component: FacilitatorTraining }),
  createRoute({ getParentRoute: pi, path: "/facilitator/library", component: FacilitatorLibrary }),
  createRoute({ getParentRoute: pi, path: "/facilitator/application", component: FacilitatorApplication }),
  createRoute({ getParentRoute: pi, path: "/available-sessions", component: InstructorAvailableSessions }),
  createRoute({ getParentRoute: pi, path: "/my-sessions", component: InstructorMySessions }),
  createRoute({ getParentRoute: pi, path: "/my-holdings", component: InstructorMyHoldings }),
  createRoute({ getParentRoute: pi, path: "/sessions/$sessionId", component: InstructorSessionDetail }),
  createRoute({ getParentRoute: pi, path: "/game-runs/$runId", component: GameLiveConsole }),
  createRoute({
    getParentRoute: pi,
    path: "/admin",
    beforeLoad: () => {
      throw redirect({ to: "/instructors/admin/overview" });
    },
  }),
  createRoute({ getParentRoute: pi, path: "/admin/overview", component: InstructorsAdminOverview }),
  createRoute({ getParentRoute: pi, path: "/admin/applicants", component: InstructorsAdminApplicants }),
  createRoute({ getParentRoute: pi, path: "/admin/applicants/$userId", component: ApplicantReviewPage }),
  createRoute({ getParentRoute: pi, path: "/admin/invitations", component: InstructorsAdminInvitations }),
  createRoute({ getParentRoute: pi, path: "/admin/instructors", component: InstructorsAdminInstructors }),
  createRoute({ getParentRoute: pi, path: "/admin/facilitators", component: InstructorsAdminFacilitators }),
  createRoute({ getParentRoute: pi, path: "/admin/payments", component: InstructorsAdminPayments }),
  createRoute({ getParentRoute: pi, path: "/admin/certificates", component: InstructorsAdminCertificates }),
];

/**
 * Guard for the flat `/admin/*` routes. Until I0-1 none of them had one at all —
 * any authenticated user (an intern, an applicant) could navigate to
 * `/admin/users` and render the shell; only the backend's 403 stopped them
 * seeing data. Client-side guards are cosmetic by design in this app (they read
 * localStorage, and the backend is the real authorization boundary) — but a
 * redirect beats a page full of failed requests.
 */
const requireAdminRole = () => {
  if (localStorage.getItem("active_role") !== "admin") {
    throw redirect({ to: "/" });
  }
};

const adminHubRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/admin",
  beforeLoad: requireAdminRole,
  component: AdminHub,
});

const adminUsersRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/admin/users",
  beforeLoad: requireAdminRole,
  component: AdminUsers,
});

const adminDocumentsRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/admin/documents",
  beforeLoad: requireAdminRole,
  component: AdminDocuments,
});

const adminSettingsRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/admin/settings",
  beforeLoad: requireAdminRole,
  component: Settings,
});

const adminProfileRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/admin/profile",
  beforeLoad: requireAdminRole,
  component: SharedProfile,
});

const adminApplicationsRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/admin/applications",
  beforeLoad: requireAdminRole,
  component: AdminApplications,
});

/**
 * Legacy `/admin/*` aliases for pages that live in the operations domain.
 * S6-2 created `/operations/*` but left these behind pointing at the same
 * components, so every ops page had two URLs and the `/admin` copy had no role
 * guard. Kept as redirects rather than deleted outright so existing bookmarks
 * and any pasted links still land somewhere useful. Nothing in the app links
 * here any more (verified 2026-07-28).
 *
 * NOTE: `/sessions/calendar` is deliberately NOT in this list — it is the
 * shared calendar for instructors/facilitators (linked from `Sidebar.tsx` and
 * `SessionsSubNav.tsx`, backend guard is any authenticated user). Redirecting
 * it to `/operations/calendar` would bounce every non-ops user to `/`.
 */
const adminProgramsRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/admin/programs",
  beforeLoad: () => {
    throw redirect({ to: "/operations/programs" });
  },
});
const adminCohortsRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/admin/cohorts",
  beforeLoad: () => {
    throw redirect({ to: "/operations/cohorts" });
  },
});
const adminContactsRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/admin/contacts",
  beforeLoad: () => {
    throw redirect({ to: "/operations/contacts" });
  },
});
const adminMergeReviewsRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/admin/merge-reviews",
  beforeLoad: () => {
    throw redirect({ to: "/operations/merge-reviews" });
  },
});
const adminCheckInRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/admin/checkin",
  beforeLoad: () => {
    throw redirect({ to: "/operations/checkin" });
  },
});

/** Shared calendar — instructors/facilitators/ops all read it; the backend
 *  scopes what each of them sees. Distinct from `/operations/calendar`. */
const sessionsCalendarRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/sessions/calendar",
  component: SessionsCalendar,
});

// ── Operations domain (V2 S6-2) — dedicated route tree, separate from admin ──
/** Roles that live in the operations domain. `coo` and `storekeeper` (I1-4)
 *  only reach the inventory pages inside it — the rest 403 at the API, so the
 *  sidebar doesn't offer them (see Sidebar.tsx::getNavItems). */
const OPERATIONS_DOMAIN_ROLES = new Set(["operations", "admin", "coo", "storekeeper"]);

const operationsLayoutRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/operations",
  beforeLoad: () => {
    const role = localStorage.getItem("active_role");
    if (!role || !OPERATIONS_DOMAIN_ROLES.has(role)) {
      throw redirect({ to: "/" });
    }
  },
  component: () => <Outlet />,
});

const po = () => operationsLayoutRoute;
const operationsRoutes = [
  createRoute({ getParentRoute: po, path: "/dashboard", component: OpsDashboard }),
  createRoute({ getParentRoute: po, path: "/this-week", component: ThisWeek }),
  createRoute({ getParentRoute: po, path: "/programs", component: AdminPrograms }),
  createRoute({ getParentRoute: po, path: "/cohorts", component: AdminCohorts }),
  createRoute({ getParentRoute: po, path: "/cohorts/$cohortId", component: AdminCohortDetail }),
  createRoute({ getParentRoute: po, path: "/cohorts/$cohortId/sessions/$sessionId", component: AdminSessionDetail }),
  createRoute({ getParentRoute: po, path: "/game-assignments/$assignmentId", component: SessionGameAssignmentDetail }),
  createRoute({ getParentRoute: po, path: "/contacts", component: AdminContacts }),
  createRoute({ getParentRoute: po, path: "/merge-reviews", component: AdminMergeReviews }),
  createRoute({ getParentRoute: po, path: "/checkin", component: AdminCheckIn }),
  createRoute({ getParentRoute: po, path: "/calendar", component: SessionsCalendar }),
  createRoute({ getParentRoute: po, path: "/profile", component: SharedProfile }),
  // Inventory (I1-4)
  createRoute({ getParentRoute: po, path: "/inventory", component: InventoryKits }),
  createRoute({ getParentRoute: po, path: "/inventory/kits/$kitId", component: InventoryKitDetail }),
  createRoute({ getParentRoute: po, path: "/inventory/locations/$locationId", component: InventoryLocationDetail }),
  createRoute({ getParentRoute: po, path: "/inventory/stock", component: InventoryStock }),
  createRoute({ getParentRoute: po, path: "/inventory/catalog", component: InventoryCatalog }),
  createRoute({ getParentRoute: po, path: "/inventory/fulfilment", component: InventoryFulfilment }),
  createRoute({ getParentRoute: po, path: "/delivery-settings", component: DeliverySettings }),
];

// LMS authoring (LM1-13) — own top-level layout, not nested under /operations
// or /instructors, since backend's require_lms_content allows both operations
// AND facilitator (plus admin) and those two roles land in different portal
// domains. One URL space, gated on activeRole directly.
const lmsAuthoringLayoutRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/lms-authoring",
  beforeLoad: () => {
    const role = localStorage.getItem("active_role");
    if (!role || !["operations", "facilitator", "admin"].includes(role)) {
      throw redirect({ to: "/" });
    }
  },
  component: () => <Outlet />,
});
const pla = () => lmsAuthoringLayoutRoute;
const lmsAuthoringRoutes = [
  createRoute({ getParentRoute: pla, path: "/courses", component: LmsCourses }),
  createRoute({ getParentRoute: pla, path: "/courses/$courseId", component: LmsCourseDetail }),
  createRoute({ getParentRoute: pla, path: "/modules/$moduleId", component: LmsModuleDetail }),
  createRoute({ getParentRoute: pla, path: "/curriculum", component: LmsCurriculum }),
  createRoute({ getParentRoute: pla, path: "/learning-paths", component: LmsLearningPaths }),
  createRoute({ getParentRoute: pla, path: "/learning-paths/$pathId", component: LmsLearningPathDetail }),
  createRoute({ getParentRoute: pla, path: "/progress", component: LmsProgressGrid }),
  createRoute({ getParentRoute: pla, path: "/missions", component: LmsMissions }),
  // Design v2 (7D-7). Its own section, not per-mission admin: the
  // component library has no mission_id and every design mission reads it.
  createRoute({ getParentRoute: pla, path: "/design-library", component: LmsDesignLibrary }),
  createRoute({ getParentRoute: pla, path: "/missions/$missionId", component: LmsMissionDetail }),
  createRoute({
    getParentRoute: pla, path: "/students", component: LmsStudents,
    // ?invite_code=FALL26 — the invite-codes page deep-links into a batch.
    validateSearch: (s: Record<string, unknown>) => ({
      invite_code: typeof s.invite_code === "string" ? s.invite_code : undefined,
    }),
  }),
  createRoute({ getParentRoute: pla, path: "/students/$userId", component: LmsStudentDetail }),
  createRoute({ getParentRoute: pla, path: "/invite-codes", component: LmsInviteCodes }),
  createRoute({ getParentRoute: pla, path: "/games", component: LmsGames }),
  createRoute({ getParentRoute: pla, path: "/games/$gameId", component: LmsGameDetail }),
];

// Apply routes — all use shared ApplyFlow (instructor uses InstructorApply for its own pipeline)
const applyAmbassadorRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/apply/ambassador",
  component: () => <ApplyFlow role="ambassador" />,
});
const applyAmbassadorCodeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/apply/ambassador/$code",
  component: () => {
    const { code } = applyAmbassadorCodeRoute.useParams()
    return <ApplyFlow role="ambassador" prefillCode={code} />
  },
});
const applyInternRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/apply/intern",
  component: () => <ApplyFlow role="intern" />,
});
const applyInternCodeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/apply/intern/$code",
  component: () => {
    const { code } = applyInternCodeRoute.useParams()
    return <ApplyFlow role="intern" prefillCode={code} />
  },
});
const applyTeacherRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/apply/teacher",
  component: () => <ApplyFlow role="teacher" />,
});
const applyTeacherCodeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/apply/teacher/$code",
  component: () => {
    const { code } = applyTeacherCodeRoute.useParams()
    return <ApplyFlow role="teacher" prefillCode={code} />
  },
});
const applyFacilitatorRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/apply/facilitator",
  component: () => <ApplyFlow role="facilitator" />,
});
const applyFacilitatorCodeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/apply/facilitator/$code",
  component: () => {
    const { code } = applyFacilitatorCodeRoute.useParams()
    return <ApplyFlow role="facilitator" prefillCode={code} />
  },
});

const applyInstructorRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/apply/instructor",
  component: InstructorApply,
});
const applyInstructorWithCodeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/apply/instructor/$code",
  component: InstructorApply,
});

// ── Learn layout (LMS D1) — sibling of authLayoutRoute, not a child ─────────
// Students are a separate surface: own beforeLoad, own shell, no portal chrome.
// `/learn/login` and `/learn/signup` are NOT children of this route — they sit
// on rootRoute so the shell (and its auth check) never wraps them, the same way
// `loginRoute` sits outside `authLayoutRoute`.
const learnLayoutRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/learn",
  beforeLoad: () => {
    if (!tokens.access) {
      throw redirect({ to: "/learn/login" });
    }
  },
  component: LearnShell,
});

const learnLoginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/learn/login",
  component: LearnLogin,
});

const learnSignupRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/learn/signup",
  component: LearnSignup,
});

const learnSetPasswordRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/learn/set-password",
  component: LearnSetPassword,
});

const learnLandingRoute = createRoute({
  getParentRoute: () => learnLayoutRoute,
  path: "/",
  component: LearnLanding,
});

const learnCatalogRoute = createRoute({
  getParentRoute: () => learnLayoutRoute,
  path: "/catalog",
  component: LearnCatalog,
});

const learnMyCoursesRoute = createRoute({
  getParentRoute: () => learnLayoutRoute,
  path: "/my-courses",
  component: LearnMyCourses,
});

const learnCourseRoute = createRoute({
  getParentRoute: () => learnLayoutRoute,
  path: "/courses/$courseId",
  component: LearnCourse,
});

// Redesign 1h: one route for the whole course, sidebar swaps the content pane
// (no route change per item) — replaces the old per-module route below.
const learnPlayerRoute = createRoute({
  getParentRoute: () => learnLayoutRoute,
  path: "/courses/$courseId/learn",
  component: LearnPlayer,
});

// Learning paths (self-paced ordered course sequences, 2026-08-08, design 4a).
const learnPathsRoute = createRoute({
  getParentRoute: () => learnLayoutRoute,
  path: "/paths",
  component: LearnPaths,
});

const learnPathRoute = createRoute({
  getParentRoute: () => learnLayoutRoute,
  path: "/paths/$pathId",
  component: LearnPath,
});

// Student profile (design 2a/2b, 2026-08-08).
const learnProfileRoute = createRoute({
  getParentRoute: () => learnLayoutRoute,
  path: "/profile",
  component: LearnProfile,
});

// Upcoming-program detail page (2026-08-08) — replaces UpcomingProgramRow's
// inline expand with a real page (full details, location + map, full
// registration form).
// Missions (Phase 2 Stage 5) — standalone challenges, sibling of the course
// catalog rather than nested under it (own table, own attempt flow).
const learnMissionsRoute = createRoute({
  getParentRoute: () => learnLayoutRoute,
  path: "/missions",
  component: MissionCatalog,
});

const learnMissionRoute = createRoute({
  getParentRoute: () => learnLayoutRoute,
  path: "/missions/$missionId",
  component: MissionPage,
});

// The design-mission wizard (P7-5) — a distinct nine-step surface, not the
// generic attempt-flow page above (a design is iterative, saved freely
// across many steps; a submission/quiz attempt is a single act). Keyed on
// attempt_id, not mission_id: /missions/design/$attemptId.
const learnDesignMissionRoute = createRoute({
  getParentRoute: () => learnLayoutRoute,
  path: "/missions/design/$attemptId",
  component: DesignMissionPage,
});

// The operate-mission console (Stage 7B-4) — same reasoning as design
// above: a bounded live session, not a single quiz/submission-shaped
// attempt form. Keyed on attempt_id.
const learnOperateMissionRoute = createRoute({
  getParentRoute: () => learnLayoutRoute,
  path: "/missions/operate/$attemptId",
  component: OperateMissionPage,
});

// Pre-design briefing (Design v2, 7D-4) — same split as the operate
// briefing below: keyed on mission_id, read before an attempt exists, so
// reading the flight rules never costs a retry.
const learnDesignBriefingRoute = createRoute({
  getParentRoute: () => learnLayoutRoute,
  path: "/missions/design/brief/$missionId",
  component: DesignBriefingPage,
  validateSearch: (search: Record<string, unknown>): { variant?: string; team?: string } => ({
    variant: typeof search.variant === "string" ? search.variant : undefined,
    team: typeof search.team === "string" ? search.team : undefined,
  }),
});

// Pre-flight briefing (Operate v2, Stage 7C-7). Keyed on mission_id, not
// attempt_id, because it is deliberately read *before* an attempt exists —
// a student can re-read the flight rules as often as they like without
// spending a retry. `?variant=` and `?team=` carry the choices made on the
// mission page through to the "Begin flight" call that finally creates one.
const learnOperateBriefingRoute = createRoute({
  getParentRoute: () => learnLayoutRoute,
  path: "/missions/operate/brief/$missionId",
  component: OperateBriefingPage,
  validateSearch: (search: Record<string, unknown>): { variant?: string; team?: string } => ({
    variant: typeof search.variant === "string" ? search.variant : undefined,
    team: typeof search.team === "string" ? search.team : undefined,
  }),
});

const learnProgramRoute = createRoute({
  getParentRoute: () => learnLayoutRoute,
  path: "/programs/$cohortId",
  component: LearnProgram,
});

// Leaderboard (P2-4, linked into the frontend in Live Games Phase 2C 8-2).
const learnLeaderboardRoute = createRoute({
  getParentRoute: () => learnLayoutRoute,
  path: "/leaderboard",
  component: LearnLeaderboard,
});

// Live Quiz (Live Games Phase 2C, 8-8, D5) — own top-level surface.
const learnGamesRoute = createRoute({
  getParentRoute: () => learnLayoutRoute,
  path: "/games",
  component: LearnGames,
});

const learnGamePlayRoute = createRoute({
  getParentRoute: () => learnLayoutRoute,
  path: "/games/$runId",
  component: GamePlay,
});

const routeTree = rootRoute.addChildren([
  ticketRoute,
  kitScanRoute,
  loginRoute,
  learnLoginRoute,
  learnSignupRoute,
  learnSetPasswordRoute,
  learnLayoutRoute.addChildren([
    learnLandingRoute, learnCatalogRoute, learnMyCoursesRoute, learnCourseRoute, learnPlayerRoute,
    learnPathsRoute, learnPathRoute, learnProfileRoute, learnProgramRoute, learnLeaderboardRoute,
    learnGamesRoute, learnGamePlayRoute,
    learnMissionsRoute, learnDesignBriefingRoute, learnDesignMissionRoute, learnOperateBriefingRoute,
    learnOperateMissionRoute, learnMissionRoute,
  ]),
  applyAmbassadorRoute,
  applyAmbassadorCodeRoute,
  applyInternRoute,
  applyInternCodeRoute,
  applyTeacherRoute,
  applyTeacherCodeRoute,
  applyFacilitatorRoute,
  applyFacilitatorCodeRoute,
  applyInstructorRoute,
  applyInstructorWithCodeRoute,
  authLayoutRoute.addChildren([
    indexRoute,
    adminHubRoute,
    adminUsersRoute,
    adminDocumentsRoute,
    adminApplicationsRoute,
    adminSettingsRoute,
    adminProgramsRoute,
    adminCohortsRoute,
    adminContactsRoute,
    adminMergeReviewsRoute,
    adminCheckInRoute,
    sessionsCalendarRoute,
    adminProfileRoute,
    operationsLayoutRoute.addChildren(operationsRoutes),
    lmsAuthoringLayoutRoute.addChildren(lmsAuthoringRoutes),
    internsLayoutRoute.addChildren(internsRoutes),
    ambassadorsLayoutRoute.addChildren(ambassadorsRoutes),
    instructorsLayoutRoute.addChildren(instructorsRoutes),
  ]),
]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

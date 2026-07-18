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

// Shared pages
import SharedProfile from "@/pages/shared/Profile";

// Interns domain pages
import Dashboard from "@/pages/interns/Dashboard";
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

// Admin hub
import AdminHub from "@/pages/admin/Dashboard";
import AdminUsers from "@/pages/admin/Users";
import AdminDocuments from "@/pages/admin/Documents";
import AdminApplications from "@/pages/admin/Applications";
import Settings from "@/pages/admin/Settings";

// Unified apply flow
import ApplyFlow from "@/pages/apply/ApplyFlow";

// Public landing pages (no auth) — shown at bare /instructors and /interns when logged out
import InstructorsLanding from "@/pages/public/InstructorsLanding";
import InternsLanding from "@/pages/public/InternsLanding";

const rootRoute = createRootRoute({ component: () => <Outlet /> });

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  component: Login,
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
    const role = localStorage.getItem("active_role");
    if (role === "admin") {
      throw redirect({ to: "/admin" });
    } else if (role === "ambassador") {
      throw redirect({ to: "/ambassadors" });
    } else if (role === "teacher") {
      throw redirect({ to: "/ambassadors/teacher-portal" });
    } else if (role === "applicant") {
      throw redirect({ to: "/instructors/status" });
    } else if (role === "instructor") {
      throw redirect({ to: "/instructors/dashboard" });
    } else if (role === "facilitator") {
      throw redirect({ to: "/instructors/facilitator/training" });
    } else {
      throw redirect({ to: "/interns" });
    }
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

const adminHubRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/admin",
  component: AdminHub,
});

const adminUsersRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/admin/users",
  component: AdminUsers,
});

const adminDocumentsRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/admin/documents",
  component: AdminDocuments,
});

const adminSettingsRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/admin/settings",
  component: Settings,
});

const adminProfileRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/admin/profile",
  component: SharedProfile,
});

const adminApplicationsRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/admin/applications",
  component: AdminApplications,
});

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

const routeTree = rootRoute.addChildren([
  loginRoute,
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
    adminProfileRoute,
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

import {
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  redirect,
} from "@tanstack/react-router";
import { Navbar } from "@/components/layout/Navbar";
import { Login } from "@/pages/auth/Login";
import { tokens } from "@/api/client";

// Interns domain pages
import Dashboard from "@/pages/interns/Dashboard";
import Tracker from "@/pages/interns/Tracker";
import Calendar from "@/pages/interns/Calendar";
import Leaderboard from "@/pages/interns/Leaderboard";
import Profile from "@/pages/interns/Profile";
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
import AmbassadorProfile from "@/pages/ambassadors/Profile";
import AmbassadorMaterials from "@/pages/ambassadors/Materials";
import AmbassadorTeacherPortal from "@/pages/ambassadors/TeacherPortal";
import AmbassadorApply from "@/pages/ambassadors/AmbassadorApply";
import TeacherApply from "@/pages/ambassadors/TeacherApply";

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
import InstructorDocuments from "@/pages/instructors/Documents";
import InstructorProfileCard from "@/pages/instructors/ProfileCard";
import InstructorPayments from "@/pages/instructors/Payments";
import InstructorsAdmin from "@/pages/instructors/Admin";
import FacilitatorTraining from "@/pages/instructors/facilitator/Training";
import FacilitatorLibrary from "@/pages/instructors/facilitator/Library";

// Admin hub
import AdminHub from "@/pages/admin/Dashboard";

const rootRoute = createRootRoute({ component: () => <Outlet /> });

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  component: Login,
});

import { useAuth } from "@/context/AuthContext";

/** Authenticated shell (PLAN §7 `_auth`): redirect to /login when no token. */
const authLayoutRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: "auth",
  beforeLoad: () => {
    if (!tokens.access) {
      throw redirect({ to: "/login" });
    }
  },
  component: () => {
    const { currentUser, isLoading } = useAuth();

    if (isLoading) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-background text-foreground">
          <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" />
        </div>
      );
    }

    if (!currentUser) {
      return null;
    }

    return (
      <div className="min-h-screen bg-background text-foreground">
        <Navbar />
        <main className="mx-auto max-w-7xl px-4 py-6">
          <Outlet />
        </main>
      </div>
    );
  },
});

const indexRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/",
  beforeLoad: () => {
    const role = localStorage.getItem("active_role");
    if (role === "ambassador") {
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
  component: () => <Outlet />,
});

const p = () => internsLayoutRoute;
const internsRoutes = [
  createRoute({ getParentRoute: p, path: "/", component: Dashboard }),
  createRoute({ getParentRoute: p, path: "/tracker", component: Tracker }),
  createRoute({ getParentRoute: p, path: "/calendar", component: Calendar }),
  createRoute({ getParentRoute: p, path: "/leaderboard", component: Leaderboard }),
  createRoute({ getParentRoute: p, path: "/profile", component: Profile }),
  createRoute({ getParentRoute: p, path: "/admin", component: Admin }),
  createRoute({ getParentRoute: p, path: "/mind-map/$epicId", component: MindMap }),
  createRoute({ getParentRoute: p, path: "/mind-map/project/$projectId", component: ProjectMindMap }),
];

const ambassadorsLayoutRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/ambassadors",
  component: () => <Outlet />,
});

const pa = () => ambassadorsLayoutRoute;
const ambassadorsRoutes = [
  createRoute({ getParentRoute: pa, path: "/", component: AmbassadorDashboard }),
  createRoute({ getParentRoute: pa, path: "/leads", component: AmbassadorLeads }),
  createRoute({ getParentRoute: pa, path: "/tasks", component: AmbassadorTasks }),
  createRoute({ getParentRoute: pa, path: "/network", component: AmbassadorNetwork }),
  createRoute({ getParentRoute: pa, path: "/network/teacher/$teacherId", component: AmbassadorTeacherProfile }),
  createRoute({ getParentRoute: pa, path: "/leaderboard", component: AmbassadorLeaderboard }),
  createRoute({ getParentRoute: pa, path: "/profile", component: AmbassadorProfile }),
  createRoute({ getParentRoute: pa, path: "/materials", component: AmbassadorMaterials }),
  createRoute({ getParentRoute: pa, path: "/teacher-portal", component: AmbassadorTeacherPortal }),
];

const instructorsLayoutRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/instructors",
  component: () => <Outlet />,
});

const pi = () => instructorsLayoutRoute;
const instructorsRoutes = [
  createRoute({ getParentRoute: pi, path: "/status", component: InstructorStatus }),
  createRoute({ getParentRoute: pi, path: "/videos", component: InstructorVideos }),
  createRoute({ getParentRoute: pi, path: "/modules", component: InstructorModules }),
  createRoute({ getParentRoute: pi, path: "/modules/$moduleId", component: InstructorModuleDetail }),
  createRoute({ getParentRoute: pi, path: "/dashboard", component: InstructorDashboard }),
  createRoute({ getParentRoute: pi, path: "/training", component: InstructorTraining }),
  createRoute({ getParentRoute: pi, path: "/training/player/$videoId", component: InstructorTrainingPlayer }),
  createRoute({ getParentRoute: pi, path: "/library", component: InstructorLibrary }),
  createRoute({ getParentRoute: pi, path: "/documents", component: InstructorDocuments }),
  createRoute({ getParentRoute: pi, path: "/profile-card", component: InstructorProfileCard }),
  createRoute({ getParentRoute: pi, path: "/payments", component: InstructorPayments }),
  createRoute({ getParentRoute: pi, path: "/facilitator/training", component: FacilitatorTraining }),
  createRoute({ getParentRoute: pi, path: "/facilitator/library", component: FacilitatorLibrary }),
  createRoute({ getParentRoute: pi, path: "/admin", component: InstructorsAdmin }),
];

const adminHubRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/admin",
  component: AdminHub,
});

const applyAmbassadorRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/apply/ambassador",
  component: AmbassadorApply,
});

const applyTeacherRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/apply/teacher/$code",
  component: TeacherApply,
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
  applyTeacherRoute,
  applyInstructorRoute,
  applyInstructorWithCodeRoute,
  authLayoutRoute.addChildren([
    indexRoute,
    adminHubRoute,
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

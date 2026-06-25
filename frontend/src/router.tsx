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

const routeTree = rootRoute.addChildren([
  loginRoute,
  applyAmbassadorRoute,
  applyTeacherRoute,
  authLayoutRoute.addChildren([
    indexRoute,
    internsLayoutRoute.addChildren(internsRoutes),
    ambassadorsLayoutRoute.addChildren(ambassadorsRoutes),
  ]),
]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

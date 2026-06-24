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

const rootRoute = createRootRoute({ component: () => <Outlet /> });

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  component: Login,
});

/** Authenticated shell (PLAN §7 `_auth`): redirect to /login when no token. */
const authLayoutRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: "auth",
  beforeLoad: () => {
    if (!tokens.access) {
      throw redirect({ to: "/login" });
    }
  },
  component: () => (
    <div className="min-h-screen bg-background text-foreground">
      <Navbar />
      <main className="mx-auto max-w-7xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  ),
});

const indexRoute = createRoute({
  getParentRoute: () => authLayoutRoute,
  path: "/",
  beforeLoad: () => {
    // Only the interns domain exists so far — route everyone there.
    throw redirect({ to: "/interns" });
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

const routeTree = rootRoute.addChildren([
  loginRoute,
  authLayoutRoute.addChildren([
    indexRoute,
    internsLayoutRoute.addChildren(internsRoutes),
  ]),
]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

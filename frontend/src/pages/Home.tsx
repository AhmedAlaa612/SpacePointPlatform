import { useAuth } from "@/context/AuthContext";
import { ROLE_LABEL } from "@/types/shared";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function Home() {
  const { user, activeRole, roles } = useAuth();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Welcome back, {user?.full_name}</h1>
        <p className="text-muted-foreground">
          Active role:{" "}
          <span className="font-medium text-foreground">
            {activeRole ? ROLE_LABEL[activeRole] : "—"}
          </span>
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Your roles</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex flex-wrap gap-2">
            {roles.length > 0 ? (
              roles.map((r) => (
                <span
                  key={r}
                  className="rounded-full border border-border bg-muted px-3 py-1 text-sm text-foreground"
                >
                  {ROLE_LABEL[r]}
                </span>
              ))
            ) : (
              <span className="text-sm text-muted-foreground">No roles assigned.</span>
            )}
          </div>
          <p className="pt-2 text-sm text-muted-foreground">
            Domain dashboards (interns, ambassadors, instructors, admin) are built out in Phases 1–5 — see
            PLAN.md §12.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

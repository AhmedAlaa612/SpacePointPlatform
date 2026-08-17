import { useCallback, useMemo, useState } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { setPassword } from "@/api/auth";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { DomainIcon } from "@/components/ui/DomainIcon";

/**
 * The "invite sent" link an ops-created account follows (LM1-7 / §8 Q5,
 * generalized 2026-08-17 for the bulk-instructor-import welcome email).
 * Token-authenticated (`?token=...` in the query string) — no login needed,
 * since the whole point is the account doesn't have a working password yet.
 * On success, sends them to login rather than auto-logging in: the token
 * proved the email link was theirs, not that they know a password. Mounted
 * at both /learn/set-password (LMS students) and /set-password (every other
 * role) — same component, the login redirect just follows whichever path
 * got it here rather than being hardcoded to the LMS one.
 */
export default function LearnSetPassword() {
  const navigate = useNavigate();
  const loginPath = window.location.pathname.startsWith("/learn") ? "/learn/login" : "/login";
  const token = useMemo(() => new URLSearchParams(window.location.search).get("token") ?? "", []);
  const [password, setPasswordValue] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      setError("");
      if (!token) {
        setError("This link is missing its token.");
        return;
      }
      if (password !== confirm) {
        setError("Passwords don't match.");
        return;
      }
      setLoading(true);
      try {
        await setPassword(token, password);
        setDone(true);
      } catch {
        setError("This link is invalid or has expired. Ask ops to resend it.");
      } finally {
        setLoading(false);
      }
    },
    [token, password, confirm],
  );

  return (
    <div className="min-h-screen bg-background text-foreground flex items-center justify-center px-4 bg-[radial-gradient(circle_at_15%_10%,hsl(var(--primary)/0.06)_0%,transparent_45%)]">
      <div className="w-full max-w-sm">
        <div className="flex justify-center mb-8">
          <DomainIcon className="h-10 w-auto" />
        </div>

        <Card className="p-6 sm:p-7">
          {done ? (
            <div className="text-center">
              <h1 className="font-display text-xl font-bold mb-3">Password set</h1>
              <p className="text-sm text-muted-foreground mb-6">
                You're all set. Log in with your new password to continue.
              </p>
              <Button size="xl" className="w-full" onClick={() => void navigate({ to: loginPath })}>
                Go to login
              </Button>
            </div>
          ) : (
            <>
              <h1 className="text-center font-display text-xl font-bold mb-6">Set your password</h1>
              {error && (
                <div className="mb-4 p-3 rounded-xl bg-destructive/10 text-destructive text-sm text-center">
                  {error}
                </div>
              )}
              <form onSubmit={(e) => void handleSubmit(e)} className="flex flex-col gap-3">
                <input
                  type="password"
                  placeholder="New password"
                  required
                  value={password}
                  onChange={(e) => setPasswordValue(e.target.value)}
                  className="h-11 px-4 rounded-xl text-sm bg-background ring-1 ring-border focus:outline-none focus:ring-primary/50 transition-shadow"
                />
                <input
                  type="password"
                  placeholder="Confirm password"
                  required
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  className="h-11 px-4 rounded-xl text-sm bg-background ring-1 ring-border focus:outline-none focus:ring-primary/50 transition-shadow"
                />
                <Button size="xl" type="submit" disabled={loading} className="w-full mt-1">
                  {loading ? "Setting..." : "Set password"}
                </Button>
              </form>
            </>
          )}
        </Card>

        {!done && (
          <p className="mt-5 text-center text-sm text-muted-foreground">
            <Link to={loginPath} className="text-primary font-medium">
              Back to login
            </Link>
          </p>
        )}
      </div>
    </div>
  );
}

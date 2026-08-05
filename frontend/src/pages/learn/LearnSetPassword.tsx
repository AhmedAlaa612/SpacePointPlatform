import { useCallback, useMemo, useState } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { GraduationCap } from "lucide-react";
import { setPassword } from "@/api/auth";

/**
 * The "invite sent" link an ops-created LMS account follows (LM1-7 / §8 Q5).
 * Token-authenticated (`?token=...` in the query string) — no login needed,
 * since the whole point is the account doesn't have a working password yet.
 * On success, sends them to /learn/login rather than auto-logging in: the
 * token proved the email link was theirs, not that they know a password.
 */
export default function LearnSetPassword() {
  const navigate = useNavigate();
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
    <div className="min-h-screen bg-background text-foreground flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="flex items-center justify-center gap-2 mb-8">
          <GraduationCap size={28} className="text-primary" />
          <span className="text-xl font-semibold">Learn</span>
        </div>

        {done ? (
          <div className="text-center">
            <h1 className="text-lg font-medium mb-3">Password set</h1>
            <p className="text-sm text-muted-foreground mb-6">
              You're all set. Log in with your new password to continue.
            </p>
            <button
              onClick={() => void navigate({ to: "/learn/login" })}
              className="h-11 px-6 bg-primary text-primary-foreground rounded-xl font-medium text-sm cursor-pointer"
            >
              Go to login
            </button>
          </div>
        ) : (
          <>
            <h1 className="text-center text-lg font-medium mb-6">Set your password</h1>
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
                className="h-11 px-4 border border-border bg-card rounded-xl text-sm"
              />
              <input
                type="password"
                placeholder="Confirm password"
                required
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                className="h-11 px-4 border border-border bg-card rounded-xl text-sm"
              />
              <button
                type="submit"
                disabled={loading}
                className="h-11 bg-primary text-primary-foreground rounded-xl font-medium text-sm disabled:opacity-50 cursor-pointer"
              >
                {loading ? "Setting..." : "Set password"}
              </button>
            </form>
            <p className="mt-4 text-center text-sm text-muted-foreground">
              <Link to="/learn/login" className="text-primary font-medium">
                Back to login
              </Link>
            </p>
          </>
        )}
      </div>
    </div>
  );
}

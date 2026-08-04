import { useCallback, useState } from "react";
import { useNavigate, Link } from "@tanstack/react-router";
import { useAuth } from "@/context/AuthContext";
import { GraduationCap } from "lucide-react";

/**
 * Student login — mounted on rootRoute, outside the portal auth shell (the
 * `ticketRoute` precedent, router.tsx:123). Students use `/auth/login` like
 * everyone else; this page just wraps it in the student-facing chrome.
 *
 * Duplicate email after a failed login attempt is surfaced as a link to
 * `/learn/signup` — the friendly-409 message from the plan (LM1-4).
 */
export default function LearnLogin() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      setError("");
      setLoading(true);
      try {
        await login(email, password);
        void navigate({ to: "/learn" });
      } catch {
        setError("Invalid email or password.");
      } finally {
        setLoading(false);
      }
    },
    [email, password, login, navigate],
  );

  return (
    <div className="min-h-screen bg-background text-foreground flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="flex items-center justify-center gap-2 mb-8">
          <GraduationCap size={28} className="text-primary" />
          <span className="text-xl font-semibold">Learn</span>
        </div>

        <h1 className="text-center text-lg font-medium mb-6">Log in</h1>

        {error && (
          <div className="mb-4 p-3 rounded-xl bg-destructive/10 text-destructive text-sm text-center">
            {error}
          </div>
        )}

        <form onSubmit={(e) => void handleSubmit(e)} className="flex flex-col gap-3">
          <input
            type="email"
            placeholder="Email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="h-11 px-4 border border-border bg-card rounded-xl text-sm"
          />
          <input
            type="password"
            placeholder="Password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="h-11 px-4 border border-border bg-card rounded-xl text-sm"
          />
          <button
            type="submit"
            disabled={loading}
            className="h-11 bg-primary text-primary-foreground rounded-xl font-medium text-sm disabled:opacity-50 cursor-pointer"
          >
            {loading ? "Logging in..." : "Log in"}
          </button>
        </form>

        <p className="mt-4 text-center text-sm text-muted-foreground">
          Don't have an account?{" "}
          <Link to="/learn/signup" className="text-primary font-medium">
            Sign up
          </Link>
        </p>
      </div>
    </div>
  );
}

import { useCallback, useState } from "react";
import { useNavigate, Link, useSearch } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { Ticket } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { fetchMe } from "@/api/auth";
import { redeemInviteCodeApi } from "@/api/lms";
import { FinWidget } from "@/components/FinWidget";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { DomainIcon } from "@/components/ui/DomainIcon";
import { PasswordInput } from "@/components/ui/PasswordInput";
import { getErrorMessage } from "@/lib/utils";
import { resolveLearnLanding } from "./resolveLearnLanding";

/**
 * Student login — mounted on rootRoute, outside the portal auth shell (the
 * `ticketRoute` precedent, router.tsx:123). Students use `/auth/login` like
 * everyone else; this page just wraps it in the student-facing chrome.
 *
 * Duplicate email after a failed login attempt is surfaced as a link to
 * `/learn/signup` — the friendly-409 message from the plan (LM1-4).
 */
export default function LearnLogin() {
  const { login, setCurrentUser } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const search = useSearch({ strict: false }) as { invite?: string; code?: string };
  const inviteParam = (search.invite ?? search.code ?? "").trim().toUpperCase();

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
        if (inviteParam) {
          try {
            const res = await redeemInviteCodeApi(inviteParam);
            await queryClient.invalidateQueries({ queryKey: ["lms-my-checklists"] });
            await queryClient.invalidateQueries({ queryKey: ["lms-my-courses"] });
            await queryClient.invalidateQueries({ queryKey: ["me"] });
            const updated = await fetchMe();
            setCurrentUser(updated);
            void navigate({ to: (res.redirect_to || "/learn/checklists") as never });
            return;
          } catch {
            // If redemption fails, proceed to normal landing
          }
        }
        void navigate({ to: await resolveLearnLanding() });
      } catch (err) {
        setError(getErrorMessage(err, "Invalid email or password."));
      } finally {
        setLoading(false);
      }
    },
    [email, password, login, inviteParam, queryClient, setCurrentUser, navigate],
  );

  return (
    <div className="min-h-screen bg-background dark:bg-[#05030A] text-foreground flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm">
        <div className="flex justify-center mb-8">
          <DomainIcon className="h-10 w-auto" />
        </div>

        <div className="lms-card p-6 sm:p-8 rounded-2xl shadow-2xl">
          <h1 className="text-center font-['Outfit'] text-2xl font-bold mb-6 text-foreground">Log in</h1>

          {inviteParam && (
            <div className="mb-4 p-3 rounded-xl bg-lms-cta-light dark:bg-lms-accent-light border border-lms-cta-border dark:border-lms-accent-border text-lms-cta dark:text-lms-accent text-xs font-medium flex items-center justify-center gap-1.5 text-center">
              <Ticket className="size-3.5 shrink-0" />
              <span>
                Log in to redeem invite code <span className="font-mono font-bold">{inviteParam}</span>
              </span>
            </div>
          )}

          {error && (
            <div className="mb-4 p-3 rounded-xl bg-destructive/10 border border-destructive/20 text-destructive text-sm text-center">
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
              className="lms-input h-11 px-4 text-sm w-full"
            />
            <PasswordInput
              placeholder="Password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="lms-input h-11 px-4 text-sm w-full"
            />
            <div className="text-right -mt-1">
              <Link to="/learn/forgot-password" className="text-xs text-muted-foreground hover:text-lms-cta dark:hover:text-lms-accent transition-colors">
                Forgot password?
              </Link>
            </div>
            <button
              type="submit"
              disabled={loading}
              className="lms-btn-primary w-full h-11 text-sm font-bold rounded-xl mt-1 flex items-center justify-center cursor-pointer disabled:opacity-50"
            >
              {loading ? "Logging in..." : "Log in"}
            </button>
          </form>
        </div>

        <p className="mt-5 text-center text-sm text-muted-foreground">
          Don't have an account?{" "}
          <Link
            to="/learn/signup"
            search={inviteParam ? { invite: inviteParam } : undefined}
            className="lms-link"
          >
            Sign up
          </Link>
        </p>
      </div>
      <FinWidget />
    </div>
  );
}

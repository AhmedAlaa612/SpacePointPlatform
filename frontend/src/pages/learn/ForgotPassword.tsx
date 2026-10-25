import { useCallback, useState } from "react";
import { Link } from "@tanstack/react-router";
import { forgotPassword } from "@/api/auth";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { DomainIcon } from "@/components/ui/DomainIcon";
import { getErrorMessage } from "@/lib/utils";

/**
 * Self-service "Forgot password?" — reached from both /login (portal) and
 * /learn/login (LMS students), mounted at /forgot-password and
 * /learn/forgot-password respectively (same dual-mount precedent as
 * LearnSetPassword, whose reset link this feeds: /auth/forgot-password mints
 * the same 24h password_set token and emails the same link that page reads).
 *
 * The confirmation message never reveals whether the email is registered —
 * it mirrors the backend's own generic response so this page can't be used
 * to enumerate accounts either.
 */
export default function ForgotPassword() {
  const loginPath = window.location.pathname.startsWith("/learn") ? "/learn/login" : "/login";
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      setError("");
      setLoading(true);
      try {
        await forgotPassword(email);
        setDone(true);
      } catch (err) {
        setError(getErrorMessage(err, "Something went wrong. Please try again."));
      } finally {
        setLoading(false);
      }
    },
    [email],
  );

  return (
    <div className="min-h-screen bg-background dark:bg-[#05030A] text-foreground flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm">
        <div className="flex justify-center mb-8">
          <DomainIcon className="h-10 w-auto" />
        </div>

        <div className="lms-card p-6 sm:p-8 rounded-2xl shadow-2xl">
          {done ? (
            <div className="text-center">
              <h1 className="font-['Outfit'] text-2xl font-bold mb-3 text-foreground">Check your email</h1>
              <p className="text-sm text-muted-foreground mb-6 text-balance leading-relaxed">
                If an account exists for <span className="font-semibold text-foreground">{email}</span>, we've sent a
                link to reset your password. It's valid for 24 hours.
              </p>
              <Link
                to={loginPath}
                className="lms-btn-primary w-full h-11 text-sm font-bold rounded-xl flex items-center justify-center cursor-pointer"
              >
                Back to login
              </Link>
            </div>
          ) : (
            <>
              <h1 className="text-center font-['Outfit'] text-2xl font-bold mb-2 text-foreground">Forgot your password?</h1>
              <p className="text-center text-sm text-muted-foreground mb-6 text-balance leading-relaxed">
                Enter your email to receive a reset link.
              </p>
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
                <button
                  type="submit"
                  disabled={loading}
                  className="lms-btn-primary w-full h-11 text-sm font-bold rounded-xl mt-1 flex items-center justify-center cursor-pointer disabled:opacity-50"
                >
                  {loading ? "Sending..." : "Send reset link"}
                </button>
              </form>
            </>
          )}
        </div>

        {!done && (
          <p className="mt-5 text-center text-sm text-muted-foreground">
            <Link to={loginPath} className="lms-link">
              Back to login
            </Link>
          </p>
        )}
      </div>
    </div>
  );
}

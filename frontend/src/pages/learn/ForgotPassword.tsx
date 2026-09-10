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
    <div className="min-h-screen bg-background text-foreground flex items-center justify-center px-4 bg-[radial-gradient(circle_at_15%_10%,hsl(var(--primary)/0.06)_0%,transparent_45%)]">
      <div className="w-full max-w-sm">
        <div className="flex justify-center mb-8">
          <DomainIcon className="h-10 w-auto" />
        </div>

        <Card className="p-6 sm:p-7">
          {done ? (
            <div className="text-center">
              <h1 className="font-display text-xl font-bold mb-3">Check your email</h1>
              <p className="text-sm text-muted-foreground mb-6">
                If an account exists for <span className="font-medium">{email}</span>, we've sent a
                link to reset your password. It's valid for 24 hours.
              </p>
              <Button size="xl" className="w-full" asChild>
                <Link to={loginPath}>Back to login</Link>
              </Button>
            </div>
          ) : (
            <>
              <h1 className="text-center font-display text-xl font-bold mb-2">Forgot your password?</h1>
              <p className="text-center text-sm text-muted-foreground mb-6">
                Enter your email and we'll send you a link to reset it.
              </p>
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
                  className="h-11 px-4 rounded-xl text-sm bg-background ring-1 ring-border focus:outline-none focus:ring-primary/50 transition-shadow"
                />
                <Button size="xl" type="submit" disabled={loading} className="w-full mt-1">
                  {loading ? "Sending..." : "Send reset link"}
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

import { useEffect, useState } from "react";
import { useParams, useNavigate } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import { useAuth } from "@/context/AuthContext";
import { fetchMe } from "@/api/auth";
import { redeemInviteCodeApi } from "@/api/lms";
import { api } from "@/api/client";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/primitives";
import { DomainIcon } from "@/components/ui/DomainIcon";

export default function LearnInviteLink() {
  const { code: rawCode } = useParams({ strict: false }) as { code?: string };
  const code = (rawCode || "").trim().toUpperCase();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user, loading, setCurrentUser } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [redeeming, setRedeeming] = useState(false);

  useEffect(() => {
    if (loading) return;

    if (!code) {
      void navigate({ to: "/learn/checklists", replace: true });
      return;
    }

    if (!user) {
      // Validate code first to ensure it's not expired before sending to signup
      let cancelled = false;
      async function validateAndRedirect() {
        try {
          await api.get(`/auth/invite/${code}?kind=student`);
          if (cancelled) return;
          void navigate({
            to: "/learn/signup",
            search: { invite: code } as never,
            replace: true,
          });
        } catch (err) {
          if (cancelled) return;
          if (isAxiosError(err)) {
            const detail = err.response?.data?.detail;
            setError(typeof detail === "string" ? detail : "This invite link is invalid or has expired.");
          } else {
            setError("This invite link is invalid or has expired.");
          }
        }
      }
      void validateAndRedirect();
      return () => {
        cancelled = true;
      };
    }

    // Logged in -> redeem code immediately
    let cancelled = false;
    async function redeem() {
      setRedeeming(true);
      setError(null);
      try {
        const res = await redeemInviteCodeApi(code);
        if (cancelled) return;

        // Invalidate LMS cache so newly unlocked programs/courses show up
        await queryClient.invalidateQueries({ queryKey: ["lms-my-checklists"] });
        await queryClient.invalidateQueries({ queryKey: ["lms-my-courses"] });
        await queryClient.invalidateQueries({ queryKey: ["me"] });

        // Refresh me to update roles (e.g. observer)
        const updatedMe = await fetchMe();
        if (cancelled) return;
        setCurrentUser(updatedMe);

        void navigate({ to: (res.redirect_to || "/learn/checklists") as never, replace: true });
      } catch (err) {
        if (cancelled) return;
        if (isAxiosError(err)) {
          const detail = err.response?.data?.detail;
          setError(typeof detail === "string" ? detail : "Unable to redeem this invite code.");
        } else {
          setError("Unable to redeem this invite code.");
        }
      } finally {
        if (!cancelled) {
          setRedeeming(false);
        }
      }
    }

    void redeem();

    return () => {
      cancelled = true;
    };
  }, [code, user, loading, navigate, queryClient, setCurrentUser]);

  return (
    <div className="min-h-screen bg-background dark:bg-[#05030A] text-foreground flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm flex flex-col items-center">
        <div className="flex justify-center mb-8">
          <DomainIcon className="h-10 w-auto" />
        </div>

        <div className="lms-card p-6 sm:p-8 rounded-2xl shadow-2xl w-full text-center">
          {error ? (
            <div className="flex flex-col gap-4">
              <div className="p-3.5 rounded-xl bg-destructive/10 border border-destructive/20 text-destructive text-sm font-medium">
                {error}
              </div>
              <p className="text-xs text-muted-foreground">
                Code <span className="font-mono font-semibold text-foreground">{code}</span> could not be redeemed.
              </p>
              <button
                type="button"
                className="lms-btn-primary w-full h-11 text-sm font-bold rounded-xl mt-2 flex items-center justify-center cursor-pointer"
                onClick={() => void navigate({ to: (user ? "/learn/checklists" : "/learn/login") as never, replace: true })}
              >
                {user ? "Go to Programs" : "Go to Login"}
              </button>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-3 py-4">
              <Spinner className="size-8 text-lms-cta dark:text-lms-accent" />
              <p className="text-sm font-medium text-muted-foreground">
                {redeeming ? `Redeeming invite code ${code}...` : "Loading invite..."}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

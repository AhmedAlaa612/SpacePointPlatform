import { useEffect, useState } from "react";
import { useParams, useNavigate } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import { useAuth } from "@/context/AuthContext";
import { fetchMe } from "@/api/auth";
import { redeemInviteCodeApi } from "@/api/lms";
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
      // Logged out -> redirect to signup with pre-filled code
      void navigate({
        to: "/learn/signup",
        search: { invite: code } as never,
        replace: true,
      });
      return;
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
    <div className="min-h-screen bg-background text-foreground flex items-center justify-center px-4 bg-[radial-gradient(circle_at_15%_10%,hsl(var(--primary)/0.06)_0%,transparent_45%)]">
      <div className="w-full max-w-sm flex flex-col items-center">
        <div className="flex justify-center mb-8">
          <DomainIcon className="h-10 w-auto" />
        </div>

        <Card className="p-6 sm:p-7 w-full text-center">
          {error ? (
            <div className="flex flex-col gap-4">
              <div className="p-3.5 rounded-xl bg-destructive/10 text-destructive text-sm font-medium">
                {error}
              </div>
              <p className="text-xs text-muted-foreground">
                Code <span className="font-mono font-semibold text-foreground">{code}</span> could not be redeemed.
              </p>
              <Button
                variant="outline"
                className="w-full mt-2"
                onClick={() => void navigate({ to: "/learn/checklists", replace: true })}
              >
                Go to Programs
              </Button>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-3 py-4">
              <Spinner className="size-8 text-primary" />
              <p className="text-sm font-medium text-muted-foreground">
                {redeeming ? `Redeeming invite code ${code}...` : "Loading invite..."}
              </p>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

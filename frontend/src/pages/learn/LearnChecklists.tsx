import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, ClipboardCheck, Trophy, Ticket } from "lucide-react";
import { isAxiosError } from "axios";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { fetchMyChecklists, redeemInviteCodeApi } from "@/api/lms";
import { fetchMe } from "@/api/auth";
import { useAuth } from "@/context/AuthContext";
import { cn } from "@/lib/utils";
import { RedeemInviteModal } from "./components/RedeemInviteModal";

/** /learn/checklists — the LMS Program redesign (2026-08-21): every
 * checklist a student has been assigned, auto-populated at registration
 * time. Distinct from /learn/programs/$cohortId (LearnProgram.tsx, the
 * public catalog's program detail/registration page) and from
 * /learn/my-programs (the older, still-live courses-only cohort view) —
 * this is the new mixed-item-type checklist entity.
 */
export default function LearnChecklists() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { setCurrentUser } = useAuth();
  const { data: checklists, isLoading } = useQuery({ queryKey: ["lms-my-checklists"], queryFn: fetchMyChecklists });

  const [redeemModalOpen, setRedeemModalOpen] = useState(false);
  const [inlineCode, setInlineCode] = useState("");
  const [inlineLoading, setInlineLoading] = useState(false);
  const [inlineError, setInlineError] = useState<string | null>(null);

  const handleInlineRedeem = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = inlineCode.trim().toUpperCase();
    if (!trimmed) return;
    setInlineLoading(true);
    setInlineError(null);
    try {
      const res = await redeemInviteCodeApi(trimmed);
      try {
        const me = await fetchMe();
        setCurrentUser(me);
      } catch {
        // ignore
      }
      await queryClient.invalidateQueries({ queryKey: ["lms-my-checklists"] });
      await queryClient.invalidateQueries({ queryKey: ["lms-my-programs"] });
      await queryClient.invalidateQueries({ queryKey: ["auth-me"] });
      setInlineCode("");
      if (res.redirect_to) {
        void navigate({ to: res.redirect_to as never });
      }
    } catch (err: unknown) {
      if (isAxiosError(err) && typeof err.response?.data?.detail === "string") {
        setInlineError(err.response.data.detail);
      } else {
        setInlineError("Could not redeem invite code. Please check and try again.");
      }
    } finally {
      setInlineLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-[1320px] px-5 sm:px-8 lg:px-14 py-8 sm:py-10 flex flex-col gap-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl sm:text-3xl font-bold tracking-tight">Programs</h1>
          <p className="text-sm text-muted-foreground mt-1.5">
            Every checklist your instructors and ops have assigned you — courses, mission runs, submissions, and manual steps, all in one place.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="self-start sm:self-auto gap-2 shrink-0 cursor-pointer"
          onClick={() => setRedeemModalOpen(true)}
        >
          <Ticket className="size-4" />
          Redeem code
        </Button>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Loading...</p>}
      {checklists && checklists.length === 0 && (
        <div className="flex flex-col items-center justify-center text-center py-12 px-4 gap-4 border border-dashed border-border rounded-2xl bg-card/40">
          <div>
            <p className="text-base font-semibold">No programs assigned yet</p>
            <p className="text-sm text-muted-foreground mt-1 max-w-sm">
              Have an invite code from your school, company, or event? Enter it below to unlock your program checklist.
            </p>
          </div>
          <form onSubmit={handleInlineRedeem} className="flex flex-col sm:flex-row items-center gap-2 w-full max-w-sm">
            <input
              type="text"
              value={inlineCode}
              onChange={(e) => {
                setInlineCode(e.target.value);
                if (inlineError) setInlineError(null);
              }}
              placeholder="e.g. UAE-2026-SCHOOL"
              className="flex-1 w-full uppercase font-mono tracking-wider text-sm rounded-lg border border-input bg-background px-3 py-2 shadow-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
            />
            <Button type="submit" disabled={inlineLoading || !inlineCode.trim()} className="w-full sm:w-auto shrink-0">
              {inlineLoading ? "Redeeming..." : "Redeem code"}
            </Button>
          </form>
          {inlineError && <p className="text-xs text-destructive">{inlineError}</p>}
        </div>
      )}

      <RedeemInviteModal
        open={redeemModalOpen}
        onOpenChange={setRedeemModalOpen}
        onSuccess={(result) => {
          void queryClient.invalidateQueries({ queryKey: ["lms-my-checklists"] });
          if (result.redirect_to) {
            void navigate({ to: result.redirect_to as never });
          }
        }}
      />

      <div className="flex flex-col gap-4 max-w-2xl">
        {checklists?.map((c) => (
          <Card
            key={c.assignment_id}
            className="cursor-pointer hover:ring-primary/30 transition-shadow p-5 flex flex-col gap-4"
            onClick={() => void navigate({ to: `/learn/checklists/${c.assignment_id}` })}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="font-display text-lg font-semibold leading-snug">
                  {c.name}
                </div>
                {c.program_name && (
                  <div className="text-xs text-muted-foreground mt-0.5">
                    {c.program_name}
                  </div>
                )}
              </div>
              <span
                className={cn(
                  "shrink-0 text-[10px] font-bold uppercase tracking-wide rounded-md px-2 py-1",
                  c.pct === 100 ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                    : c.items_done > 0 ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground",
                )}
              >
                {c.pct === 100 ? "Complete" : c.items_done > 0 ? "In progress" : "Not started"}
              </span>
            </div>

            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>{c.items_done} of {c.items_total} steps</span>
                <span>{c.pct}%</span>
              </div>
              <div className="h-1.5 rounded-full bg-muted relative overflow-hidden">
                <div
                  className={cn("absolute inset-y-0 left-0 rounded-full", c.pct === 100 ? "bg-emerald-500" : "bg-primary")}
                  style={{ width: `${c.pct}%` }}
                />
              </div>
            </div>

            <div className="flex items-center justify-between pt-3 border-t border-border">
              {c.pct === 100 ? (
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Trophy className="size-3.5" />
                  {c.certificate_earned ? "Certificate earned" : c.certificate_required ? "Awaiting certificate" : "All done"}
                </div>
              ) : (
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground min-w-0">
                  <ClipboardCheck className="size-3.5 shrink-0" />
                  <span className="truncate">Next: <span className="text-foreground font-medium">{c.next_item_title}</span></span>
                </div>
              )}
              <span className="shrink-0 text-sm font-semibold text-primary flex items-center gap-1">
                {c.items_done > 0 ? "Continue" : "Start"}
                <ChevronRight className="size-4" />
              </span>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}

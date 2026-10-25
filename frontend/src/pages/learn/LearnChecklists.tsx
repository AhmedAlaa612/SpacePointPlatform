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
    <div className="mx-auto max-w-[1320px] px-5 sm:px-8 lg:px-14 py-8 sm:py-10 flex flex-col gap-8">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="font-['Outfit'] text-3xl sm:text-4xl font-extrabold tracking-tight text-foreground">Program Checklists</h1>
          <p className="text-sm sm:text-base text-muted-foreground mt-1.5 max-w-2xl leading-relaxed">
            Every checklist your instructors and ops have assigned you — courses, mission runs, submissions, and manual steps, all in one place.
          </p>
        </div>
        <button
          type="button"
          className="lms-btn-secondary self-start sm:self-auto h-9 px-4 font-['Outfit'] text-xs font-semibold gap-2 shrink-0 cursor-pointer inline-flex items-center"
          onClick={() => setRedeemModalOpen(true)}
        >
          <Ticket className="size-4" />
          Redeem code
        </button>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground font-['Outfit']">Loading checklists...</p>}
      {checklists && checklists.length === 0 && (
        <div className="lms-card flex flex-col items-center justify-center text-center py-14 px-6 gap-5">
          <div>
            <p className="font-['Outfit'] text-lg font-bold text-foreground">No programs assigned yet</p>
            <p className="text-sm text-muted-foreground mt-1 max-w-sm">
              Have an invite code from your school, company, or event? Enter it below to unlock your program checklist.
            </p>
          </div>
          <form onSubmit={handleInlineRedeem} className="flex flex-col sm:flex-row items-center gap-3 w-full max-w-sm">
            <input
              type="text"
              value={inlineCode}
              onChange={(e) => {
                setInlineCode(e.target.value);
                if (inlineError) setInlineError(null);
              }}
              placeholder="e.g. UAE-2026-SCHOOL"
              className="flex-1 w-full uppercase font-mono tracking-wider text-sm rounded-xl border border-border/80 dark:border-lms-accent-border bg-background px-4 py-2.5 shadow-sm focus:outline-none focus:border-lms-cta dark:focus:border-lms-accent"
            />
            <button
              type="submit"
              disabled={inlineLoading || !inlineCode.trim()}
              className="lms-btn-primary px-5 py-2.5 font-['Outfit'] text-xs font-semibold w-full sm:w-auto shrink-0 disabled:opacity-40 cursor-pointer"
            >
              {inlineLoading ? "Redeeming..." : "Redeem code"}
            </button>
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

      <div className="flex flex-col gap-5 max-w-2xl">
        {checklists?.map((c) => (
          <article
            key={c.assignment_id}
            className="lms-card p-6 flex flex-col gap-5 cursor-pointer hover:border-lms-cta dark:hover:border-lms-accent transition-all group"
            onClick={() => void navigate({ to: `/learn/checklists/${c.assignment_id}` })}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="font-['Outfit'] text-lg sm:text-xl font-bold leading-snug text-foreground group-hover:text-lms-cta dark:group-hover:text-lms-accent transition-colors">
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
                  "shrink-0 text-[10px] font-bold uppercase tracking-wider rounded-md px-2.5 py-1",
                  c.pct === 100
                    ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30"
                    : c.items_done > 0
                    ? "bg-lms-cta-light text-lms-cta dark:text-lms-accent border border-lms-cta-border dark:border-lms-accent-border"
                    : "bg-muted text-muted-foreground border border-border/60",
                )}
              >
                {c.pct === 100 ? "Complete" : c.items_done > 0 ? "In progress" : "Not started"}
              </span>
            </div>

            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between text-xs text-muted-foreground font-medium">
                <span>{c.items_done} of {c.items_total} steps</span>
                <span className="font-['Outfit'] font-bold text-foreground">{c.pct}%</span>
              </div>
              <div className="h-2 rounded-full bg-foreground/10 relative overflow-hidden">
                <div
                  className={cn("absolute inset-y-0 left-0 rounded-full transition-all duration-500", c.pct === 100 ? "bg-emerald-500" : "bg-lms-cta dark:bg-lms-accent")}
                  style={{ width: `${c.pct}%` }}
                />
              </div>
            </div>

            <div className="flex items-center justify-between pt-3 border-t border-border/60 dark:border-lms-accent-border/20">
              {c.pct === 100 ? (
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Trophy className="size-3.5 text-amber-500" />
                  {c.certificate_earned ? "Certificate earned" : c.certificate_required ? "Awaiting certificate" : "All done"}
                </div>
              ) : (
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground min-w-0">
                  <ClipboardCheck className="size-3.5 shrink-0 text-lms-cta dark:text-lms-accent" />
                  <span className="truncate">Next: <span className="text-foreground font-semibold">{c.next_item_title}</span></span>
                </div>
              )}
              <span className="shrink-0 text-xs sm:text-sm font-bold text-lms-cta dark:text-lms-accent flex items-center gap-1 font-['Outfit'] group-hover:translate-x-0.5 transition-transform">
                {c.items_done > 0 ? "Continue" : "Start"}
                <ChevronRight className="size-4" />
              </span>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

import { useState } from "react";
import { useNavigate, useParams } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ChevronRight, Download, Lock, Rocket, Trophy } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  fetchLearningPath, fetchMyCertificates, startLearningPath, startPathCheckout, type LearningPathStep,
} from "@/api/lms";
import { cn } from "@/lib/utils";

function formatPrice(cents: number, currency: string): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: currency.toUpperCase() }).format(cents / 100);
}

/** /learn/paths/$id — design 4a "The ledger": one full-bleed hero, a single
 * progress+stats row, and a numbered chapter list with hairline dividers
 * instead of a card grid. "Continue"/"Start" bulk-enrols in every step's
 * course (POST /lms/learning-paths/{id}/start) — a path only makes sense
 * once the student has access to the whole thing, mirroring how cohort-add
 * already bulk-enrols a program's curriculum in one shot. */
export default function LearnPath() {
  const { pathId } = useParams({ strict: false }) as { pathId: string };
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: path, isLoading, error } = useQuery({
    queryKey: ["lms-learning-path", pathId],
    queryFn: () => fetchLearningPath(pathId),
  });
  // The certificate is issued server-side on completion, so the source of
  // truth for "earned" is the certificate list, never a client-side
  // recomputation of whether the steps look done.
  const { data: certificates } = useQuery({
    queryKey: ["lms-my-certificates"],
    queryFn: fetchMyCertificates,
  });
  const earned = certificates?.find((c) => c.learning_path_id === pathId);

  const start = useMutation({
    mutationFn: () => startLearningPath(pathId),
    onSuccess: (updated) => {
      queryClient.setQueryData(["lms-learning-path", pathId], updated);
      const target = updated.steps.find((s) => s.state === "current") ?? updated.steps.find((s) => s.state !== "mission" && s.state !== "done");
      if (target) void navigate({ to: `/learn/courses/${target.course_id}` });
    },
  });

  const [checkoutError, setCheckoutError] = useState("");
  const checkout = useMutation({
    mutationFn: () => startPathCheckout(pathId),
    onSuccess: ({ checkout_url }) => { window.location.href = checkout_url; },
    onError: () => setCheckoutError("Couldn't start checkout. Please try again."),
  });

  if (error) return <div className="mx-auto max-w-[900px] px-5 py-10"><p className="text-sm text-destructive">Couldn't load this learning path.</p></div>;
  if (isLoading || !path) return <div className="mx-auto max-w-[900px] px-5 py-10"><p className="text-sm text-muted-foreground">Loading...</p></div>;

  const currentStep = path.steps.find((s) => s.state === "current");
  const hasStarted = path.steps.some((s) => s.state === "done" || s.state === "current");
  const ctaLabel = start.isPending
    ? "Starting..."
    : !hasStarted
    ? "Start path"
    : currentStep
    ? `Continue step ${currentStep.position}`
    : "Review path";

  const totalHours = Math.round((path.total_duration_seconds / 3600) * 10) / 10;

  return (
    <div className="flex flex-col">
      <div className="relative h-[280px] sm:h-[360px] bg-[repeating-linear-gradient(135deg,hsl(var(--primary)/0.09)_0px,hsl(var(--primary)/0.09)_11px,hsl(var(--foreground)/0.014)_11px,hsl(var(--foreground)/0.014)_22px)] flex items-end">
        {path.image_url && (
          <img src={path.image_url} alt="" className="absolute inset-0 w-full h-full object-cover" />
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-background via-background/55 to-background/10" />
        <div className="relative px-5 sm:px-8 lg:px-14 pb-8 sm:pb-10 flex flex-col gap-3 max-w-2xl">
          <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-primary">Learning path</div>
          <h1 className="font-display text-3xl sm:text-5xl font-bold tracking-tight leading-none">{path.title}</h1>
          {path.description && <p className="text-sm sm:text-base leading-relaxed text-muted-foreground max-w-lg text-pretty">{path.description}</p>}
        </div>
      </div>

      <div className="px-5 sm:px-8 lg:px-14 py-8 sm:py-10 flex flex-col gap-10 max-w-[1180px] mx-auto w-full">
        <div className="flex flex-wrap items-center gap-6 sm:gap-10 py-5 border-b border-border">
          <div className="flex items-baseline gap-2">
            <div className="font-display text-3xl sm:text-4xl font-bold tracking-tight">
              {path.pct}<span className="text-lg text-muted-foreground">%</span>
            </div>
            <div className="text-xs text-muted-foreground">complete</div>
          </div>
          <div className="flex-1 min-w-[120px] h-0.5 bg-border relative">
            <div className="absolute inset-y-0 left-0 bg-primary" style={{ width: `${path.pct}%` }} />
          </div>
          <div className="flex gap-6 sm:gap-8">
            <Stat value={path.course_count} label="courses" />
            {path.mission_count > 0 && <Stat value={path.mission_count} label="missions" />}
            {totalHours > 0 && <Stat value={`${totalHours}h`} label="total" />}
          </div>
          <div className="flex flex-col items-end gap-2 shrink-0">
            <div className="flex items-center gap-2">
              {path.price_cents != null && !path.fully_owned && (
                <Button
                  size="xl" variant={hasStarted ? "outline" : "default"}
                  onClick={() => void checkout.mutate()} disabled={checkout.isPending}
                >
                  {checkout.isPending ? "Redirecting..." : `Buy path — ${formatPrice(path.price_cents, path.currency)}`}
                </Button>
              )}
              {(path.price_cents == null || path.fully_owned || hasStarted) && (
                <Button
                  size="xl"
                  variant={path.price_cents != null && !path.fully_owned ? "outline" : "default"}
                  onClick={() => void start.mutate()} disabled={start.isPending}
                >
                  {ctaLabel}
                  <ChevronRight className="size-4" />
                </Button>
              )}
            </div>
            {checkoutError && <p className="text-xs text-destructive">{checkoutError}</p>}
          </div>
        </div>

        <div className="flex flex-col">
          {path.steps.map((step) => (
            <StepRow key={step.course_id} step={step} onOpen={() => void navigate({ to: `/learn/courses/${step.course_id}` })} />
          ))}
        </div>

        <div className="flex items-center gap-5 sm:gap-6">
          <div className={cn(
            "w-16 h-16 rounded-full ring-1 flex items-center justify-center shrink-0",
            earned ? "ring-primary bg-primary/10 text-primary" : "ring-primary/35 text-primary",
          )}>
            <Trophy className="size-6" />
          </div>
          <div className="min-w-0">
            <div className="font-display text-lg sm:text-xl font-semibold tracking-tight">
              {path.title} certificate
            </div>
            <div className="text-sm text-muted-foreground mt-1 max-w-md text-pretty">
              {earned
                ? "Earned — it's on your profile, and downloadable here."
                : "Awarded automatically once every course above is complete."}
            </div>
          </div>
          {earned?.url && (
            <a
              href={earned.url}
              target="_blank"
              rel="noreferrer"
              className="ml-auto shrink-0 inline-flex items-center gap-1.5 h-10 px-4 rounded-xl bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity"
            >
              <Download className="size-4" /> Download
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

function Stat({ value, label }: { value: string | number; label: string }) {
  return (
    <div>
      <div className="font-display text-lg font-semibold">{value}</div>
      <div className="text-[11px] text-muted-foreground mt-0.5">{label}</div>
    </div>
  );
}

function StepRow({ step, onOpen }: { step: LearningPathStep; onOpen: () => void }) {
  const isMission = step.kind === "mission";
  const clickable = !isMission;
  const statusText =
    step.state === "done" ? "Complete"
    : step.state === "current" ? `${step.pct}% · resume`
    : "Locked";

  return (
    <div
      onClick={clickable ? onOpen : undefined}
      className={cn(
        "grid grid-cols-[auto_1fr_auto] sm:grid-cols-[56px_1fr_auto] items-baseline gap-4 sm:gap-6 py-6 border-b border-border/70",
        step.state === "locked" && "opacity-50",
        isMission && "opacity-80",
        clickable && "cursor-pointer hover:bg-foreground/5 transition-colors -mx-2 px-2 rounded-lg",
      )}
    >
      <div className={cn(
        "font-display text-2xl font-semibold tracking-tight tabular-nums",
        step.state === "current" ? "text-primary" : step.state === "done" ? "text-muted-foreground" : "text-muted-foreground/40",
      )}>
        {String(step.position).padStart(2, "0")}
      </div>
      <div className="flex flex-col gap-1 min-w-0">
        <div className="flex items-center gap-2.5">
          <div className={cn("font-display text-lg sm:text-xl font-semibold tracking-tight", step.state === "current" ? "text-foreground" : "text-foreground/85")}>
            {step.title}
          </div>
          {isMission && (
            <span className="text-[10px] font-semibold uppercase tracking-widest text-primary flex items-center gap-1">
              <Rocket className="size-3" /> Mission
            </span>
          )}
        </div>
        <div className="text-xs text-muted-foreground">
          {step.modules_total > 0 ? `${step.modules_total} module${step.modules_total === 1 ? "" : "s"}` : isMission ? "Field mission" : ""}
        </div>
      </div>
      <div className="flex items-center gap-2 text-sm font-medium justify-self-end">
        {step.state === "done" && <CheckCircle2 className="size-4 text-muted-foreground" />}
        {step.state === "locked" || isMission ? <Lock className="size-3.5 text-muted-foreground" /> : null}
        <span className={step.state === "current" ? "text-primary" : "text-muted-foreground"}>{statusText}</span>
      </div>
    </div>
  );
}

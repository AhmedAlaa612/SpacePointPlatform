import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { useAuth } from "@/context/AuthContext";
import { submitProgramInterest, type UpcomingProgram } from "@/api/lms";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function UpcomingProgramRow({ program }: { program: UpcomingProgram }) {
  const navigate = useNavigate();
  const [interestOpen, setInterestOpen] = useState(false);
  const d = program.starts_on ? new Date(program.starts_on) : null;
  const isPlanned = program.status === "planned";

  const openProgram = () => void navigate({ to: "/learn/programs/$cohortId", params: { cohortId: program.cohort_id } });

  return (
    <article
      onClick={openProgram}
      className="lms-card p-5 sm:p-6 grid grid-cols-1 sm:grid-cols-[76px_1fr_auto] items-center gap-5 cursor-pointer group transition-colors"
    >
      <div className="w-16 h-16 sm:w-[76px] sm:h-[76px] border border-lms-cta-border dark:border-lms-accent-border rounded-lg flex flex-col items-center justify-center bg-transparent shrink-0">
        <strong className="font-display font-extrabold text-2xl sm:text-3xl leading-none text-foreground">
          {d ? d.getDate() : "?"}
        </strong>
        <span className="font-display font-bold text-[10px] tracking-wider mt-1 text-lms-cta dark:text-lms-accent uppercase">
          {d ? MONTHS[d.getMonth()] : "TBA"}
        </span>
      </div>

      <div className="min-w-0">
        <span className="font-display text-[10px] font-bold tracking-wider uppercase text-lms-cta dark:text-lms-accent block mb-1">
          {isPlanned ? "Planned" : "Registration open"}
        </span>
        <h3 className="font-display font-extrabold text-lg sm:text-xl text-foreground tracking-tight truncate group-hover:text-lms-cta dark:group-hover:text-lms-accent transition-colors">
          {program.program_name}
        </h3>
        <p className="text-xs text-muted-foreground truncate mt-1">
          {[
            program.location_name ?? program.location,
            program.spots_left != null ? `${program.spots_left} seats left` : (program.price_display ?? null),
            program.curriculum_titles?.length ? `${program.curriculum_titles.length} modules` : null
          ].filter(Boolean).join(" · ")}
        </p>
      </div>

      <div className="shrink-0" onClick={(e) => e.stopPropagation()}>
        {isPlanned ? (
          <button
            onClick={() => setInterestOpen(true)}
            className="lms-btn-secondary px-5 h-11 text-xs sm:text-sm inline-flex items-center gap-2 cursor-pointer w-full sm:w-auto justify-center"
          >
            Notify me <ArrowRight className="size-3.5" />
          </button>
        ) : (
          <button
            onClick={openProgram}
            className="lms-btn-primary px-5 h-11 text-xs sm:text-sm inline-flex items-center gap-2 cursor-pointer w-full sm:w-auto justify-center"
          >
            View program <ArrowRight className="size-3.5" />
          </button>
        )}
      </div>

      {isPlanned && <NotifyMeDialog program={program} open={interestOpen} onOpenChange={setInterestOpen} />}
    </article>
  );
}

function NotifyMeDialog({
  program, open, onOpenChange,
}: { program: UpcomingProgram; open: boolean; onOpenChange: (open: boolean) => void }) {
  // Pre-fill for a signed-in student — this dialog also serves anonymous
  // marketing-site visitors (submitProgramInterest is a public lead-capture
  // endpoint, not tied to accounts), so a blank form is right for THEM, but
  // asking someone who's already logged in to retype what we already know
  // about them is just friction.
  const { user } = useAuth();
  const [name, setName] = useState(user?.full_name ?? "");
  const [email, setEmail] = useState(user?.email ?? "");
  const [phone, setPhone] = useState(user?.phone ?? "");
  const [website, setWebsite] = useState(""); // honeypot — never shown to a real user
  const [error, setError] = useState("");
  const [result, setResult] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const reset = () => {
    setName(user?.full_name ?? ""); setEmail(user?.email ?? ""); setPhone(user?.phone ?? "");
    setWebsite(""); setError(""); setResult(null);
  };

  const submit = async () => {
    setSubmitting(true);
    setError("");
    try {
      const res = await submitProgramInterest(program.interest_endpoint, {
        student_name: name.trim(), email: email.trim(), phone: phone.trim(), ...(website ? { website } : {}),
      });
      setResult(res.message);
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Something went wrong — please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) reset(); }}>
      <DialogContent className="max-w-md" onClick={(e) => e.stopPropagation()}>
        <DialogTitle>Notify me — {program.program_name}</DialogTitle>
        {result ? (
          <div className="flex flex-col gap-4">
            <p className="text-sm text-foreground">{result}</p>
            <Button onClick={() => onOpenChange(false)}>Done</Button>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <p className="text-sm text-muted-foreground">We'll email you the moment registration opens.</p>
            <input
              value={name} onChange={(e) => setName(e.target.value)} placeholder="Full name" autoFocus
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
            <input
              value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" type="email"
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
            <input
              value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="Phone"
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
            {/* Honeypot — off-screen, never shown to a real user; a bot filling every field fills this too. */}
            <input
              value={website} onChange={(e) => setWebsite(e.target.value)} tabIndex={-1} autoComplete="off"
              className="absolute -left-[9999px] w-px h-px opacity-0" aria-hidden="true"
            />
            {error && <p className="text-xs text-red-500">{error}</p>}
            <Button
              onClick={() => void submit()}
              disabled={!name.trim() || !email.trim() || !phone.trim() || submitting}
            >
              {submitting ? "Sending..." : "Notify me"}
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

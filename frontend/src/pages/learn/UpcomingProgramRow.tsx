import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { Calendar, MapPin, Users, BookOpen, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { submitProgramInterest, type UpcomingProgram } from "@/api/lms";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** One row for a public cohort — /public/catalog data, the same feed the
 * marketing site uses. Clicking the row (or "Register now") opens the full
 * program page (`/learn/programs/$cohortId`, 2026-08-08) — description,
 * curriculum, sessions, location/map, and the full registration form live
 * there now, not inline here. `planned` cohorts keep the lightweight
 * "Notify me" dialog on the row itself — interest is a low-commitment lead
 * capture, not worth sending through a full page.
 */
export function UpcomingProgramRow({ program }: { program: UpcomingProgram }) {
  const navigate = useNavigate();
  const [interestOpen, setInterestOpen] = useState(false);
  const d = program.starts_on ? new Date(program.starts_on) : null;
  const isPlanned = program.status === "planned";

  const openProgram = () => void navigate({ to: "/learn/programs/$cohortId", params: { cohortId: program.cohort_id } });

  return (
    <div
      onClick={openProgram}
      className="py-3.5 border-b border-border/60 last:border-0 flex items-center gap-4 cursor-pointer hover:bg-foreground/5 transition-colors -mx-3 px-3 rounded-xl"
    >
      <div className="w-12 shrink-0 text-center rounded-lg bg-muted py-1.5">
        <div className="text-[10px] font-semibold uppercase tracking-wide text-primary">
          {d ? MONTHS[d.getMonth()] : "—"}
        </div>
        <div className="font-display text-lg font-bold leading-tight">{d ? d.getDate() : "?"}</div>
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold truncate">{program.program_name}</span>
          {isPlanned && (
            <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-muted text-muted-foreground shrink-0">
              Coming soon
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground flex-wrap">
          {(program.location_name ?? program.location) && (
            <span className="flex items-center gap-1"><MapPin className="size-3" />{program.location_name ?? program.location}</span>
          )}
          {program.location_address && (
            <span>{program.location_address}</span>
          )}
          {program.location_maps_url && (
            <a
              href={program.location_maps_url} target="_blank" rel="noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="flex items-center gap-0.5 text-primary hover:underline"
            >
              map <ExternalLink className="size-3" />
            </a>
          )}
          {program.spots_left != null ? (
            <span className="flex items-center gap-1"><Users className="size-3" />{program.spots_left} left</span>
          ) : (
            <span className="flex items-center gap-1"><Calendar className="size-3" />{program.price_display}</span>
          )}
          {program.curriculum_titles.length > 0 && (
            <span className="flex items-center gap-1"><BookOpen className="size-3" />{program.curriculum_titles.length} modules</span>
          )}
        </div>
      </div>
      <div className="shrink-0" onClick={(e) => e.stopPropagation()}>
        {isPlanned ? (
          <Button size="sm" variant="outline" onClick={() => setInterestOpen(true)}>Notify me</Button>
        ) : (
          <Button size="sm" onClick={openProgram}>Register now</Button>
        )}
      </div>

      {isPlanned && <NotifyMeDialog program={program} open={interestOpen} onOpenChange={setInterestOpen} />}
    </div>
  );
}

function NotifyMeDialog({
  program, open, onOpenChange,
}: { program: UpcomingProgram; open: boolean; onOpenChange: (open: boolean) => void }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [website, setWebsite] = useState(""); // honeypot — never shown to a real user
  const [error, setError] = useState("");
  const [result, setResult] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const reset = () => {
    setName(""); setEmail(""); setPhone(""); setWebsite(""); setError(""); setResult(null);
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

import { useState } from "react";
import { Calendar, MapPin, Users, ChevronDown, ChevronUp, BookOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import {
  submitProgramInterest, submitProgramRegistration, type UpcomingProgram,
} from "@/api/lms";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function formatSessionDate(meetingDate: string, startsAt: string | null): string {
  const d = new Date(`${meetingDate}T00:00:00`);
  const dateText = `${MONTHS[d.getMonth()]} ${d.getDate()}`;
  return startsAt ? `${dateText}, ${startsAt.slice(0, 5)}` : dateText;
}

/** One row for a public cohort — /public/catalog data, the same feed the
 * marketing site uses. `planned` cohorts show "Notify me" (register interest,
 * emailed once registration opens); `registration_open` show "Register now".
 * Both open an in-app form posting straight to the public endpoint — replaces
 * the old "Details" link, which pointed a GET at a POST-only API route and
 * 405'd (2026-08-07).
 */
export function UpcomingProgramRow({ program }: { program: UpcomingProgram }) {
  const [expanded, setExpanded] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const d = program.starts_on ? new Date(program.starts_on) : null;
  const isPlanned = program.status === "planned";
  const hasDetails = program.sessions.length > 0 || program.instructors.length > 0 || program.curriculum_titles.length > 0;

  return (
    <div className="py-3.5 border-b border-border/60 last:border-0">
      <div className="flex items-center gap-4">
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
            {program.location && (
              <span className="flex items-center gap-1"><MapPin className="size-3" />{program.location}</span>
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
        <div className="flex items-center gap-2 shrink-0">
          {hasDetails && (
            <button
              onClick={() => setExpanded((v) => !v)}
              className="text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
              aria-label="Show details"
            >
              {expanded ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
            </button>
          )}
          <Button size="sm" variant={isPlanned ? "outline" : "default"} onClick={() => setFormOpen(true)}>
            {isPlanned ? "Notify me" : "Register now"}
          </Button>
        </div>
      </div>

      {expanded && (
        <div className="mt-3 ml-16 flex flex-col gap-2.5 text-xs text-muted-foreground">
          {program.description && <p className="text-foreground/80">{program.description}</p>}
          {program.curriculum_titles.length > 0 && (
            <div>
              <p className="font-medium text-foreground/80 mb-1">What's covered</p>
              <ul className="list-disc list-inside space-y-0.5">
                {program.curriculum_titles.map((title) => <li key={title}>{title}</li>)}
              </ul>
            </div>
          )}
          {program.sessions.length > 0 && (
            <div>
              <p className="font-medium text-foreground/80 mb-1">Sessions</p>
              <ul className="space-y-0.5">
                {program.sessions.map((s, i) => (
                  <li key={i}>{formatSessionDate(s.meeting_date, s.starts_at)}{s.title ? ` — ${s.title}` : ""}</li>
                ))}
              </ul>
            </div>
          )}
          {program.instructors.length > 0 && (
            <p><span className="font-medium text-foreground/80">Instructor{program.instructors.length > 1 ? "s" : ""}:</span> {program.instructors.join(", ")}</p>
          )}
          {program.capacity != null && (
            <p><span className="font-medium text-foreground/80">Capacity:</span> {program.capacity}</p>
          )}
        </div>
      )}

      <ProgramLeadFormDialog program={program} open={formOpen} onOpenChange={setFormOpen} />
    </div>
  );
}

function ProgramLeadFormDialog({
  program, open, onOpenChange,
}: { program: UpcomingProgram; open: boolean; onOpenChange: (open: boolean) => void }) {
  const isPlanned = program.status === "planned";
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
      const endpoint = isPlanned ? program.interest_endpoint : program.registration_endpoint;
      const send = isPlanned ? submitProgramInterest : submitProgramRegistration;
      const res = await send(endpoint, { student_name: name.trim(), email: email.trim(), phone: phone.trim(), ...(website ? { website } : {}) } as never);
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
      <DialogContent className="max-w-md">
        <DialogTitle>{isPlanned ? `Notify me — ${program.program_name}` : `Register — ${program.program_name}`}</DialogTitle>
        {result ? (
          <div className="flex flex-col gap-4">
            <p className="text-sm text-foreground">{result}</p>
            <Button onClick={() => onOpenChange(false)}>Done</Button>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <p className="text-sm text-muted-foreground">
              {isPlanned
                ? "We'll email you the moment registration opens."
                : "A few details and you're in."}
            </p>
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
              {submitting ? "Sending..." : isPlanned ? "Notify me" : "Register"}
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

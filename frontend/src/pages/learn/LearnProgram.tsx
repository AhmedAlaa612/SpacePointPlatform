import { useState } from "react";
import { Link, useParams } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import {
  BookOpen, Calendar, ChevronDown, ChevronRight, ExternalLink, MapPin, Users,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useAuth } from "@/context/AuthContext";
import {
  fetchUpcomingPrograms, submitProgramInterest, submitProgramRegistration,
  type ProgramRegistrationInput, type UpcomingProgram,
} from "@/api/lms";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function formatDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  return `${MONTHS[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
}

function formatSessionDate(meetingDate: string, startsAt: string | null): string {
  const d = new Date(`${meetingDate}T00:00:00`);
  const dateText = `${MONTHS[d.getMonth()]} ${d.getDate()}`;
  return startsAt ? `${dateText}, ${startsAt.slice(0, 5)}` : dateText;
}

/** /learn/programs/$cohortId — the real "program page" the operator asked
 * for, replacing UpcomingProgramRow's inline expand. Reuses the same
 * `/public/catalog` list the catalog/landing pages already fetch (cheap,
 * small list — see LMS_REDESIGN_FOLLOWUPS.md #4) rather than adding a
 * per-cohort endpoint; finds the matching cohort client-side. */
export default function LearnProgram() {
  const { cohortId } = useParams({ strict: false }) as { cohortId: string };
  const { data: programs, isLoading } = useQuery({ queryKey: ["lms-upcoming-programs"], queryFn: fetchUpcomingPrograms });
  const program = programs?.find((p) => p.cohort_id === cohortId);

  if (isLoading) return <div className="mx-auto max-w-[900px] px-5 py-10"><p className="text-sm text-muted-foreground">Loading...</p></div>;
  if (!program) return <div className="mx-auto max-w-[900px] px-5 py-10"><p className="text-sm text-destructive">This program isn't available anymore.</p></div>;

  const isPlanned = program.status === "planned";
  const mapsEmbedSrc = program.location_address
    ? `https://maps.google.com/maps?q=${encodeURIComponent(program.location_address)}&output=embed`
    : null;
  const mapsLinkHref = program.location_maps_url
    || (program.location_address ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(program.location_address)}` : null);

  return (
    <div className="mx-auto max-w-[1180px] px-5 sm:px-8 lg:px-10 py-6 sm:py-8 flex flex-col gap-6">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Link to="/learn/catalog" search={{ tab: "programs" } as never} className="text-primary hover:opacity-80">Upcoming programs</Link>
        <ChevronRight className="size-3" />
        <span className="text-foreground">{program.program_name}</span>
      </div>

      <div className="grid lg:grid-cols-[1fr_380px] gap-8 items-start">
        <div className="flex flex-col gap-6 min-w-0">
          <div className="flex flex-col gap-3">
            {isPlanned && (
              <span className="w-fit text-[11px] font-semibold uppercase tracking-wide px-2.5 py-1 rounded-md bg-muted text-muted-foreground">
                Coming soon
              </span>
            )}
            <h1 className="font-display text-3xl sm:text-4xl font-extrabold tracking-tight leading-tight">{program.program_name}</h1>
            {program.description && <p className="text-base leading-relaxed text-muted-foreground max-w-xl">{program.description}</p>}
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2 pt-1 text-sm text-muted-foreground">
              {program.starts_on && (
                <span className="flex items-center gap-2"><Calendar className="size-4 text-primary" />
                  {formatDate(program.starts_on)}{program.ends_on && program.ends_on !== program.starts_on ? ` – ${formatDate(program.ends_on)}` : ""}
                </span>
              )}
              {(program.location_name || program.location) && (
                <span className="flex items-center gap-2"><MapPin className="size-4 text-primary" />{program.location_name ?? program.location}</span>
              )}
              {program.capacity != null && (
                <span className="flex items-center gap-2"><Users className="size-4 text-primary" />
                  {program.spots_left != null ? `${program.spots_left} of ${program.capacity} spots left` : `${program.capacity} spots`}
                </span>
              )}
            </div>
          </div>

          {program.curriculum_titles.length > 0 && (
            <div className="flex flex-col gap-3">
              <h2 className="font-display text-xl font-bold tracking-tight">What's covered</h2>
              <Card className="p-0 divide-y divide-border">
                {program.curriculum_titles.map((title, i) => (
                  <div key={title} className="flex items-center gap-3.5 p-4">
                    <div className="w-7 h-7 rounded-lg bg-muted flex items-center justify-center shrink-0 text-xs font-semibold text-muted-foreground">
                      {i + 1}
                    </div>
                    <div className="text-sm font-medium flex-1">{title}</div>
                    <BookOpen className="size-4 text-muted-foreground shrink-0" />
                  </div>
                ))}
              </Card>
            </div>
          )}

          {program.sessions.length > 0 && (
            <div className="flex flex-col gap-3">
              <h2 className="font-display text-xl font-bold tracking-tight">Sessions</h2>
              <Card className="p-0 divide-y divide-border">
                {program.sessions.map((s, i) => (
                  <div key={i} className="flex items-center gap-3.5 p-4">
                    <Calendar className="size-4 text-muted-foreground shrink-0" />
                    <div className="text-sm">
                      {formatSessionDate(s.meeting_date, s.starts_at)}
                      {s.title && <span className="text-muted-foreground"> — {s.title}</span>}
                    </div>
                  </div>
                ))}
              </Card>
            </div>
          )}

          {program.instructors.length > 0 && (
            <div className="flex flex-col gap-2">
              <h2 className="font-display text-xl font-bold tracking-tight">Instructor{program.instructors.length > 1 ? "s" : ""}</h2>
              <p className="text-sm text-muted-foreground">{program.instructors.join(", ")}</p>
            </div>
          )}

          {(program.location_name || program.location_address || mapsEmbedSrc) && (
            <div className="flex flex-col gap-3">
              <h2 className="font-display text-xl font-bold tracking-tight">Location</h2>
              <Card className="p-5 gap-3">
                {(program.location_name ?? program.location) && (
                  <div className="font-medium">{program.location_name ?? program.location}</div>
                )}
                {program.location_address && <div className="text-sm text-muted-foreground">{program.location_address}</div>}
                {mapsLinkHref && (
                  <a
                    href={mapsLinkHref} target="_blank" rel="noreferrer"
                    className="inline-flex items-center gap-1 text-sm text-primary hover:underline w-fit"
                  >
                    Open in Google Maps <ExternalLink className="size-3.5" />
                  </a>
                )}
                {mapsEmbedSrc && (
                  <iframe
                    title={`Map for ${program.location_name ?? program.location_address}`}
                    src={mapsEmbedSrc}
                    className="w-full h-[260px] rounded-xl border-0 mt-1"
                    loading="lazy"
                    referrerPolicy="no-referrer-when-downgrade"
                  />
                )}
              </Card>
            </div>
          )}
        </div>

        <div className="lg:sticky lg:top-24">
          {isPlanned ? (
            <NotifyMeCard program={program} />
          ) : (
            <RegistrationCard program={program} />
          )}
        </div>
      </div>
    </div>
  );
}

function NotifyMeCard({ program }: { program: UpcomingProgram }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState("");

  const submit = async () => {
    setSubmitting(true);
    setError("");
    try {
      const res = await submitProgramInterest(program.interest_endpoint, {
        student_name: name.trim(), email: email.trim(), phone: phone.trim(),
      });
      setResult(res.message);
    } catch {
      setError("Something went wrong — please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card className="p-5 flex flex-col gap-3">
      <div className="font-display text-lg font-bold">Notify me</div>
      {result ? (
        <p className="text-sm text-foreground">{result}</p>
      ) : (
        <>
          <p className="text-sm text-muted-foreground">We'll email you the moment registration opens.</p>
          <input
            value={name} onChange={(e) => setName(e.target.value)} placeholder="Full name"
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
          {error && <p className="text-xs text-destructive">{error}</p>}
          <Button size="xl" onClick={() => void submit()} disabled={!name.trim() || !email.trim() || !phone.trim() || submitting}>
            {submitting ? "Sending..." : "Notify me"}
          </Button>
        </>
      )}
    </Card>
  );
}

function RegistrationCard({ program }: { program: UpcomingProgram }) {
  const { currentUser } = useAuth();
  const [form, setForm] = useState<ProgramRegistrationInput>({
    student_name: currentUser?.full_name ?? "",
    email: currentUser?.email ?? "",
    phone: currentUser?.phone ?? "",
    city: "",
    date_of_birth: currentUser?.date_of_birth ?? "",
    grade: currentUser?.grade ?? "",
    organization_name: "",
  });
  const [parentOpen, setParentOpen] = useState(false);
  const [parentName, setParentName] = useState("");
  const [parentPhone, setParentPhone] = useState("");
  const [parentEmail, setParentEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState("");

  const set = (field: keyof ProgramRegistrationInput) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((prev) => ({ ...prev, [field]: e.target.value }));

  const submit = async () => {
    setSubmitting(true);
    setError("");
    try {
      const body: ProgramRegistrationInput = {
        ...form,
        city: form.city?.trim() || undefined,
        date_of_birth: form.date_of_birth || undefined,
        grade: form.grade?.trim() || undefined,
        organization_name: form.organization_name?.trim() || undefined,
        ...(parentName.trim() && parentPhone.trim()
          ? { parent_name: parentName.trim(), parent_phone: parentPhone.trim(), parent_email: parentEmail.trim() || undefined }
          : {}),
      };
      const res = await submitProgramRegistration(program.registration_endpoint, body);
      setResult(res.message);
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Something went wrong — please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const inputCls = "w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors";

  return (
    <Card className="p-5 flex flex-col gap-3">
      <div>
        <div className="font-display text-lg font-bold">{program.price_display}</div>
        <div className="text-xs text-muted-foreground mt-0.5">A few details and you're in.</div>
      </div>
      {result ? (
        <p className="text-sm text-foreground">{result}</p>
      ) : (
        <>
          <input value={form.student_name} onChange={set("student_name")} placeholder="Full name" className={inputCls} />
          <input value={form.email} onChange={set("email")} placeholder="Email" type="email" className={inputCls} />
          <input value={form.phone} onChange={set("phone")} placeholder="Phone" className={inputCls} />
          <input value={form.city ?? ""} onChange={set("city")} placeholder="City (optional)" className={inputCls} />
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-[11px] text-muted-foreground mb-1">Date of birth (optional)</label>
              <input type="date" value={form.date_of_birth ?? ""} onChange={set("date_of_birth")} className={inputCls} />
            </div>
            <div>
              <label className="block text-[11px] text-muted-foreground mb-1">Grade/Year (optional)</label>
              <input value={form.grade ?? ""} onChange={set("grade")} placeholder="e.g. Grade 8" className={inputCls} />
            </div>
          </div>
          <input value={form.organization_name ?? ""} onChange={set("organization_name")} placeholder="School / organization (optional)" className={inputCls} />

          <button
            type="button" onClick={() => setParentOpen((v) => !v)}
            className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors w-fit cursor-pointer"
          >
            <ChevronDown className={`size-3.5 transition-transform ${parentOpen ? "rotate-180" : ""}`} />
            Parent/guardian information (optional)
          </button>
          {parentOpen && (
            <div className="flex flex-col gap-2 pl-1 border-l-2 border-border ml-1.5">
              <input value={parentName} onChange={(e) => setParentName(e.target.value)} placeholder="Parent/guardian name" className={`${inputCls} ml-3 w-[calc(100%-0.75rem)]`} />
              <input value={parentPhone} onChange={(e) => setParentPhone(e.target.value)} placeholder="Parent/guardian phone" className={`${inputCls} ml-3 w-[calc(100%-0.75rem)]`} />
              <input value={parentEmail} onChange={(e) => setParentEmail(e.target.value)} placeholder="Parent/guardian email (optional)" type="email" className={`${inputCls} ml-3 w-[calc(100%-0.75rem)]`} />
            </div>
          )}

          {error && <p className="text-xs text-destructive">{error}</p>}
          <Button
            size="xl"
            onClick={() => void submit()}
            disabled={!form.student_name.trim() || !form.email.trim() || !form.phone.trim() || submitting}
          >
            {submitting ? "Registering..." : "Register"}
          </Button>
        </>
      )}
    </Card>
  );
}

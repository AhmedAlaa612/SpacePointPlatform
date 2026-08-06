import { Calendar, MapPin, Users } from "lucide-react";
import type { UpcomingProgram } from "@/api/lms";
import { apiBaseUrl } from "@/api/client";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** One row for a public, upcoming (registration_open) cohort — /public/catalog
 * data, the same feed the marketing site uses. Browse-only for now: there's no
 * authenticated self-registration flow yet, so "Details" opens the existing
 * public registration form rather than faking a one-click enrol. */
export function UpcomingProgramRow({ program }: { program: UpcomingProgram }) {
  const d = program.starts_on ? new Date(program.starts_on) : null;

  return (
    <a
      href={`${apiBaseUrl}${program.registration_endpoint}`}
      target="_blank"
      rel="noreferrer"
      className="flex items-center gap-4 py-3.5 border-b border-border/60 last:border-0 hover:opacity-80 transition-opacity"
    >
      <div className="w-12 shrink-0 text-center rounded-lg bg-muted py-1.5">
        <div className="text-[10px] font-semibold uppercase tracking-wide text-primary">
          {d ? MONTHS[d.getMonth()] : "—"}
        </div>
        <div className="font-display text-lg font-bold leading-tight">{d ? d.getDate() : "?"}</div>
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold truncate">{program.program_name}</div>
        <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
          {program.location && (
            <span className="flex items-center gap-1"><MapPin className="size-3" />{program.location}</span>
          )}
          {program.spots_left != null && (
            <span className="flex items-center gap-1"><Users className="size-3" />{program.spots_left} left</span>
          )}
          {!program.location && program.spots_left == null && (
            <span className="flex items-center gap-1"><Calendar className="size-3" />{program.price_display}</span>
          )}
        </div>
      </div>
      <div className="text-xs font-semibold px-2.5 py-1 rounded-md bg-primary/10 text-primary shrink-0">
        {program.is_limited ? "Filling up" : "Enrolling"}
      </div>
    </a>
  );
}

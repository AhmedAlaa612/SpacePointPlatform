/** The Ops Handbook (Operate v2, Stage 7C-7).
 *
 * The direct answer to "some notes on common problems that might happen and
 * the right response to it" — a flight rules document, open during the
 * flight, the way a real operations team works.
 *
 * **It is deliberately not hidden.** Withholding it would test memory
 * rather than judgement, and the professional norm is the opposite: flight
 * controllers work from written rules precisely so they don't have to
 * remember under pressure. What difficulty controls (D-d) is how much of
 * the response is spelled out:
 *
 *   full      — symptom, meaning, action, consequence.  (Cadet)
 *   symptoms  — symptom and meaning; you pick the response.  (Engineer)
 *   reference — the fault exists, here's what to watch.  (Flight Director)
 *
 * Every word of it is rendered from `services/missions/operate/anomalies.py`,
 * so authoring a new anomaly authors its own lesson — there is no second
 * document to fall out of sync.
 */
import { useState } from "react";
import { BookOpen, ChevronDown, Radio, X } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { Handbook } from "@/api/missionsOperate";

const DISCLOSURE_NOTE: Record<string, string> = {
  full: "Full playbook — symptom, cause, response and consequence for every fault.",
  symptoms: "Symptoms and causes only. Working out the right response is your job.",
  reference: "Reference only. You are the flight director — diagnose it yourself.",
};

const ORIGIN_NOTE: Record<string, string> = {
  injected: "Happens to you. You can't prevent it — only notice it and respond.",
  emergent: "Happens because of how you're flying. Manage it well and you'll never see it.",
};

function Entry({ entry }: { entry: Handbook["entries"][number] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl ring-1 ring-border overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-start gap-3 px-4 py-3 text-left hover:bg-muted/40 transition-colors"
      >
        <span
          className={`mt-0.5 shrink-0 text-[9px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded ${
            entry.origin === "injected"
              ? "bg-primary/15 text-primary"
              : "bg-amber-500/15 text-amber-600 dark:text-amber-400"
          }`}
          title={ORIGIN_NOTE[entry.origin]}
        >
          {entry.origin === "injected" ? "External" : "Self-inflicted"}
        </span>
        <span className="flex-1 min-w-0">
          <span className="block text-sm font-semibold">{entry.title}</span>
          <span className="block text-xs text-muted-foreground mt-0.5">{entry.symptom}</span>
        </span>
        <ChevronDown className={`size-4 shrink-0 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="px-4 pb-4 pt-1 flex flex-col gap-3 text-xs border-t border-border/60">
          <div>
            <p className="font-semibold text-[10px] uppercase tracking-wide text-muted-foreground mb-1">Watch</p>
            <p className="font-mono text-[11px] text-primary">{entry.symptom_channels.join(" · ")}</p>
          </div>
          {entry.meaning && (
            <div>
              <p className="font-semibold text-[10px] uppercase tracking-wide text-muted-foreground mb-1">
                What it means
              </p>
              <p className="leading-relaxed">{entry.meaning}</p>
            </div>
          )}
          {entry.action && (
            <div>
              <p className="font-semibold text-[10px] uppercase tracking-wide text-emerald-600 dark:text-emerald-400 mb-1">
                What to do
              </p>
              <p className="leading-relaxed">{entry.action}</p>
            </div>
          )}
          {entry.if_ignored && (
            <div>
              <p className="font-semibold text-[10px] uppercase tracking-wide text-destructive mb-1">If you don't</p>
              <p className="leading-relaxed">{entry.if_ignored}</p>
            </div>
          )}
          {entry.commands && entry.commands.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {entry.commands.map((c) => (
                <code key={c} className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-muted">{c}</code>
              ))}
            </div>
          )}
          {!entry.meaning && (
            <p className="text-[11px] italic text-muted-foreground">
              {DISCLOSURE_NOTE.reference}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export function HandbookBody({ handbook }: { handbook: Handbook }) {
  const bySubsystem = handbook.commands.reduce<Record<string, typeof handbook.commands>>((acc, c) => {
    (acc[c.subsystem] ||= []).push(c);
    return acc;
  }, {});

  return (
    <Tabs defaultValue="anomalies" className="gap-3">
      <TabsList>
        <TabsTrigger value="anomalies">Anomalies</TabsTrigger>
        <TabsTrigger value="commands">Commands</TabsTrigger>
        <TabsTrigger value="rules">Flight rules</TabsTrigger>
        <TabsTrigger value="assumptions">Model</TabsTrigger>
      </TabsList>

      <TabsContent value="anomalies" className="flex flex-col gap-2">
        <p className="text-[11px] text-muted-foreground">{DISCLOSURE_NOTE[handbook.disclosure]}</p>
        {handbook.entries.map((e) => <Entry key={e.key} entry={e} />)}
      </TabsContent>

      <TabsContent value="commands" className="flex flex-col gap-3">
        {Object.entries(bySubsystem).map(([subsystem, commands]) => (
          <div key={subsystem}>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground mb-1.5">
              {subsystem}
            </p>
            <div className="flex flex-col gap-1">
              {commands.map((c) => (
                <div key={c.name} className="flex flex-col sm:flex-row sm:items-baseline gap-x-3 gap-y-0.5 text-xs">
                  <code className="font-mono text-[11px] text-primary shrink-0 sm:w-52">{c.usage}</code>
                  <span className="text-muted-foreground">{c.summary}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </TabsContent>

      <TabsContent value="rules" className="flex flex-col gap-1.5">
        <p className="text-[11px] text-muted-foreground mb-1">
          The console colours every readout against these. A value outside its band is the first thing to look at.
        </p>
        {handbook.flight_rules.map((r) => (
          <div key={r.channel} className="flex items-baseline justify-between gap-3 text-xs py-1 border-b border-border/40 last:border-0">
            <span>
              <span className="text-[10px] font-mono text-muted-foreground mr-2">{r.subsystem}</span>
              {r.label}
            </span>
            <span className="font-mono text-[11px] shrink-0">
              {r.low !== null && r.high !== null
                ? `${r.low} – ${r.high} ${r.unit}`
                : r.low !== null
                  ? `≥ ${r.low} ${r.unit}`
                  : `≤ ${r.high} ${r.unit}`}
            </span>
          </div>
        ))}
      </TabsContent>

      <TabsContent value="assumptions" className="flex flex-col gap-2">
        <p className="text-[11px] text-muted-foreground">
          This is a teaching model, and here is exactly what it simplifies. Knowing the limits of your simulation
          is part of knowing how to use one.
        </p>
        <ul className="flex flex-col gap-1.5">
          {handbook.assumptions.map((a) => (
            <li key={a} className="text-xs leading-relaxed flex gap-2">
              <span className="text-muted-foreground shrink-0">·</span>
              <span>{a}</span>
            </li>
          ))}
        </ul>
      </TabsContent>
    </Tabs>
  );
}

/** Slide-over panel for the live console. */
export default function OpsHandbook({ handbook }: { handbook: Handbook | null }) {
  const [open, setOpen] = useState(false);
  if (!handbook) return null;

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-6 right-6 z-40 flex items-center gap-2 px-4 py-2.5 rounded-full bg-primary text-primary-foreground shadow-lg hover:opacity-90 transition-opacity text-xs font-semibold"
      >
        <BookOpen className="size-4" />
        Ops Handbook
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <button
            aria-label="Close handbook"
            onClick={() => setOpen(false)}
            className="absolute inset-0 bg-background/70 backdrop-blur-sm"
          />
          <aside className="relative w-full sm:max-w-[560px] h-full overflow-y-auto bg-card ring-1 ring-border p-5 sm:p-6 flex flex-col gap-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="font-display text-lg font-extrabold tracking-tight flex items-center gap-2">
                  <Radio className="size-4 text-primary" /> Ops Handbook
                </h2>
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  Flight rules stay open during the flight. That is how real ops works.
                </p>
              </div>
              <button onClick={() => setOpen(false)} className="p-1 rounded hover:bg-muted">
                <X className="size-4" />
              </button>
            </div>
            <HandbookBody handbook={handbook} />
          </aside>
        </div>
      )}
    </>
  );
}

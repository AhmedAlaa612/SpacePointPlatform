/** The Design Handbook (Design v2, 7D-5).
 *
 * The design mission's answer to the Ops Handbook: what each budget checks,
 * what makes it fail, what to change, the formulas, the eight data types,
 * and a library of the mistakes students actually make.
 *
 * Open while designing at every difficulty, for the same reason the operate
 * mission's is: engineers work from references, and testing memory is not
 * the lesson. What the variant controls is how much of the *fix* is spelled
 * out (`handbook_disclosure`).
 *
 * Every word comes from `services/missions/design/content.py`, so the
 * dashboard's recommendations and this handbook can never disagree — they
 * render the same records.
 */
import { useState } from "react";
import { BookOpen, ChevronDown, X } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { DesignHandbook as Handbook, HandbookBudget, HandbookMistake } from "@/api/missionsDesign";

/** Authored content is prose, not markdown — but a mission manager can
 * type whatever they like into it (D8), and nothing here renders
 * markdown. Strip the asterisks rather than show them raw. */
function stripMarkdown(text: string): string {
  return (text ?? "").replace(/\*\*/g, "");
}

const DISCLOSURE_NOTE: Record<string, string> = {
  full: "Full playbook — what each budget checks, why it fails, and what to change.",
  symptoms: "What each budget checks and why it fails. Working out the fix is your job.",
  reference: "Formulas and limits only. You are the systems engineer.",
};

function Collapsible({ title, subtitle, children }: {
  title: string; subtitle: string; children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl ring-1 ring-border overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-start gap-3 px-4 py-3 text-left hover:bg-muted/40 transition-colors"
      >
        <span className="flex-1 min-w-0">
          <span className="block text-sm font-semibold">{title}</span>
          <span className="block text-xs text-muted-foreground mt-0.5">{subtitle}</span>
        </span>
        <ChevronDown className={`size-4 shrink-0 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && <div className="px-4 pb-4 pt-1 flex flex-col gap-3 text-xs border-t border-border/60">{children}</div>}
    </div>
  );
}

function Section({ label, tone, children }: { label: string; tone?: string; children: React.ReactNode }) {
  return (
    <div>
      <p className={`text-[10px] font-semibold uppercase tracking-wide mb-1 ${tone ?? "text-muted-foreground"}`}>{label}</p>
      <p className="leading-relaxed">{children}</p>
    </div>
  );
}

function BudgetEntry({ budget: b }: { budget: HandbookBudget }) {
  return (
    <Collapsible title={b.title} subtitle={b.checks}>
      {b.means && <Section label="What it means">{b.means}</Section>}
      {b.fails_when && <Section label="It fails when">{b.fails_when}</Section>}
      {b.fix && <Section label="How to fix it" tone="text-emerald-600 dark:text-emerald-400">{b.fix}</Section>}
      {b.why_it_matters && <Section label="Why it matters">{b.why_it_matters}</Section>}
      <div>
        <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground mb-1">Formula</p>
        <pre className="font-mono text-[11px] leading-relaxed whitespace-pre-wrap bg-muted/50 rounded-lg px-3 py-2">{b.formula}</pre>
      </div>
    </Collapsible>
  );
}

function MistakeEntry({ mistake: m }: { mistake: HandbookMistake }) {
  return (
    <Collapsible title={m.title} subtitle={m.symptom}>
      {m.meaning && <Section label="What's actually happening">{m.meaning}</Section>}
      {m.fix && <Section label="How to fix it" tone="text-emerald-600 dark:text-emerald-400">{m.fix}</Section>}
      <div className="flex flex-wrap gap-1.5">
        {m.steps.map((s) => (
          <code key={s} className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-muted">{s.replace(/_/g, " ")}</code>
        ))}
      </div>
    </Collapsible>
  );
}

export function DesignHandbookBody({ handbook: h }: { handbook: Handbook }) {
  return (
    <Tabs defaultValue="budgets" className="gap-3">
      <TabsList className="flex-wrap">
        <TabsTrigger value="budgets">Budgets</TabsTrigger>
        <TabsTrigger value="mistakes">Common mistakes</TabsTrigger>
        <TabsTrigger value="data">Data types</TabsTrigger>
        <TabsTrigger value="order">The order</TabsTrigger>
        <TabsTrigger value="model">Model</TabsTrigger>
      </TabsList>

      <TabsContent value="budgets" className="flex flex-col gap-2">
        <p className="text-[11px] text-muted-foreground">{DISCLOSURE_NOTE[h.disclosure]}</p>
        <div className="rounded-xl ring-1 ring-primary/25 bg-primary/5 px-4 py-3">
          <p className="text-xs leading-relaxed whitespace-pre-line">{stripMarkdown(h.what_is_a_budget)}</p>
        </div>
        {h.budgets.map((b) => <BudgetEntry key={b.key} budget={b} />)}
      </TabsContent>

      <TabsContent value="mistakes" className="flex flex-col gap-2">
        <p className="text-[11px] text-muted-foreground">
          Every one of these is a design that passes some checks and fails others in a
          recognisable pattern. When the report tells you what to change, this is where it
          gets the advice from.
        </p>
        {h.mistakes.map((m) => <MistakeEntry key={m.key} mistake={m} />)}
      </TabsContent>

      <TabsContent value="data" className="flex flex-col gap-1.5">
        <p className="text-[11px] text-muted-foreground mb-1">
          What each data type on the data budget actually means.
        </p>
        {h.data_types.map((d) => (
          <div key={d.name} className="flex flex-col sm:flex-row sm:items-baseline gap-x-3 gap-y-0.5 text-xs py-1.5 border-b border-border/40 last:border-0">
            <span className="font-semibold shrink-0 sm:w-44">{d.name}</span>
            <span className="text-muted-foreground leading-relaxed">{d.detail}</span>
          </div>
        ))}
      </TabsContent>

      <TabsContent value="order" className="flex flex-col gap-2">
        <p className="text-[11px] text-muted-foreground">
          You can work in any order you like — but these are computed from each other, so some
          steps will look empty until the ones they read from are filled in.
        </p>
        {h.step_order.map((s, i) => (
          <div key={s.key} className="flex gap-3">
            <span className="shrink-0 size-5 rounded-full bg-muted text-[10px] font-mono flex items-center justify-center mt-0.5">
              {i + 1}
            </span>
            <div className="min-w-0">
              <p className="text-xs font-semibold">{s.label}</p>
              <p className="text-[11px] text-muted-foreground leading-relaxed mt-0.5">{stripMarkdown(s.detail)}</p>
              {s.depends_on.length > 0 && (
                <p className="text-[10px] font-mono text-primary mt-0.5">
                  reads: {s.depends_on.map((d) => d.replace(/_/g, " ")).join(", ")}
                </p>
              )}
            </div>
          </div>
        ))}
      </TabsContent>

      <TabsContent value="model" className="flex flex-col gap-2">
        <p className="text-[11px] text-muted-foreground">
          This is a teaching model, and here is exactly what it simplifies. Knowing the limits of
          your analysis is part of knowing how to use it.
        </p>
        <ul className="flex flex-col gap-1.5">
          {h.assumptions.map((a) => (
            <li key={a} className="text-xs leading-relaxed flex gap-2">
              <span className="text-muted-foreground shrink-0">·</span><span>{a}</span>
            </li>
          ))}
        </ul>
      </TabsContent>
    </Tabs>
  );
}

/** Slide-over panel for the design wizard. */
export default function DesignHandbookDrawer({ handbook }: { handbook: Handbook | null }) {
  const [open, setOpen] = useState(false);
  if (!handbook) return null;

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-6 right-6 z-40 flex items-center gap-2 px-4 py-2.5 rounded-full bg-primary text-primary-foreground shadow-lg hover:opacity-90 transition-opacity text-xs font-semibold"
      >
        <BookOpen className="size-4" />
        Design Handbook
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <button
            aria-label="Close handbook"
            onClick={() => setOpen(false)}
            className="absolute inset-0 bg-background/70 backdrop-blur-sm"
          />
          <aside className="relative w-full sm:max-w-[600px] h-full overflow-y-auto bg-card ring-1 ring-border p-5 sm:p-6 flex flex-col gap-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="font-display text-lg font-extrabold tracking-tight flex items-center gap-2">
                  <BookOpen className="size-4 text-primary" /> Design Handbook
                </h2>
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  Keep this open while you work. Engineers design with references, not from memory.
                </p>
              </div>
              <button onClick={() => setOpen(false)} className="p-1 rounded hover:bg-muted">
                <X className="size-4" />
              </button>
            </div>
            <DesignHandbookBody handbook={handbook} />
          </aside>
        </div>
      )}
    </>
  );
}

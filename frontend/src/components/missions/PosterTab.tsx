/** Poster/Canva (August Build Brief, Branch 3) — down to two link fields:
 * `poster_template_url` (ops-set once per cohort, read-only here) and
 * `poster_url` (the team's own working-copy link, editable until the
 * cohort's program ends).
 *
 * Mirrors `DesignHandbookDrawer`'s slide-over-panel mechanic exactly, but
 * anchored to the left edge instead of the right — the bottom-right corner
 * is already the handbook's trigger, and this is the only other floating
 * tab this wizard needs (legacy Madar's left-edge "Standings" tab is the
 * precedent for the shape).
 */
import { useState } from "react";
import { isAxiosError } from "axios";
import { Image as ImageIcon, X } from "lucide-react";
import type { DesignState } from "@/api/missionsDesign";
import { updateDesign } from "@/api/missionsDesign";

function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err)) {
    const detail = err.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object" && "message" in detail) return String(detail.message);
  }
  return fallback;
}

export default function PosterTab({ state, attemptId, onSaved }: {
  state: DesignState; attemptId: string; onSaved: (s: DesignState) => void;
}) {
  const [open, setOpen] = useState(false);
  const [posterUrl, setPosterUrl] = useState(state.poster_url ?? "");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  const save = async () => {
    setSaving(true);
    setSaveError("");
    try {
      const next = await updateDesign(attemptId, { poster_url: posterUrl });
      onSaved(next);
    } catch (err) {
      setSaveError(errorDetail(err, "Couldn't save your poster link."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="fixed left-0 top-1/2 -translate-y-1/2 z-40 group flex flex-col items-center gap-3 px-3.5 py-6 rounded-r-2xl bg-[#1d132e]/95 hover:bg-[#271a3e] border border-l-0 border-purple-500/30 hover:border-purple-400/50 text-purple-100 shadow-2xl shadow-purple-950/80 -translate-x-1.5 hover:translate-x-0 transition-all duration-300 ease-out cursor-pointer select-none"
        title="Open Poster Tab"
      >
        <span className="text-[11px] font-bold tracking-widest uppercase [writing-mode:vertical-rl] rotate-180 text-purple-200/90 group-hover:text-white transition-colors">
          POSTER
        </span>
        <div className="p-1.5 rounded-lg bg-purple-500/15 border border-purple-500/30 text-purple-300 group-hover:bg-purple-500/25 group-hover:text-purple-100 transition-colors">
          <ImageIcon className="size-4" />
        </div>
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex justify-start">
          <button
            aria-label="Close poster tab"
            onClick={() => setOpen(false)}
            className="absolute inset-0 bg-background/80 backdrop-blur-md transition-opacity"
          />
          <aside className="relative w-full sm:max-w-[480px] h-full overflow-y-auto bg-card border-r border-border p-6 flex flex-col gap-5 shadow-2xl animate-in slide-in-from-left duration-200">
            <div className="flex items-start justify-between gap-3 pb-4 border-b border-border">
              <div>
                <h2 className="font-display text-lg font-extrabold tracking-tight flex items-center gap-2.5 text-foreground">
                  <div className="p-2 rounded-xl bg-primary/10 border border-primary/20 text-primary">
                    <ImageIcon className="size-5" />
                  </div>
                  Mission Poster
                </h2>
                <p className="text-xs text-muted-foreground mt-1">
                  Your team's mission poster — start from the template, keep your working link updated here.
                </p>
              </div>
              <button
                onClick={() => setOpen(false)}
                className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
              >
                <X className="size-4" />
              </button>
            </div>

            <div className="flex flex-col gap-2.5 p-4 rounded-2xl bg-muted/30 border border-border/60">
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Template</p>
              {state.poster_template_url ? (
                <a
                  href={state.poster_template_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline underline-offset-4"
                >
                  Open your poster template ↗
                </a>
              ) : (
                <p className="text-xs text-muted-foreground">
                  Ask your ops team to set a poster template for this cohort.
                </p>
              )}
            </div>

            <div className="flex flex-col gap-3 p-4 rounded-2xl bg-card border border-border shadow-sm">
              <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Your working copy link
              </label>
              <input
                value={posterUrl}
                onChange={(e) => setPosterUrl(e.target.value)}
                placeholder="https://canva.com/design/..."
                className="w-full h-10 px-3.5 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
              />
              <button
                onClick={() => void save()}
                disabled={saving}
                className="w-fit h-9 px-5 bg-primary text-primary-foreground rounded-xl text-xs font-semibold hover:opacity-90 transition-opacity disabled:opacity-50 cursor-pointer shadow-sm"
              >
                {saving ? "Saving..." : "Save Poster Link"}
              </button>
              {saveError && <p className="text-xs text-destructive mt-1">{saveError}</p>}
            </div>
          </aside>
        </div>
      )}
    </>
  );
}

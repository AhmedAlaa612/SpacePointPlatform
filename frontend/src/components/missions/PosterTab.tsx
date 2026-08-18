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
        className="fixed left-0 top-1/2 -translate-y-1/2 z-40 flex items-center gap-2 px-3 py-2.5 rounded-r-full bg-primary text-primary-foreground shadow-lg hover:opacity-90 transition-opacity text-xs font-semibold [writing-mode:vertical-rl] rotate-180"
      >
        <ImageIcon className="size-4 rotate-90" />
        Poster
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex justify-start">
          <button
            aria-label="Close poster tab"
            onClick={() => setOpen(false)}
            className="absolute inset-0 bg-background/70 backdrop-blur-sm"
          />
          <aside className="relative w-full sm:max-w-[480px] h-full overflow-y-auto bg-card ring-1 ring-border p-5 sm:p-6 flex flex-col gap-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="font-display text-lg font-extrabold tracking-tight flex items-center gap-2">
                  <ImageIcon className="size-4 text-primary" /> Poster
                </h2>
                <p className="text-[11px] text-muted-foreground mt-0.5">
                  Your team's mission poster — start from the template, keep the working link here.
                </p>
              </div>
              <button onClick={() => setOpen(false)} className="p-1 rounded hover:bg-muted">
                <X className="size-4" />
              </button>
            </div>

            <div className="flex flex-col gap-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Template</p>
              {state.poster_template_url ? (
                <a
                  href={state.poster_template_url} target="_blank" rel="noreferrer"
                  className="text-sm text-primary underline underline-offset-2 hover:opacity-80 transition-opacity"
                >
                  Open your poster template
                </a>
              ) : (
                <p className="text-xs text-muted-foreground">
                  Ask your ops team to set a poster template for this cohort.
                </p>
              )}
            </div>

            <div className="flex flex-col gap-2">
              <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Your working copy link
              </label>
              <input
                value={posterUrl} onChange={(e) => setPosterUrl(e.target.value)}
                placeholder="https://canva.com/design/..."
                className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
              />
              <button
                onClick={() => void save()} disabled={saving}
                className="w-fit h-9 px-4 bg-primary text-primary-foreground rounded-xl text-xs font-semibold hover:opacity-90 transition-opacity disabled:opacity-50"
              >
                {saving ? "Saving..." : "Save"}
              </button>
              {saveError && <p className="text-xs text-destructive">{saveError}</p>}
            </div>
          </aside>
        </div>
      )}
    </>
  );
}

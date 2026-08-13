/** Mission content authoring (Design v2, 7D-8 / D8).
 *
 * The editable half of a published mission. `mission_variants.config` —
 * thresholds, limits, objectives — is frozen once a mission goes live,
 * because editing a threshold retroactively changes what already-graded
 * attempts were measured against. Explanation is a different thing: it can
 * be improved at any time, by staff or by the mission's assigned manager,
 * and that is what makes an intern mission-owner a useful role rather than
 * a read-only one.
 *
 * Two behaviours worth knowing:
 *
 * * **Clearing a field restores the default**, it does not blank it. There
 *   is no way to delete the authored copy, only to replace it.
 * * **Text identical to the default is never saved as an override.** If it
 *   were, a field an editor merely looked at would stop tracking future
 *   improvements to the shipped wording.
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import { ChevronDown, RotateCcw } from "lucide-react";
import {
  fetchMissionContent, hasContentModel, saveMissionContent, toOverrides,
  type ContentEntry, type ContentField, type EditableContent,
} from "@/api/missionsContent";

function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") return err.response.data.detail;
  return fallback;
}

const FIELD_LABELS: Record<string, string> = {
  title: "Title",
  checks: "What it checks",
  means: "What it means",
  fails_when: "It fails when",
  fix: "How to fix it",
  why_it_matters: "Why it matters",
  symptom: "Symptom",
  meaning: "What's actually happening",
};

function FieldEditor({ label, field, onChange }: {
  label: string; field: ContentField; onChange: (value: string) => void;
}) {
  const dirty = field.value !== field.default;
  const rows = Math.min(8, Math.max(2, Math.ceil(field.value.length / 90)));
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between gap-2">
        <label className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          {label}
          {dirty && <span className="ml-1.5 text-primary normal-case tracking-normal">· edited</span>}
        </label>
        {dirty && (
          <button
            onClick={() => onChange(field.default)}
            className="flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground"
            title="Restore the shipped wording"
          >
            <RotateCcw className="size-3" /> Reset
          </button>
        )}
      </div>
      <textarea
        value={field.value} rows={rows}
        onChange={(e) => onChange(e.target.value)}
        className={`px-3 py-2 border bg-card text-foreground rounded-xl text-sm leading-relaxed
          focus:outline-none focus:border-primary transition-colors resize-y w-full
          ${dirty ? "border-primary/50" : "border-border"}`}
      />
    </div>
  );
}

function EntryEditor({ entry, onChange }: {
  entry: ContentEntry; onChange: (field: string, value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const edited = Object.values(entry.fields).filter((f) => f.value !== f.default).length;
  const title = entry.fields.title?.value ?? entry.key.replace(/_/g, " ");

  return (
    <div className="rounded-xl ring-1 ring-border overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-muted/40 transition-colors"
      >
        <span className="flex-1 min-w-0 text-sm font-medium truncate">{title}</span>
        {edited > 0 && (
          <span className="shrink-0 text-[10px] font-semibold text-primary">{edited} edited</span>
        )}
        <ChevronDown className={`size-4 shrink-0 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="px-4 pb-4 pt-1 flex flex-col gap-3 border-t border-border/60">
          {Object.entries(entry.fields).map(([field, meta]) => (
            <FieldEditor
              key={field} label={FIELD_LABELS[field] ?? field} field={meta}
              onChange={(value) => onChange(field, value)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function MissionContentSection({ missionId }: { missionId: string }) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<EditableContent | null>(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  const { data: content, isLoading } = useQuery({
    queryKey: ["mission-content", missionId],
    queryFn: () => fetchMissionContent(missionId),
  });

  const save = useMutation({
    mutationFn: (editable: EditableContent) => saveMissionContent(missionId, toOverrides(editable)),
    onSuccess: (next) => {
      setError("");
      setSaved(true);
      setDraft(hasContentModel(next) ? next.editable : null);
      void queryClient.invalidateQueries({ queryKey: ["mission-content", missionId] });
    },
    onError: (err) => setError(errorDetail(err, "Couldn't save this content.")),
  });

  if (isLoading || !content) return null;
  if (!hasContentModel(content)) {
    // Only `design` has an authored content model today. Rendering nothing
    // is right — an empty editor on a quiz mission would imply there is
    // something to write.
    return null;
  }

  const editable = draft ?? content.editable;
  // "Dirty" means *unsaved*, not "differs from the shipped default". An
  // override that has already been saved is a perfectly settled state — if
  // dirty meant "differs from default" then Save would never clear it and
  // the Saved badge could never show.
  const dirty = draft !== null && JSON.stringify(draft) !== JSON.stringify(content.editable);

  const update = (next: EditableContent) => {
    setDraft(next);
    setSaved(false);
  };

  const patchEntry = (list: "budgets" | "mistakes", key: string, field: string, value: string) =>
    update({
      ...editable,
      [list]: editable[list].map((e) =>
        e.key === key ? { ...e, fields: { ...e.fields, [field]: { ...e.fields[field], value } } } : e),
    });

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 className="text-lg font-bold flex items-center">
            <span className="w-1.5 h-6 bg-primary rounded-full mr-3" />
            Teaching content
          </h3>
          <p className="text-xs text-muted-foreground mt-1 max-w-[70ch] leading-relaxed">
            The briefing, handbook and report advice students read. Editable even while this mission
            is published — changing an explanation cannot re-grade anybody. Thresholds and objectives
            are the other half of that split, and those stay frozen until the mission returns to draft.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {saved && !dirty && <span className="text-[11px] text-emerald-600 dark:text-emerald-400">Saved</span>}
          <button
            onClick={() => { setDraft(null); setSaved(false); setError(""); }}
            disabled={!dirty}
            className="h-9 px-4 border border-border rounded-xl text-sm font-medium hover:bg-muted transition-colors disabled:opacity-40"
          >
            Discard
          </button>
          <button
            onClick={() => save.mutate(editable)}
            disabled={save.isPending}
            className="h-9 px-4 rounded-xl text-sm font-medium bg-primary text-primary-foreground hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {save.isPending ? "Saving..." : "Save content"}
          </button>
        </div>
      </div>

      {error && <p className="text-xs text-destructive">{error}</p>}

      <FieldEditor
        label="What a budget is — the briefing's opening paragraph"
        field={editable.what_is_a_budget}
        onChange={(value) => update({
          ...editable,
          what_is_a_budget: { ...editable.what_is_a_budget, value },
        })}
      />

      <div className="flex flex-col gap-2">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          Budgets — what each one checks and how to fix it
        </p>
        {editable.budgets.map((entry) => (
          <EntryEditor
            key={entry.key} entry={entry}
            onChange={(field, value) => patchEntry("budgets", entry.key, field, value)}
          />
        ))}
      </div>

      <div className="flex flex-col gap-2">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Common mistakes
          </p>
          <p className="text-[11px] text-muted-foreground mt-0.5">
            These are also what the report screen recommends when a design fails in a matching
            pattern, so editing one changes the advice in both places.
          </p>
        </div>
        {editable.mistakes.map((entry) => (
          <EntryEditor
            key={entry.key} entry={entry}
            onChange={(field, value) => patchEntry("mistakes", entry.key, field, value)}
          />
        ))}
      </div>

      <p className="text-[11px] text-muted-foreground">
        Clearing a field restores the shipped wording — there is no way to leave a student with a
        blank explanation. Text left identical to the default is not saved as an override, so it
        keeps tracking future improvements.
      </p>
    </div>
  );
}

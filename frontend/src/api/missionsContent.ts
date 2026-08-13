/** Mission content authoring (Design v2, 7D-8 / D8) —
 * `/missions/manager/{mission_id}/content`.
 *
 * The D8 split in one sentence: `mission_variants.config` holds grading
 * criteria and is frozen once a mission is published; `missions.content`
 * holds explanation and is always editable, by staff and by that mission's
 * assigned manager. Changing how a budget is explained cannot re-grade
 * anybody; changing a threshold can.
 *
 * Every field arrives with both its current `value` and the code-authored
 * `default`, so an editor can always see what they changed and clearing a
 * field restores the default rather than blanking it.
 */
import { api } from "./client";

export interface ContentField {
  value: string;
  overridden: boolean;
  default: string;
}

export interface ContentEntry {
  key: string;
  fields: Record<string, ContentField>;
}

export interface EditableContent {
  what_is_a_budget: ContentField;
  budgets: ContentEntry[];
  mistakes: ContentEntry[];
  assumptions: { value: string[]; overridden: boolean; default: string[] };
}

export interface MissionContent {
  mission_id: string;
  mission_kind: string;
  mission_status: string;
  /** Empty for any kind that has no authored content model (currently
   * everything except `design`). */
  editable: EditableContent | Record<string, never>;
}

/** The shape the PUT expects — overrides only, blanks meaning "restore". */
export interface ContentOverrides {
  what_is_a_budget?: string;
  budgets?: Record<string, Record<string, string>>;
  mistakes?: Record<string, Record<string, string>>;
  assumptions?: string[];
}

export async function fetchMissionContent(missionId: string): Promise<MissionContent> {
  const { data } = await api.get<MissionContent>(`/missions/manager/${missionId}/content`);
  return data;
}

export async function saveMissionContent(
  missionId: string, content: ContentOverrides,
): Promise<MissionContent> {
  const { data } = await api.put<MissionContent>(`/missions/manager/${missionId}/content`, { content });
  return data;
}

/** Rebuild the override payload from an edited `EditableContent`.
 * A value equal to its default is dropped, not sent — otherwise "I didn't
 * touch this" would silently become a permanent override that stops
 * tracking future improvements to the default copy. */
export function toOverrides(editable: EditableContent): ContentOverrides {
  const out: ContentOverrides = {};

  if (editable.what_is_a_budget.value.trim() &&
      editable.what_is_a_budget.value !== editable.what_is_a_budget.default) {
    out.what_is_a_budget = editable.what_is_a_budget.value;
  }

  const collect = (entries: ContentEntry[]) => {
    const acc: Record<string, Record<string, string>> = {};
    for (const entry of entries) {
      const changed: Record<string, string> = {};
      for (const [field, meta] of Object.entries(entry.fields)) {
        if (meta.value.trim() && meta.value !== meta.default) changed[field] = meta.value;
      }
      if (Object.keys(changed).length) acc[entry.key] = changed;
    }
    return acc;
  };

  const budgets = collect(editable.budgets);
  if (Object.keys(budgets).length) out.budgets = budgets;
  const mistakes = collect(editable.mistakes);
  if (Object.keys(mistakes).length) out.mistakes = mistakes;

  const assumptions = editable.assumptions.value.filter((a) => a.trim());
  if (assumptions.length && JSON.stringify(assumptions) !== JSON.stringify(editable.assumptions.default)) {
    out.assumptions = assumptions;
  }

  return out;
}

export function hasContentModel(content: MissionContent): content is MissionContent & { editable: EditableContent } {
  return "what_is_a_budget" in content.editable;
}

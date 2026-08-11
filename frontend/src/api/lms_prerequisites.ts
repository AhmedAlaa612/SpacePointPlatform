/** Unified prerequisite edges (7B-2) — thin wrapper over
 * `/lms/admin/prerequisites`. Types mirror `schemas/curriculum.py`. */
import { api } from "@/api/client";

export type PrerequisiteItemType = "course" | "mission";

export interface PrerequisiteEdge {
  item_type: PrerequisiteItemType;
  item_id: string;
  requires_type: PrerequisiteItemType;
  requires_id: string;
  requires_title: string;
}

export interface PrerequisiteEdgeInput {
  item_type: PrerequisiteItemType;
  item_id: string;
  requires_type: PrerequisiteItemType;
  requires_id: string;
}

export const listPrerequisitesApi = (itemType: PrerequisiteItemType, itemId: string) =>
  api.get<PrerequisiteEdge[]>("/lms/admin/prerequisites", { params: { item_type: itemType, item_id: itemId } })
    .then((r) => r.data);

export const addPrerequisiteApi = (edge: PrerequisiteEdgeInput) =>
  api.post<PrerequisiteEdge>("/lms/admin/prerequisites", edge).then((r) => r.data);

export const removePrerequisiteApi = (edge: PrerequisiteEdgeInput) =>
  api.delete("/lms/admin/prerequisites", { params: edge }).then(() => undefined);

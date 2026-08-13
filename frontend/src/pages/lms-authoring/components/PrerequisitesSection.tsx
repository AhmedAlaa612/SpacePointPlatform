import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Plus, X } from "lucide-react"
import { EmptyState, Spinner } from "@/components/ui/primitives"
import {
  listPrerequisitesApi, addPrerequisiteApi, removePrerequisiteApi,
  type PrerequisiteItemType, type PrerequisiteEdge,
} from "@/api/lms_prerequisites"
import { ItemPicker } from "@/pages/lms-authoring/components/ItemPicker"

/**
 * Inline "what does this course/mission require first" panel — replaces the
 * standalone `LmsPrerequisites.tsx` page (2026-08-12): the operator's ask
 * was to set a prerequisite from the course/mission's own page rather than
 * hunting for a separate item-picker page. `itemType`/`itemId` are fixed by
 * the host page; only the *requires* side is picked here.
 */
export function PrerequisitesSection({ itemType, itemId }: { itemType: PrerequisiteItemType; itemId: string }) {
  const queryClient = useQueryClient()
  const [requiresType, setRequiresType] = useState<PrerequisiteItemType>(itemType === "course" ? "mission" : "course")
  const [requiresId, setRequiresId] = useState("")
  const [error, setError] = useState("")

  const { data: edges = [], isLoading } = useQuery<PrerequisiteEdge[]>({
    queryKey: ["lms-admin-prerequisites", itemType, itemId],
    queryFn: () => listPrerequisitesApi(itemType, itemId),
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["lms-admin-prerequisites", itemType, itemId] })

  const addMutation = useMutation({
    mutationFn: () => addPrerequisiteApi({ item_type: itemType, item_id: itemId, requires_type: requiresType, requires_id: requiresId }),
    onSuccess: () => { setError(""); setRequiresId(""); invalidate() },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to add prerequisite"),
  })
  const removeMutation = useMutation({
    mutationFn: (edge: PrerequisiteEdge) => removePrerequisiteApi(edge),
    onSuccess: invalidate,
  })

  return (
    <div className="flex flex-col gap-3 p-4 bg-card border border-border rounded-2xl">
      <h3 className="text-sm font-medium text-foreground">Prerequisites</h3>

      {isLoading ? (
        <Spinner />
      ) : edges.length === 0 ? (
        <EmptyState title="No prerequisites yet" hint="This item is available to everyone with no gate." />
      ) : (
        <div className="flex flex-col gap-2">
          {edges.map((edge) => (
            <div key={`${edge.requires_type}-${edge.requires_id}`} className="flex items-center justify-between p-3 bg-background border border-border rounded-xl">
              <span className="text-sm text-foreground">
                {edge.requires_title}
                <span className="ml-2 text-xs text-muted-foreground uppercase tracking-wide">{edge.requires_type}</span>
              </span>
              <button
                onClick={() => removeMutation.mutate(edge)}
                className="p-1.5 rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors"
              >
                <X size={14} />
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-wrap gap-2 items-center">
        <select
          value={requiresType}
          onChange={(e) => { setRequiresType(e.target.value as PrerequisiteItemType); setRequiresId("") }}
          className="h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
        >
          <option value="course">Course</option>
          <option value="mission">Mission</option>
        </select>
        <ItemPicker
          type={requiresType} value={requiresId} onChange={setRequiresId}
          exclude={requiresType === itemType ? itemId : undefined}
        />
        <button
          onClick={() => requiresId && addMutation.mutate()}
          disabled={!requiresId || addMutation.isPending}
          className="flex items-center gap-1.5 h-10 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 transition-colors disabled:opacity-50"
        >
          <Plus size={14} /> Require
        </button>
      </div>
      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  )
}

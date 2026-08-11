import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Plus, X } from "lucide-react"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { listCoursesApi } from "@/api/lms_admin"
import { listMissionsAdminApi } from "@/api/missions_admin"
import {
  listPrerequisitesApi, addPrerequisiteApi, removePrerequisiteApi,
  type PrerequisiteItemType, type PrerequisiteEdge,
} from "@/api/lms_prerequisites"

function ItemPicker({
  type, value, onChange, exclude,
}: { type: PrerequisiteItemType; value: string; onChange: (id: string) => void; exclude?: string }) {
  const { data: courses = [] } = useQuery({ queryKey: ["lms-admin-courses"], queryFn: listCoursesApi, enabled: type === "course" })
  const { data: missions = [] } = useQuery({ queryKey: ["missions-admin-list"], queryFn: listMissionsAdminApi, enabled: type === "mission" })
  const options = type === "course" ? courses : missions
  return (
    <select
      value={value} onChange={(e) => onChange(e.target.value)}
      className="h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
    >
      <option value="">Select {type === "course" ? "a course" : "a mission"}…</option>
      {options.filter((o) => o.id !== exclude).map((o) => (
        <option key={o.id} value={o.id}>{o.title}</option>
      ))}
    </select>
  )
}

/** 7B-2 (Missions Phase 2B, 2026-08-12) — the first admin authoring surface
 * either mission-mission or course-involving prerequisite edges have ever
 * had (mission_prerequisites rows were only ever seeded directly). One
 * item's prerequisites at a time, matching LmsCurriculum's pattern; a
 * course and a mission are interchangeable "items" here (D2) — either can
 * require either. */
export default function LmsPrerequisites() {
  const queryClient = useQueryClient()
  const [itemType, setItemType] = useState<PrerequisiteItemType>("course")
  const [itemId, setItemId] = useState("")
  const [requiresType, setRequiresType] = useState<PrerequisiteItemType>("course")
  const [requiresId, setRequiresId] = useState("")
  const [error, setError] = useState("")

  const { data: edges = [], isLoading } = useQuery<PrerequisiteEdge[]>({
    queryKey: ["lms-admin-prerequisites", itemType, itemId],
    queryFn: () => listPrerequisitesApi(itemType, itemId),
    enabled: !!itemId,
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
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Prerequisites"
        subtitle="What a course or mission requires first — either kind can require either kind."
      />

      <div className="flex flex-wrap items-center gap-3 max-w-2xl">
        <select
          value={itemType}
          onChange={(e) => { setItemType(e.target.value as PrerequisiteItemType); setItemId("") }}
          className="h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
        >
          <option value="course">Course</option>
          <option value="mission">Mission</option>
        </select>
        <ItemPicker type={itemType} value={itemId} onChange={setItemId} />
      </div>

      {!itemId ? (
        <EmptyState title="Pick an item" hint="Choose a course or mission above to manage what it requires." />
      ) : isLoading ? (
        <Spinner />
      ) : (
        <div className="flex flex-col gap-4 max-w-xl">
          {edges.length === 0 ? (
            <EmptyState title="No prerequisites yet" hint="This item is available to everyone with no gate." />
          ) : (
            <div className="flex flex-col gap-2">
              {edges.map((edge) => (
                <div key={`${edge.requires_type}-${edge.requires_id}`} className="flex items-center justify-between p-3 bg-card border border-border rounded-xl">
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
              className="h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
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
      )}
    </div>
  )
}

import { useQuery } from "@tanstack/react-query"
import { listCoursesApi } from "@/api/lms_admin"
import { listMissionsAdminApi } from "@/api/missions_admin"
import type { PrerequisiteItemType } from "@/api/lms_prerequisites"

/** Course-or-mission dropdown, shared by the prerequisites picker
 * (originally `LmsPrerequisites.tsx`, extracted 2026-08-12 so course/mission
 * detail pages can mount an inline "add prerequisite" picker too). */
export function ItemPicker({
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

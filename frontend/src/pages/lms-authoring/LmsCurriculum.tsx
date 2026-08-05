import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Plus, X } from "lucide-react"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { getProgramsApi } from "@/api/sessions/programs"
import { listCoursesApi, listCurriculumApi, addCurriculumEntryApi, removeCurriculumEntryApi, type CurriculumEntry } from "@/api/lms_admin"
import type { Program } from "@/types/sessions"

/** D5: "every program gets an LMS view" — program → ordered courses. Own
 * page rather than a tab on Programs.tsx, matching LM1-13's "own pages"
 * instruction; program_curriculum is a distinct concern from the program
 * record itself. */
export default function LmsCurriculum() {
  const queryClient = useQueryClient()
  const [programId, setProgramId] = useState<string>("")
  const [addingCourseId, setAddingCourseId] = useState("")
  const [error, setError] = useState("")

  const { data: programs = [], isLoading: programsLoading } = useQuery<Program[]>({
    queryKey: ["sessions-programs"],
    queryFn: getProgramsApi,
  })
  const { data: courses = [] } = useQuery({ queryKey: ["lms-admin-courses"], queryFn: listCoursesApi })
  const { data: curriculum = [], isLoading: curriculumLoading } = useQuery<CurriculumEntry[]>({
    queryKey: ["lms-admin-curriculum", programId],
    queryFn: () => listCurriculumApi(programId),
    enabled: !!programId,
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["lms-admin-curriculum", programId] })

  const addMutation = useMutation({
    mutationFn: (courseId: string) => addCurriculumEntryApi(programId, { course_id: courseId }),
    onSuccess: () => { setError(""); setAddingCourseId(""); invalidate() },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to add course"),
  })
  const removeMutation = useMutation({
    mutationFn: (courseId: string) => removeCurriculumEntryApi(programId, courseId),
    onSuccess: invalidate,
  })

  const coursesById = Object.fromEntries(courses.map((c) => [c.id, c]))
  const availableCourses = courses.filter((c) => !curriculum.some((entry) => entry.course_id === c.id))

  if (programsLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="LMS Curriculum" subtitle="Which courses each program's students see in the LMS, and in what order." />

      <div className="max-w-sm">
        <select
          value={programId} onChange={(e) => setProgramId(e.target.value)}
          className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
        >
          <option value="">Select a program…</option>
          {programs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>

      {!programId ? (
        <EmptyState title="Pick a program" hint="Choose a program above to manage its curriculum." />
      ) : curriculumLoading ? (
        <Spinner />
      ) : (
        <div className="flex flex-col gap-4 max-w-xl">
          {curriculum.length === 0 ? (
            <EmptyState title="No courses in this program's curriculum yet" />
          ) : (
            <div className="flex flex-col gap-2">
              {curriculum.map((entry) => (
                <div key={entry.id} className="flex items-center justify-between p-3 bg-card border border-border rounded-xl">
                  <span className="text-sm text-foreground">
                    {entry.position}. {coursesById[entry.course_id]?.title ?? entry.course_id}
                  </span>
                  <button
                    onClick={() => removeMutation.mutate(entry.course_id)}
                    className="p-1.5 rounded-lg text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors"
                  >
                    <X size={14} />
                  </button>
                </div>
              ))}
            </div>
          )}

          {availableCourses.length > 0 && (
            <div className="flex gap-2">
              <select
                value={addingCourseId} onChange={(e) => setAddingCourseId(e.target.value)}
                className="flex-1 h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
              >
                <option value="">Add a course…</option>
                {availableCourses.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
              </select>
              <button
                onClick={() => addingCourseId && addMutation.mutate(addingCourseId)}
                disabled={!addingCourseId || addMutation.isPending}
                className="flex items-center gap-1.5 h-10 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 transition-colors disabled:opacity-50"
              >
                <Plus size={14} /> Add
              </button>
            </div>
          )}
          {error && <p className="text-xs text-red-500">{error}</p>}
        </div>
      )}
    </div>
  )
}

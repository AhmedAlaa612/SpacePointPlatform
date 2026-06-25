import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Plus, ChevronRight, GraduationCap, Users, Clock, CheckSquare } from "lucide-react"
import { useAuth } from "@/context/AuthContext"
import { getTeacherSessionsApi, createSessionApi } from "@/api/ambassadors/network"
import { getTeacherSummaryApi } from "@/api/ambassadors/teacher"
import type { TeacherSession } from "@/types/ambassadors"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { PageHeader, Spinner, EmptyState, StatusPill, StatCard } from "@/pages/ambassadors/components/common"
import { SessionDetailModal } from "@/pages/ambassadors/components/SessionDetailModal"

export default function TeacherPortal() {
  const { currentUser } = useAuth()
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [selected, setSelected] = useState<TeacherSession | null>(null)

  if (!currentUser) return <Spinner />

  const teacherId = currentUser.id

  const { data: sessions = [], isLoading } = useQuery({
    queryKey: ["my-sessions", teacherId],
    queryFn: () => getTeacherSessionsApi(teacherId),
    enabled: !!teacherId,
  })
  const { data: summary } = useQuery({ queryKey: ["teacher-summary"], queryFn: getTeacherSummaryApi })

  const upcoming = sessions.filter((s) => s.status === "pending" || s.status === "approved")
  const past = sessions.filter((s) => ["done", "rejected", "cancelled"].includes(s.status))

  const Row = ({ s }: { s: TeacherSession }) => (
    <Card>
      <CardContent className="p-4 sm:p-5">
        <button onClick={() => setSelected(s)} className="w-full flex items-center justify-between gap-3 text-left">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <p className="font-semibold text-foreground">{s.title}</p>
              <StatusPill status={s.status} />
              {s.material_link && <span className="text-xs text-green-600 font-semibold">Material ready</span>}
              {s.status === "approved" && s.material_sent && <span className="w-2 h-2 rounded-full bg-heliotrope" title="Ready to mark delivered" />}
            </div>
            <p className="text-xs text-gray-400 mt-1">
              {new Date(s.date).toLocaleDateString()} · planned {s.planned_students}
              {s.status === "done" && ` · attended ${s.attended_students}`}
            </p>
          </div>
          <ChevronRight size={18} className="text-gray-300 shrink-0" />
        </button>
      </CardContent>
    </Card>
  )

  return (
    <div>
      <PageHeader
        title="Teacher Portal"
        subtitle="Schedule sessions, log your impact and see how you rank."
        action={<Button onClick={() => setOpen(true)}><Plus size={16} /> New session</Button>}
      />

      {/* Impact header */}
      {summary && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-6">
          <StatCard icon={<GraduationCap size={20} />} label="Sessions Delivered" value={summary.stats.sessions_done} />
          <StatCard icon={<Users size={20} />} label="Students Reached" value={summary.stats.students_reached} />
          <StatCard icon={<Clock size={20} />} label="Upcoming" value={summary.stats.upcoming} />
          <StatCard icon={<CheckSquare size={20} />} label="Awaiting Approval" value={summary.stats.pending} />
        </div>
      )}

      {isLoading ? (
        <Spinner />
      ) : (
        <div className="space-y-6">
          <section>
            <h2 className="text-sm font-semibold text-muted-foreground mb-2">Upcoming & pending</h2>
            {upcoming.length === 0 ? (
              <Card><CardContent className="p-0"><EmptyState title="Nothing upcoming" hint="Submit a session for your ambassador to approve." /></CardContent></Card>
            ) : (
              <div className="flex flex-col gap-3">{upcoming.map((s) => <Row key={s.id} s={s} />)}</div>
            )}
          </section>

          {past.length > 0 && (
            <section>
              <h2 className="text-sm font-semibold text-muted-foreground mb-2">Past</h2>
              <div className="flex flex-col gap-3">{past.map((s) => <Row key={s.id} s={s} />)}</div>
            </section>
          )}

        </div>
      )}

      {selected && <SessionDetailModal session={selected} onClose={() => setSelected(null)} />}

      <NewSessionModal
        open={open}
        teacherId={teacherId}
        onClose={() => setOpen(false)}
        onSuccess={() => { qc.invalidateQueries({ queryKey: ["my-sessions"] }); qc.invalidateQueries({ queryKey: ["teacher-summary"] }) }}
      />
    </div>
  )
}

function NewSessionModal({
  open, teacherId, onClose, onSuccess,
}: { open: boolean; teacherId: string; onClose: () => void; onSuccess: () => void }) {
  const [form, setForm] = useState({ title: "", description: "", date: "", planned_students: 20 })
  const [error, setError] = useState("")
  const mutation = useMutation({
    mutationFn: () =>
      createSessionApi(teacherId, {
        title: form.title,
        description: form.description || undefined,
        date: new Date(form.date).toISOString(),
        planned_students: Number(form.planned_students),
      }),
    onSuccess: () => { onSuccess(); onClose() },
    onError: (e: any) => setError(e?.response?.data?.detail || "Failed to create session."),
  })

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>New session</DialogTitle></DialogHeader>
        <form onSubmit={(e) => { e.preventDefault(); setError(""); mutation.mutate() }} className="flex flex-col gap-3 mt-2">
          <input className="input" placeholder="Session title" value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} required />
          <textarea className="input h-20 py-2 resize-none" placeholder="Description (what's the session about?)" value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} />
          <input className="input" type="datetime-local" value={form.date} onChange={(e) => setForm((f) => ({ ...f, date: e.target.value }))} required />
          <input className="input" type="number" min={0} placeholder="Planned students" value={form.planned_students} onChange={(e) => setForm((f) => ({ ...f, planned_students: Number(e.target.value) }))} />
          {error && <p className="text-sm text-red-500">{error}</p>}
          <Button type="submit" disabled={mutation.isPending} className="mt-1">{mutation.isPending ? "Submitting…" : "Submit session"}</Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}

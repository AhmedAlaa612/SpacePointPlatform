import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { getAllSessionsApi } from "@/api/ambassadors/network"
import type { TeacherSession } from "@/types/ambassadors"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { EmptyState, PageHeader, Spinner, StatusPill } from "@/pages/ambassadors/components/common"
import { SessionDetailModal } from "@/pages/ambassadors/components/SessionDetailModal"

export default function AmbassadorsAdminSessions() {
  return (
    <div>
      <PageHeader title="Ambassadors Admin" subtitle="All teacher sessions across the network." />
      <SessionsAdmin />
    </div>
  )
}

function SessionsAdmin() {
  const [selected, setSelected] = useState<TeacherSession | null>(null)
  const { data: sessions = [], isLoading } = useQuery({ queryKey: ["admin-sessions"], queryFn: getAllSessionsApi })
  if (isLoading) return <Spinner />
  if (!sessions.length) return <EmptyState title="No sessions yet" />

  const sorted = [...sessions].sort((a, b) => +new Date(a.date) - +new Date(b.date))

  return (
    <Card>
      <CardHeader><CardTitle>All sessions</CardTitle></CardHeader>
      <CardContent>
        <div className="overflow-x-auto -mx-1">
          <table className="w-full text-sm min-w-[640px]">
            <thead>
              <tr className="text-left text-muted-foreground border-b border-border">
                <th className="py-2.5 pr-3 font-semibold">Date</th>
                <th className="py-2.5 pr-3 font-semibold">Session</th>
                <th className="py-2.5 pr-3 font-semibold">Teacher</th>
                <th className="py-2.5 pr-3 font-semibold">Ambassador</th>
                <th className="py-2.5 pr-3 font-semibold text-center">Students</th>
                <th className="py-2.5 pr-3 font-semibold text-right">Status</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((s) => (
                <tr key={s.id} onClick={() => setSelected(s)} className="border-b border-border/50 last:border-0 cursor-pointer hover:bg-muted">
                  <td className="py-2.5 pr-3 text-muted-foreground whitespace-nowrap">{new Date(s.date).toLocaleDateString()}</td>
                  <td className="py-2.5 pr-3 font-medium">{s.title}</td>
                  <td className="py-2.5 pr-3 text-muted-foreground">{(s as any).teacher_name ?? "—"}</td>
                  <td className="py-2.5 pr-3 text-muted-foreground">{(s as any).ambassador_name ?? "—"}</td>
                  <td className="py-2.5 pr-3 text-center">{s.status === "done" ? s.attended_students : s.planned_students}</td>
                  <td className="py-2.5 pr-3 text-right"><StatusPill status={s.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {selected && <SessionDetailModal session={selected} role="manager" onClose={() => setSelected(null)} />}
      </CardContent>
    </Card>
  )
}

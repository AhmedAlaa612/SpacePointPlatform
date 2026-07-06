import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { MessageSquare } from "lucide-react"
import { getLeadsApi, updateLeadStatusApi } from "@/api/ambassadors/leads"
import type { Lead } from "@/types/ambassadors"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { EmptyState, PageHeader, Spinner, StatusPill } from "@/pages/ambassadors/components/common"
import { LeadDetailModal } from "@/pages/ambassadors/components/LeadDetailModal"

export default function AmbassadorsAdminLeads() {
  return (
    <div>
      <PageHeader title="Ambassadors Admin" subtitle="Review and progress submitted leads." />
      <LeadsAdmin />
    </div>
  )
}

function LeadsAdmin() {
  const qc = useQueryClient()
  const [selected, setSelected] = useState<Lead | null>(null)
  const { data: leads = [], isLoading } = useQuery({ queryKey: ["admin-leads"], queryFn: getLeadsApi })
  const status = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => updateLeadStatusApi(id, status),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin-leads"] }); qc.invalidateQueries({ queryKey: ["dashboard"] }) },
  })

  if (isLoading) return <Spinner />
  if (!leads.length) return <EmptyState title="No leads submitted yet" />

  return (
    <div className="flex flex-col gap-3">
      {leads.map((l) => (
        <Card key={l.id}>
          <CardContent className="p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <p className="font-semibold">{l.company || l.contact_name}</p>
                <StatusPill status={l.status} />
              </div>
              <p className="text-xs text-muted-foreground mt-1">{l.contact_name} · {l.type} · by {(l as any).ambassador_name ?? "—"}</p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <Button size="sm" variant="outline" onClick={() => setSelected(l)}><MessageSquare size={14} className="mr-1.5" /> Details</Button>
              <select className="input !w-auto" value={l.status} onChange={(e) => status.mutate({ id: l.id, status: e.target.value })}>
                <option value="submitted">Submitted</option>
                <option value="in review">In review</option>
                <option value="converted">Converted (awards points)</option>
                <option value="closed">Closed</option>
              </select>
            </div>
          </CardContent>
        </Card>
      ))}
      {selected && <LeadDetailModal lead={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}

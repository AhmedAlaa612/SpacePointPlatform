import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Plus, MessageSquare } from "lucide-react"
import { getLeadsApi, createLeadApi } from "@/api/ambassadors/leads"
import type { Lead } from "@/types/ambassadors"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { PageHeader, Spinner, EmptyState, StatusPill } from "@/pages/ambassadors/components/common"
import { LeadDetailModal } from "@/pages/ambassadors/components/LeadDetailModal"

export default function Leads() {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [selected, setSelected] = useState<Lead | null>(null)
  const { data: leads = [], isLoading } = useQuery({ queryKey: ["leads"], queryFn: getLeadsApi })

  return (
    <div>
      <PageHeader
        title="Leads"
        subtitle="Submit B2B and B2C leads. Converted leads earn you points."
        action={<Button onClick={() => setOpen(true)}><Plus size={16} /> New lead</Button>}
      />

      {isLoading ? (
        <Spinner />
      ) : leads.length === 0 ? (
        <Card><CardContent className="p-0"><EmptyState title="No leads yet" hint="Submit your first business lead to grow the network." /></CardContent></Card>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {leads.map((l) => (
            <Card key={l.id}>
              <CardContent className="p-5">
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div className="min-w-0">
                    <p className="font-semibold text-foreground truncate">{l.company || l.contact_name}</p>
                    <p className="text-sm text-muted-foreground truncate">{l.company ? l.contact_name : "Individual"}</p>
                  </div>
                  <StatusPill status={l.status} />
                </div>
                <p className="text-xs text-muted-foreground uppercase tracking-wide">{l.type}</p>
                {l.notes && <p className="text-sm text-muted-foreground dark:text-zinc-300 mt-2 line-clamp-3">{l.notes}</p>}
                <div className="flex items-center justify-between mt-3">
                  <p className="text-xs text-gray-400">{new Date(l.created_at).toLocaleDateString()}</p>
                  <Button size="sm" variant="outline" onClick={() => setSelected(l)}>
                    <MessageSquare size={14} /> Details & comments
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {selected && <LeadDetailModal lead={selected} onClose={() => setSelected(null)} />}
      <NewLeadModal open={open} onClose={() => setOpen(false)} onSuccess={() => qc.invalidateQueries({ queryKey: ["leads"] })} />
    </div>
  )
}

function NewLeadModal({ open, onClose, onSuccess }: { open: boolean; onClose: () => void; onSuccess: () => void }) {
  const [form, setForm] = useState({ contact_name: "", company: "", type: "B2B", notes: "" })
  const [error, setError] = useState("")
  const mutation = useMutation({
    mutationFn: () => createLeadApi({
      contact_name: form.contact_name,
      type: form.type,
      notes: form.notes || undefined,
      company: form.type === "B2B" ? form.company : undefined,
    }),
    onSuccess: () => { onSuccess(); onClose(); setForm({ contact_name: "", company: "", type: "B2B", notes: "" }) },
    onError: (e: any) => setError(e?.response?.data?.detail || "Failed to submit lead."),
  })

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>New lead</DialogTitle></DialogHeader>
        <form
          onSubmit={(e) => { e.preventDefault(); setError(""); mutation.mutate() }}
          className="flex flex-col gap-3 mt-2"
        >
          <select className="input" value={form.type} onChange={(e) => setForm((f) => ({ ...f, type: e.target.value }))}>
            <option value="B2B">B2B — a business / school</option>
            <option value="B2C">B2C — an individual</option>
          </select>
          <input
            className="input"
            placeholder={form.type === "B2B" ? "Contact name" : "Customer name"}
            value={form.contact_name}
            onChange={(e) => setForm((f) => ({ ...f, contact_name: e.target.value }))}
            required
          />
          {form.type === "B2B" && (
            <input className="input" placeholder="Company / organization" value={form.company} onChange={(e) => setForm((f) => ({ ...f, company: e.target.value }))} required />
          )}
          <textarea className="input h-24 py-2 resize-none" placeholder="Notes (optional)" value={form.notes} onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))} />
          {error && <p className="text-sm text-red-500">{error}</p>}
          <Button type="submit" disabled={mutation.isPending} className="mt-1">
            {mutation.isPending ? "Submitting…" : "Submit lead"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}

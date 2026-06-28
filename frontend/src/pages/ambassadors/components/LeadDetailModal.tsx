import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Send, Pencil, Trash2 } from "lucide-react"
import type { Lead } from "@/types/ambassadors"
import { getLeadCommentsApi, addLeadCommentApi, editLeadApi, deleteLeadApi } from "@/api/ambassadors/leads"
import { useAuth } from "@/context/AuthContext"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { StatusPill, Spinner } from "./common"

export function LeadDetailModal({ lead, onClose }: { lead: Lead; onClose: () => void }) {
  const qc = useQueryClient()
  const { currentUser } = useAuth()
  const [text, setText] = useState("")
  const [editing, setEditing] = useState(false)
  const [edit, setEdit] = useState({
    contact_name: lead.contact_name,
    company: lead.company ?? "",
    type: lead.type,
    notes: lead.notes ?? "",
  })
  const { data: comments = [], isLoading } = useQuery({
    queryKey: ["lead-comments", lead.id],
    queryFn: () => getLeadCommentsApi(lead.id),
  })
  const refreshLeads = () => {
    qc.invalidateQueries({ queryKey: ["leads"] })
    qc.invalidateQueries({ queryKey: ["admin-leads"] })
  }
  const add = useMutation({
    mutationFn: () => addLeadCommentApi(lead.id, text.trim()),
    onSuccess: () => {
      setText("")
      qc.invalidateQueries({ queryKey: ["lead-comments", lead.id] })
      qc.invalidateQueries({ queryKey: ["notifications"] })
    },
  })
  const save = useMutation({
    mutationFn: () => editLeadApi(lead.id, {
      contact_name: edit.contact_name,
      company: edit.type === "B2B" ? edit.company : "",
      type: edit.type,
      notes: edit.notes,
    }),
    onSuccess: () => { refreshLeads(); onClose() },
  })
  const withdraw = useMutation({
    mutationFn: () => deleteLeadApi(lead.id),
    onSuccess: () => { refreshLeads(); onClose() },
  })

  const isAdmin = currentUser?.role === "admin"
  // Ambassadors may fix/withdraw their own lead while it hasn't been picked up yet.
  const canEdit = isAdmin || lead.status === "submitted"
  const canWithdraw = isAdmin || ["submitted", "in review"].includes(lead.status)

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {lead.company || lead.contact_name} <StatusPill status={lead.status} />
          </DialogTitle>
        </DialogHeader>

        {editing ? (
          <form onSubmit={(e) => { e.preventDefault(); save.mutate() }} className="mt-2 flex flex-col gap-3">
            <select className="input" value={edit.type} onChange={(e) => setEdit((s) => ({ ...s, type: e.target.value }))}>
              <option value="B2B">B2B — a business / school</option>
              <option value="B2C">B2C — an individual</option>
            </select>
            <input className="input" placeholder="Contact name" value={edit.contact_name} onChange={(e) => setEdit((s) => ({ ...s, contact_name: e.target.value }))} required />
            {edit.type === "B2B" && (
              <input className="input" placeholder="Company / organization" value={edit.company} onChange={(e) => setEdit((s) => ({ ...s, company: e.target.value }))} required />
            )}
            <textarea className="input h-20 py-2 resize-none" placeholder="Notes" value={edit.notes} onChange={(e) => setEdit((s) => ({ ...s, notes: e.target.value }))} />
            <div className="flex gap-2">
              <Button type="submit" variant="default" disabled={save.isPending}>{save.isPending ? "Saving…" : "Save changes"}</Button>
              <Button type="button" variant="outline" onClick={() => setEditing(false)}>Cancel</Button>
            </div>
          </form>
        ) : (
        <div className="mt-2 space-y-3">
          <div className="text-sm">
            <p className="text-muted-foreground">Contact: <span className="text-foreground font-medium">{lead.contact_name}</span></p>
            <p className="text-muted-foreground">Type: <span className="text-foreground font-medium uppercase">{lead.type}</span></p>
            {lead.ambassador_name && <p className="text-muted-foreground">Ambassador: <span className="text-foreground font-medium">{lead.ambassador_name}</span></p>}
          </div>
          {lead.notes && (
            <div className="rounded-lg bg-muted/50 p-3 text-sm text-foreground border border-border whitespace-pre-wrap">{lead.notes}</div>
          )}

          {(canEdit || canWithdraw) && (
            <div className="flex gap-2">
              {canEdit && <Button variant="ghost" size="sm" onClick={() => setEditing(true)}><Pencil size={14} /> Edit</Button>}
              {canWithdraw && (
                <Button variant="ghost" size="sm" disabled={withdraw.isPending}
                  onClick={() => { if (confirm("Withdraw this lead? It will be permanently removed.")) withdraw.mutate() }}>
                  <Trash2 size={14} /> Withdraw
                </Button>
              )}
            </div>
          )}

          {/* Comment thread */}
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">Comments</p>
            <div className="max-h-64 overflow-y-auto space-y-2 pr-1">
              {isLoading ? (
                <Spinner />
              ) : comments.length === 0 ? (
                <p className="text-sm text-muted-foreground py-3 text-center">No comments yet.</p>
              ) : (
                comments.map((c) => (
                  <div key={c.id} className="rounded-lg border border-border p-2.5">
                    <div className="flex items-center justify-between gap-2 mb-0.5">
                      <span className="text-xs font-semibold text-foreground">
                        {c.author_name ?? "Unknown"}
                        {c.author_role === "admin" && <span className="ml-1.5 text-[10px] font-bold text-heliotrope uppercase">Admin</span>}
                      </span>
                      <span className="text-[11px] text-muted-foreground">{new Date(c.created_at).toLocaleString()}</span>
                    </div>
                    <p className="text-sm text-foreground whitespace-pre-wrap">{c.body}</p>
                  </div>
                ))
              )}
            </div>
          </div>

          <form
            onSubmit={(e) => { e.preventDefault(); if (text.trim()) add.mutate() }}
            className="flex items-end gap-2 pt-1"
          >
            <textarea
              className="input h-11 py-2 resize-none flex-1"
              placeholder="Write a comment…"
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (text.trim()) add.mutate() } }}
            />
            <Button type="submit" size="icon" disabled={add.isPending || !text.trim()}><Send size={16} /></Button>
          </form>
        </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

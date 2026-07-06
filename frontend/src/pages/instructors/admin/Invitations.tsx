import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Plus, Trash2 } from "lucide-react"
import {
  createInvitationApi, deleteInvitationApi, listInvitationsApi, updateInvitationApi,
} from "@/api/instructors/admin"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { EmptyState, PageHeader, Spinner } from "@/pages/instructors/components/common"

export default function InstructorsAdminInvitations() {
  const qc = useQueryClient()
  const [code, setCode] = useState("")
  const [maxUses, setMaxUses] = useState(20)

  const { data: invitations, isLoading } = useQuery({ queryKey: ["admin-invitations"], queryFn: listInvitationsApi })

  const create = useMutation({
    mutationFn: () => createInvitationApi({ code, max_uses: maxUses }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin-invitations"] }); setCode("") },
  })
  const toggleActive = useMutation({
    mutationFn: (params: { id: string; is_active: boolean }) => updateInvitationApi(params.id, { is_active: params.is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-invitations"] }),
  })
  const remove = useMutation({
    mutationFn: (id: string) => deleteInvitationApi(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-invitations"] }),
  })

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Invitation Codes" subtitle="Create and manage access codes for the Apply gate." />

      <Card>
        <CardContent className="p-5 flex flex-col sm:flex-row gap-3">
          <div className="flex-1"><input className="input" placeholder="Invitation code" value={code} onChange={(e) => setCode(e.target.value)} /></div>
          <div className="w-32"><input className="input" type="number" placeholder="Max uses" value={maxUses} onChange={(e) => setMaxUses(Number(e.target.value))} /></div>
          <Button onClick={() => create.mutate()} disabled={!code || create.isPending}>
            <Plus size={14} className="mr-1" /> Create
          </Button>
        </CardContent>
      </Card>

      {(invitations ?? []).length === 0 ? (
        <EmptyState title="No invitation codes yet" />
      ) : (
        <div className="space-y-2">
          {invitations!.map((i) => (
            <div key={i.id} className="flex items-center justify-between gap-3 p-3 rounded-lg border bg-card">
              <div>
                <p className="text-sm font-mono font-medium">{i.code}</p>
                <p className="text-xs text-muted-foreground">{i.used_count} / {i.max_uses} used</p>
              </div>
              <div className="flex items-center gap-2">
                <Button size="sm" variant="outline" onClick={() => toggleActive.mutate({ id: i.id, is_active: !i.is_active })}>
                  {i.is_active ? "Active" : "Inactive"}
                </Button>
                <button onClick={() => remove.mutate(i.id)} className="p-2 text-muted-foreground hover:text-destructive">
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

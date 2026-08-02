import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Plus, Trash2 } from "lucide-react"
import {
  createInvitationApi, deleteInvitationApi, listInvitationsApi, updateInvitationApi,
} from "@/api/instructors/admin"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { EmptyState, PageHeader, Spinner } from "@/pages/instructors/components/common"
import { useToast } from "@/components/ui/toast"

export default function InstructorsAdminInvitations() {
  const qc = useQueryClient()
  const toast = useToast()
  const [code, setCode] = useState("")
  const [maxUses, setMaxUses] = useState(20)

  const { data: invitations, isLoading } = useQuery({ queryKey: ["admin-invitations"], queryFn: listInvitationsApi })

  const create = useMutation({
    mutationFn: () => createInvitationApi({ code, max_uses: maxUses }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-invitations"] })
      toast.success("Invitation code created")
      setCode("")
    },
  })

  const updateMutation = useMutation({
    mutationFn: (params: { id: string; is_active?: boolean; max_uses?: number }) =>
      updateInvitationApi(params.id, { is_active: params.is_active, max_uses: params.max_uses }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-invitations"] })
      toast.success("Invitation updated")
    },
  })

  const remove = useMutation({
    mutationFn: (id: string) => deleteInvitationApi(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-invitations"] })
      toast.success("Invitation deleted")
    },
  })

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Invitation Codes" subtitle="Create and manage access codes for the Apply gate." />

      <Card>
        <CardContent className="p-5 flex flex-col sm:flex-row gap-3">
          <div className="flex-1">
            <input className="input" placeholder="Invitation code" value={code} onChange={(e) => setCode(e.target.value)} />
          </div>
          <div className="w-full sm:w-32">
            <input className="input" type="number" min={1} placeholder="Max uses" value={maxUses} onChange={(e) => setMaxUses(Number(e.target.value))} />
          </div>
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
            <InvitationRow
              key={i.id}
              invitation={i}
              onToggleActive={() => updateMutation.mutate({ id: i.id, is_active: !i.is_active })}
              onUpdateLimit={(limit) => updateMutation.mutate({ id: i.id, max_uses: limit })}
              onDelete={() => remove.mutate(i.id)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function InvitationRow({ invitation: i, onToggleActive, onUpdateLimit, onDelete }: {
  invitation: any
  onToggleActive: () => void
  onUpdateLimit: (limit: number) => void
  onDelete: () => void
}) {
  const [limit, setLimit] = useState(i.max_uses)

  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5 rounded-xl border border-border bg-card">
      <div>
        <p className="text-sm font-mono font-bold text-foreground">{i.code}</p>
        <p className="text-xs text-muted-foreground mt-0.5">{i.used_count} used</p>
      </div>
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-medium text-muted-foreground">Limit:</span>
          <input
            type="number"
            min={1}
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            onBlur={() => {
              if (limit > 0 && limit !== i.max_uses) {
                onUpdateLimit(limit)
              }
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.currentTarget.blur()
              }
            }}
            className="w-20 h-8 px-2 bg-background border border-border rounded-lg text-xs font-semibold text-foreground focus:outline-none focus:border-primary transition-colors text-right tabular-nums"
          />
        </div>
        <Button
          size="sm"
          variant={i.is_active ? "outline" : "secondary"}
          onClick={onToggleActive}
          className="h-8"
        >
          {i.is_active ? "Active" : "Inactive"}
        </Button>
        <button
          onClick={onDelete}
          className="p-1.5 text-muted-foreground hover:text-destructive transition-colors"
          title="Delete code"
        >
          <Trash2 size={16} />
        </button>
      </div>
    </div>
  )
}

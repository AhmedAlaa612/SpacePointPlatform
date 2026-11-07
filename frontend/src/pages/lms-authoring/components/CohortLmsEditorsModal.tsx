import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { UserPlus, Trash2 } from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { useToast } from "@/components/ui/toast"
import {
  getCohortLmsEditorsApi,
  grantCohortLmsEditorApi,
  revokeCohortLmsEditorApi,
} from "@/api/lms_admin"

interface CohortLmsEditorsModalProps {
  cohortId: string
  cohortName: string
  open: boolean
  onClose: () => void
}

export function CohortLmsEditorsModal({
  cohortId,
  cohortName,
  open,
  onClose,
}: CohortLmsEditorsModalProps) {
  const queryClient = useQueryClient()
  const toast = useToast()
  const [selectedUserId, setSelectedUserId] = useState<string>("")

  const { data, isLoading } = useQuery({
    queryKey: ["cohort-lms-editors", cohortId],
    queryFn: () => getCohortLmsEditorsApi(cohortId),
    enabled: open && !!cohortId,
  })

  const grantMutation = useMutation({
    mutationFn: (userId: string) => grantCohortLmsEditorApi(cohortId, userId),
    onSuccess: () => {
      setSelectedUserId("")
      void queryClient.invalidateQueries({ queryKey: ["cohort-lms-editors", cohortId] })
      toast.success("Instructor access granted")
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail || "Failed to grant access")
    },
  })

  const revokeMutation = useMutation({
    mutationFn: (userId: string) => revokeCohortLmsEditorApi(cohortId, userId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["cohort-lms-editors", cohortId] })
      toast.success("Instructor access revoked")
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail || "Failed to revoke access")
    },
  })

  const editors = data?.editors || []
  const assignedIds = new Set(editors.map((e) => e.user_id))
  const unassignedInstructors = (data?.eligible_instructors || []).filter(
    (ins) => !assignedIds.has(ins.id)
  )

  const handleAdd = () => {
    if (!selectedUserId) return
    grantMutation.mutate(selectedUserId)
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-md p-6 bg-card text-card-foreground border border-border rounded-xl">
        <DialogHeader className="pb-3 border-b border-border">
          <DialogTitle className="text-base font-semibold">
            LMS Instructors — {cohortName}
          </DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-4 py-2">
          {/* Add form */}
          <div className="flex items-center gap-2">
            <select
              value={selectedUserId}
              onChange={(e) => setSelectedUserId(e.target.value)}
              disabled={isLoading || grantMutation.isPending}
              className="flex-1 h-9 px-3 rounded-lg border border-border bg-background text-foreground text-sm focus:outline-none focus:border-primary"
            >
              <option value="">Select instructor...</option>
              {unassignedInstructors.map((ins) => (
                <option key={ins.id} value={ins.id}>
                  {ins.full_name} {ins.email ? `(${ins.email})` : ""}
                </option>
              ))}
            </select>
            <Button
              type="button"
              size="sm"
              disabled={!selectedUserId || grantMutation.isPending}
              onClick={handleAdd}
              className="h-9 px-3 shrink-0"
            >
              <UserPlus className="w-4 h-4 mr-1.5" />
              Add
            </Button>
          </div>

          {/* Editors list */}
          <div className="flex flex-col gap-2 max-h-60 overflow-y-auto">
            {isLoading ? (
              <div className="text-xs text-muted-foreground py-4 text-center">Loading...</div>
            ) : editors.length === 0 ? (
              <div className="text-xs text-muted-foreground py-4 text-center border border-dashed border-border rounded-lg">
                No instructors assigned
              </div>
            ) : (
              editors.map((editor) => (
                <div
                  key={editor.id}
                  className="flex items-center justify-between gap-3 p-2.5 rounded-lg border border-border bg-muted/40"
                >
                  <div className="min-w-0 flex flex-col">
                    <span className="text-sm font-medium text-foreground truncate">
                      {editor.full_name}
                    </span>
                    <span className="text-xs text-muted-foreground truncate">
                      {editor.email}
                    </span>
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={revokeMutation.isPending}
                    onClick={() => revokeMutation.mutate(editor.user_id)}
                    className="h-7 px-2 text-destructive hover:text-destructive hover:bg-destructive/10 shrink-0"
                    title="Remove access"
                  >
                    <Trash2 className="w-3.5 h-3.5 mr-1" />
                    Remove
                  </Button>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="flex justify-end pt-2 border-t border-border">
          <Button type="button" variant="outline" size="sm" onClick={onClose}>
            Done
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

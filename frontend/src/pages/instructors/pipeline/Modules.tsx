import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate } from "@tanstack/react-router"
import { ChevronRight } from "lucide-react"
import { listModulesApi, submitApplicationApi } from "@/api/instructors/applicant"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { PageHeader, Spinner, StatusPill } from "@/pages/instructors/components/common"

export default function Modules() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { data: modules, isLoading } = useQuery({ queryKey: ["instructor-modules"], queryFn: listModulesApi })

  const submitApplication = useMutation({
    mutationFn: submitApplicationApi,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["instructor-status"] })
      void navigate({ to: "/instructors/status" })
    },
  })

  if (isLoading || !modules) return <Spinner />

  const allSubmitted = modules.every((m) => m.submission_status && m.submission_status !== "rejected")

  return (
    <div>
      <PageHeader
        title="Phase 1 — Checklist Modules"
        subtitle="Work through each module's checklist, then upload your write-up."
        action={
          allSubmitted ? (
            <Button onClick={() => submitApplication.mutate()} disabled={submitApplication.isPending}>
              {submitApplication.isPending ? "Submitting…" : "Submit application"}
            </Button>
          ) : undefined
        }
      />
      {submitApplication.isError && (
        <p className="text-sm text-destructive mb-4">
          {(submitApplication.error as any)?.response?.data?.detail || "Could not submit application."}
        </p>
      )}
      <div className="flex flex-col gap-3">
        {modules.map((m) => (
          <Link key={m.id} to="/instructors/modules/$moduleId" params={{ moduleId: m.id }}>
            <Card className="hover:border-primary transition-colors">
              <CardContent className="p-4 flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-semibold text-foreground">{m.title}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {m.completed_count} / {m.item_count} items checked
                  </p>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  {m.submission_status && <StatusPill status={m.submission_status} />}
                  <ChevronRight className="text-muted-foreground" size={18} />
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  )
}

import { useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useParams } from "@tanstack/react-router"
import { ArrowLeft, Check, Upload } from "lucide-react"
import { moduleDetailApi, submitModuleApi, toggleChecklistItemApi } from "@/api/instructors/applicant"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { PageHeader, Spinner, StatusPill } from "@/pages/instructors/components/common"

export default function ModuleDetail() {
  const { moduleId } = useParams({ strict: false }) as { moduleId: string }
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [notes, setNotes] = useState("")

  const { data: module, isLoading } = useQuery({
    queryKey: ["instructor-module", moduleId],
    queryFn: () => moduleDetailApi(moduleId),
  })

  const toggle = useMutation({
    mutationFn: toggleChecklistItemApi,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["instructor-module", moduleId] }),
  })

  const submit = useMutation({
    mutationFn: () => {
      const file = fileRef.current?.files?.[0]
      if (!file) throw new Error("Choose a PDF first")
      return submitModuleApi(moduleId, file, notes)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["instructor-module", moduleId] })
      qc.invalidateQueries({ queryKey: ["instructor-modules"] })
    },
  })

  if (isLoading || !module) return <Spinner />

  const locked = module.submission_status === "submitted" || module.submission_status === "approved"

  return (
    <div>
      <Link to="/instructors/modules" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-4">
        <ArrowLeft size={16} /> Back to modules
      </Link>
      <PageHeader
        title={module.title}
        subtitle={`${module.completed_count} / ${module.item_count} items checked`}
        action={module.submission_status ? <StatusPill status={module.submission_status} /> : undefined}
      />

      {module.submission_feedback && (
        <Card className="mb-4 border-destructive/50">
          <CardContent className="p-4">
            <p className="text-sm font-semibold text-destructive">Feedback</p>
            <p className="text-sm text-muted-foreground mt-1">{module.submission_feedback}</p>
          </CardContent>
        </Card>
      )}

      <div className="flex flex-col gap-4 mb-6">
        {module.sections.map((section, i) => (
          <Card key={section.id ?? i}>
            {section.title && (
              <CardContent className="pb-0 pt-4">
                <p className="text-sm font-semibold text-foreground">{section.title}</p>
              </CardContent>
            )}
            <CardContent className="space-y-2">
              {section.items.map((item) => (
                <label key={item.id} className="flex items-start gap-3 rounded-lg p-2 hover:bg-muted cursor-pointer">
                  <button
                    type="button"
                    onClick={() => !locked && toggle.mutate(item.id)}
                    className={`mt-0.5 w-5 h-5 rounded border flex items-center justify-center shrink-0 ${
                      item.is_completed ? "bg-primary border-primary text-primary-foreground" : "border-border"
                    }`}
                  >
                    {item.is_completed && <Check size={14} />}
                  </button>
                  <div>
                    <p className="text-sm font-medium text-foreground">{item.item_code} — {item.title}</p>
                    {item.description && <p className="text-xs text-muted-foreground mt-0.5">{item.description}</p>}
                  </div>
                </label>
              ))}
            </CardContent>
          </Card>
        ))}
      </div>

      {!locked && (
        <Card>
          <CardContent className="p-4 space-y-3">
            <p className="text-sm font-semibold text-foreground">Upload your write-up (PDF)</p>
            <input ref={fileRef} type="file" accept="application/pdf" className="input" />
            <textarea
              className="input min-h-20" placeholder="Notes (optional)" value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
            {submit.isError && (
              <p className="text-sm text-destructive">{(submit.error as any)?.message || "Upload failed."}</p>
            )}
            <Button onClick={() => submit.mutate()} disabled={submit.isPending}>
              <Upload size={16} className="mr-2" /> {submit.isPending ? "Uploading…" : "Submit module"}
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

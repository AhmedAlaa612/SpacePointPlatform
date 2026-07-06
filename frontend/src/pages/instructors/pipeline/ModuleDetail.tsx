import { useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useParams } from "@tanstack/react-router"
import { ArrowLeft, Check, Lock, Upload } from "lucide-react"
import { listVideosApi, moduleDetailApi, submitModuleApi, toggleChecklistItemApi } from "@/api/instructors/applicant"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { PageHeader, Spinner, StatusPill } from "@/pages/instructors/components/common"

export default function ModuleDetail() {
  const { moduleId } = useParams({ strict: false }) as { moduleId: string }
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [notes, setNotes] = useState("")

  const { data: videos, isLoading: videosLoading } = useQuery({
    queryKey: ["instructor-videos"],
    queryFn: listVideosApi,
  })

  const { data: module, isLoading } = useQuery({
    queryKey: ["instructor-module", moduleId],
    queryFn: () => moduleDetailApi(moduleId),
  })

  const toggle = useMutation({
    mutationFn: toggleChecklistItemApi,
    onMutate: async (itemId) => {
      await qc.cancelQueries({ queryKey: ["instructor-module", moduleId] })
      const previous = qc.getQueryData(["instructor-module", moduleId])
      qc.setQueryData(["instructor-module", moduleId], (old: any) => {
        if (!old) return old
        let delta = 0
        const sections = old.sections.map((sec: any) => ({
          ...sec,
          items: sec.items.map((it: any) => {
            if (it.id !== itemId) return it
            delta = it.is_completed ? -1 : 1
            return { ...it, is_completed: !it.is_completed }
          }),
        }))
        return { ...old, sections, completed_count: old.completed_count + delta }
      })
      return { previous }
    },
    onError: (_err, _itemId, ctx) => {
      if (ctx?.previous) qc.setQueryData(["instructor-module", moduleId], ctx.previous)
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["instructor-module", moduleId] }),
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

  if (isLoading || videosLoading || !module || !videos) return <Spinner />

  const videosDone = videos.length === 3 && videos.every((v) => v.status === "submitted")

  const uploadLocked = module.submission_status === "submitted" || module.submission_status === "approved"

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

      {!videosDone ? (
        <Card>
          <CardContent className="p-10 text-center">
            <Lock className="mx-auto mb-4 text-primary" size={48} />
            <h3 className="text-xl font-bold text-foreground mb-2">Complete Videos First</h3>
            <p className="text-muted-foreground mb-6">
              You must complete all 3 introductory video summaries before unlocking these modules.
            </p>
            <Link to="/instructors/videos">
              <Button>Go to Videos</Button>
            </Link>
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Module PDF Submission — first */}
          <Card className="mb-6">
            <CardContent className="p-6 space-y-3">
              <p className="text-sm font-semibold text-foreground">Module PDF Submission</p>
              <p className="text-sm text-muted-foreground">
                Upload a single, consolidated PDF containing all required research and findings for this entire module.{" "}
                <span className="text-primary font-medium block mt-1">
                  Maximum file size: 10MB. If your file exceeds 10MB, please upload it to Google Drive and paste the
                  shared link in the notes section below.
                </span>
              </p>

              {module.submission_feedback && (
                <div className="rounded-lg border border-destructive/50 bg-destructive/5 p-4">
                  <p className="text-sm font-semibold text-destructive">Feedback</p>
                  <p className="text-sm text-muted-foreground mt-1">{module.submission_feedback}</p>
                </div>
              )}

              {!uploadLocked ? (
                <div className="space-y-3 pt-1">
                  <input ref={fileRef} type="file" accept="application/pdf" className="input" />
                  <textarea
                    className="input min-h-20"
                    placeholder="Notes / Google Drive link (optional)"
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                  />
                  {submit.isError && (
                    <p className="text-sm text-destructive">{(submit.error as any)?.message || "Upload failed."}</p>
                  )}
                  <Button onClick={() => submit.mutate()} disabled={submit.isPending}>
                    <Upload size={16} className="mr-2" /> {submit.isPending ? "Uploading…" : "Submit module"}
                  </Button>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground pt-1">
                  Your submission has been {module.submission_status === "approved" ? "approved" : "received"} and can
                  no longer be edited.
                </p>
              )}
            </CardContent>
          </Card>

          {/* Checklist — second */}
          <div className="flex flex-col gap-4">
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
                        onClick={() => toggle.mutate(item.id)}
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
        </>
      )}
    </div>
  )
}

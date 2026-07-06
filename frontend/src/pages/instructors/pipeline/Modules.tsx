import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { CheckCircle2, Lock } from "lucide-react"
import {
  listVideosApi,
  listModulesApi,
  submitApplicationApi,
  getApplicationStatusApi,
} from "@/api/instructors/applicant"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { PageHeader, Spinner } from "@/pages/instructors/components/common"

export default function Modules() {
  const qc = useQueryClient()

  const { data: status } = useQuery({
    queryKey: ["instructor-status"],
    queryFn: getApplicationStatusApi,
  })
  const { data: videos, isLoading: videosLoading } = useQuery({
    queryKey: ["instructor-videos"],
    queryFn: listVideosApi,
  })
  const { data: modules, isLoading: modulesLoading } = useQuery({
    queryKey: ["instructor-modules"],
    queryFn: listModulesApi,
  })

  const submitApp = useMutation({
    mutationFn: submitApplicationApi,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["instructor-status"] }),
  })

  if (videosLoading || modulesLoading || !videos || !modules) return <Spinner />

  const videosDone = videos.length === 3 && videos.every((v) => v.status === "submitted")

  const modulesUploaded = modules.filter((m) => m.submission_status && m.submission_status !== "rejected").length
  const modulesDone = modules.length > 0 && modulesUploaded === modules.length
  const canSubmit = videosDone && modulesDone && status?.status === "in_progress"

  return (
    <div>
      <PageHeader
        title="Learning Modules"
        subtitle="Complete the checklist research items for each module below."
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
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-12">
            {modules.map((m) => {
              const percent = m.item_count > 0 ? Math.round((m.completed_count / m.item_count) * 100) : 100
              const isComplete = percent === 100
              return (
                <Link key={m.id} to="/instructors/modules/$moduleId" params={{ moduleId: m.id }}>
                  <Card
                    className={`h-full transition-all hover:-translate-y-1 ${
                      isComplete ? "border-primary/50 bg-primary/5" : "hover:border-primary/40"
                    }`}
                  >
                    <CardContent className="p-6">
                      <div className="flex justify-between items-start mb-4">
                        <div>
                          <p className="text-sm text-muted-foreground">Module {m.sort_order}</p>
                          <h3 className="text-lg font-bold text-foreground">{m.title}</h3>
                        </div>
                        <div className={`p-2 rounded-full shrink-0 ${isComplete ? "bg-primary/20 text-primary" : "bg-muted text-muted-foreground"}`}>
                          <CheckCircle2 size={20} />
                        </div>
                      </div>
                      <div>
                        <div className="flex justify-between text-sm mb-1">
                          <span className="text-muted-foreground">Progress</span>
                          <span className={isComplete ? "text-primary font-bold" : "text-foreground"}>
                            {m.completed_count} / {m.item_count} Items
                          </span>
                        </div>
                        <div className="w-full bg-muted rounded-full h-2.5">
                          <div
                            className={`h-2.5 rounded-full transition-all duration-700 ${isComplete ? "bg-primary" : "bg-blue-500"}`}
                            style={{ width: `${percent}%` }}
                          />
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </Link>
              )
            })}
          </div>

          <Card className="border-t-4 border-t-primary/30">
            <CardContent className="p-8 flex flex-col md:flex-row items-center justify-between gap-6">
              <div>
                <h3 className="text-xl font-bold text-foreground mb-2">Final Application</h3>
                <p className="text-sm text-muted-foreground max-w-lg">
                  Once you have completely uploaded all required research PDFs across the {modules.length} modules,
                  you can submit your final application for review.
                </p>
              </div>
              <div className="shrink-0 text-right">
                {submitApp.isError && (
                  <p className="text-sm text-destructive mb-2">
                    {(submitApp.error as any)?.response?.data?.detail || "Could not submit application."}
                  </p>
                )}
                <Button
                  size="lg"
                  disabled={!canSubmit || submitApp.isPending}
                  onClick={() => submitApp.mutate()}
                >
                  {submitApp.isPending
                    ? "Submitting…"
                    : status && status.status !== "in_progress"
                    ? "Application Under Review"
                    : "Submit Application"}
                </Button>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}

import { Link } from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import { CheckCircle2, Info, PlayCircle } from "lucide-react"
import { listTrainingApi } from "@/api/instructors/training"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { EmptyState, PageHeader, Spinner } from "@/pages/instructors/components/common"

export default function Training() {
  const { data: modules, isLoading } = useQuery({ queryKey: ["instructor-training"], queryFn: listTrainingApi })

  if (isLoading) return <Spinner />

  return (
    <div>
      <PageHeader title="SatKit Training" subtitle="Work through each module's videos at your own pace." />

      <div className="mb-6 flex items-start gap-3 rounded-2xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-700 dark:border-blue-900/50 dark:bg-blue-950/30 dark:text-blue-400">
        <Info size={18} className="shrink-0 mt-0.5" />
        <p>
          <strong>Hardware Requisition Note:</strong> You cannot order physical SatKits for your students
          until you complete these training videos and pass the short quiz.
        </p>
      </div>

      {(modules ?? []).length === 0 ? (
        <EmptyState title="No training modules yet" hint="Facilitators add training content here." />
      ) : (
        <div className="space-y-4">
          {modules!.map((m) => (
            <Card key={m.id}>
              <CardHeader>
                <CardTitle>{m.title}</CardTitle>
                {m.description && <p className="text-sm text-muted-foreground">{m.description}</p>}
              </CardHeader>
              <CardContent className="space-y-2">
                {m.videos.map((v) => (
                  <Link
                    key={v.id}
                    to="/instructors/training/player/$videoId"
                    params={{ videoId: v.id }}
                    className="flex items-center gap-3 p-3 rounded-lg border bg-background hover:bg-muted transition-colors"
                  >
                    {v.is_completed ? (
                      <CheckCircle2 className="text-green-600 shrink-0" size={20} />
                    ) : (
                      <PlayCircle className="text-primary shrink-0" size={20} />
                    )}
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">{v.title}</p>
                      {v.description && <p className="text-xs text-muted-foreground truncate">{v.description}</p>}
                    </div>
                  </Link>
                ))}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

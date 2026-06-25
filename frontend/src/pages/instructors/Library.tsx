import { useQuery } from "@tanstack/react-query"
import { Download, FileText } from "lucide-react"
import { listLibraryApi } from "@/api/instructors/training"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { EmptyState, PageHeader, Spinner } from "@/pages/instructors/components/common"

export default function Library() {
  const { data: modules, isLoading } = useQuery({ queryKey: ["instructor-library"], queryFn: listLibraryApi })

  if (isLoading) return <Spinner />

  return (
    <div>
      <PageHeader title="Library" subtitle="Shared workshop materials from your facilitators." />

      {(modules ?? []).length === 0 ? (
        <EmptyState title="No resources yet" hint="Facilitators add shared materials here." />
      ) : (
        <div className="space-y-4">
          {modules!.map((m) => (
            <Card key={m.id}>
              <CardHeader>
                <CardTitle>{m.name}</CardTitle>
                {m.description && <p className="text-sm text-muted-foreground">{m.description}</p>}
              </CardHeader>
              <CardContent className="space-y-2">
                {m.resources.map((r) => (
                  <a
                    key={r.id}
                    href={r.file_url}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center gap-3 p-3 rounded-lg border bg-background hover:bg-muted transition-colors"
                  >
                    <FileText className="text-primary shrink-0" size={20} />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium truncate">{r.title}</p>
                      <p className="text-xs text-muted-foreground">{r.format}</p>
                    </div>
                    <Download className="text-muted-foreground shrink-0" size={16} />
                  </a>
                ))}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

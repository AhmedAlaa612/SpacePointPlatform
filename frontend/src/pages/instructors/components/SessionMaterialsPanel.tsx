import { useQuery } from "@tanstack/react-query"
import { FileText, Link2, Paperclip } from "lucide-react"
import { getSessionMaterialsApi } from "@/api/sessions/openings"
import { Card, CardContent } from "@/components/ui/card"

/**
 * What this session's instructor should read before teaching (I5-6).
 *
 * Resolved server-side: the session's own materials, else the cohort's, else
 * the program's — override, not merge. Renders nothing when there are none,
 * so sessions without materials look exactly as they did before this existed.
 *
 * `Session.material_url` (the single pre-existing link) is untouched and still
 * shown by the page above; this is the richer list the CEO asked for.
 */
export function SessionMaterialsPanel({ sessionId }: { sessionId: string }) {
  const { data } = useQuery({
    queryKey: ["session-materials", sessionId],
    queryFn: () => getSessionMaterialsApi(sessionId),
  })

  if (!data || data.materials.length === 0) return null

  return (
    <Card>
      <CardContent className="p-4 flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <p className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <Paperclip size={15} /> Materials
          </p>
          {data.level !== "session" && (
            <span className="text-xs text-muted-foreground">
              from the {data.level}
            </span>
          )}
        </div>

        <div className="flex flex-col gap-1.5">
          {data.materials.map((m) => (
            <a
              key={m.id}
              href={m.url ?? "#"}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-2 rounded-xl border border-border bg-background/50 px-3 py-2 hover:bg-muted/60 transition-colors"
            >
              {m.filename
                ? <FileText size={14} className="shrink-0 text-muted-foreground" />
                : <Link2 size={14} className="shrink-0 text-muted-foreground" />}
              <span className="min-w-0">
                <span className="block text-sm text-foreground truncate">{m.title}</span>
                {m.notes && (
                  <span className="block text-xs text-muted-foreground truncate">{m.notes}</span>
                )}
              </span>
            </a>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

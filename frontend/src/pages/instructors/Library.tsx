import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { ExternalLink, FileText, Video } from "lucide-react"
import { getLibraryResourceUrlApi, listLibraryApi } from "@/api/instructors/training"
import type { LibraryResource } from "@/types/instructors"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { EmptyState, PageHeader, Spinner } from "@/pages/instructors/components/common"
import { PdfViewer } from "@/components/documents/PdfViewer"
import { isVideoFormat } from "@/lib/utils"

/** A hosted PDF opens in the no-download inline viewer instead of a
 *  clickable/downloadable link — everything else (a PPTX upload, a `link`
 *  resource pointing off-site) still opens as a plain link, since there's
 *  no inline viewer for those. See `routers/instructors/library.py`'s own
 *  docstring for why a hosted PDF's `file_url` already comes back blank. */
const isInlinePdf = (r: LibraryResource) => r.resource_type === "file" && r.format.toUpperCase() === "PDF"

/** A hosted video plays inline instead of downloading — its `file_url` is
 * already a resolved signed URL in the list response (only a hosted PDF's
 * is blanked out), so this doesn't need its own resolve-on-open fetch. */
const isInlineVideo = (r: LibraryResource) => r.resource_type === "file" && isVideoFormat(r.format)

export default function Library() {
  const { data: modules, isLoading } = useQuery({ queryKey: ["instructor-library"], queryFn: listLibraryApi })
  const [viewing, setViewing] = useState<LibraryResource | null>(null)

  if (isLoading) return <Spinner />

  return (
    <div>
      <PageHeader title="Curriculum Library" subtitle="Shared workshop materials from your facilitators." />

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
                {m.resources.map((r) =>
                  isInlinePdf(r) || isInlineVideo(r) ? (
                    <button
                      key={r.id}
                      type="button"
                      onClick={() => setViewing(r)}
                      className="w-full flex items-center gap-3 p-3 rounded-lg border bg-background hover:bg-muted transition-colors text-left cursor-pointer"
                    >
                      {isInlineVideo(r) ? <Video className="text-primary shrink-0" size={20} /> : <FileText className="text-primary shrink-0" size={20} />}
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium truncate">{r.title}</p>
                        <p className="text-xs text-muted-foreground">{r.format}</p>
                      </div>
                    </button>
                  ) : (
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
                        {r.resource_type !== "link" && <p className="text-xs text-muted-foreground">{r.format}</p>}
                      </div>
                      <ExternalLink className="text-muted-foreground shrink-0" size={16} />
                    </a>
                  ),
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={!!viewing} onOpenChange={(open) => !open && setViewing(null)}>
        <DialogContent className="sm:max-w-3xl max-w-3xl">
          <DialogHeader><DialogTitle>{viewing?.title}</DialogTitle></DialogHeader>
          {viewing && <ResourceViewer resource={viewing} />}
        </DialogContent>
      </Dialog>
    </div>
  )
}

function ResourceViewer({ resource }: { resource: LibraryResource }) {
  if (isInlineVideo(resource)) {
    return <video src={resource.file_url} controls autoPlay className="w-full max-h-[70vh] rounded-lg bg-black" />
  }
  return <PdfResourceViewer resourceId={resource.id} />
}

function PdfResourceViewer({ resourceId }: { resourceId: string }) {
  const { data: url, isLoading, isError } = useQuery({
    queryKey: ["library-resource-url", resourceId],
    queryFn: () => getLibraryResourceUrlApi(resourceId),
  })

  if (isLoading) return <p className="text-sm text-muted-foreground py-6">Loading document...</p>
  if (isError || !url) {
    return <p className="text-sm text-destructive py-6">Couldn't load this document.</p>
  }
  return <PdfViewer url={url} />
}

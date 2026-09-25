import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { ExternalLink, FileText, Video } from "lucide-react"
import { getLibraryResourceUrlApi, listLibraryApi } from "@/api/instructors/training"
import type { LibraryResource } from "@/types/instructors"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { EmptyState, PageHeader, Spinner } from "@/pages/instructors/components/common"
import { PdfViewer } from "@/components/documents/PdfViewer"
import { VideoPlayer } from "@/components/video/VideoPlayer"
import { isVideoFormat } from "@/lib/utils"

/** A hosted PDF opens in the no-download inline viewer instead of a
 *  clickable/downloadable link — everything else (a PPTX upload, a `link`
 *  resource pointing off-site) still opens as a plain link, since there's
 *  no inline viewer for those. See `routers/instructors/library.py`'s own
 *  docstring for why a hosted PDF's `file_url` already comes back blank. */
const isInlinePdf = (r: LibraryResource) => r.resource_type === "file" && r.format.toUpperCase() === "PDF"

/** A hosted video (or an embedded one — format === "EMBED") plays inline
 * instead of downloading — same resolve-on-open posture as a hosted PDF
 * (see routers/instructors/library.py's own docstring): its `file_url`
 * comes back blank in the list too, resolved only once someone actually
 * opens it. */
const isInlineVideo = (r: LibraryResource) =>
  r.resource_type === "file" && (isVideoFormat(r.format) || r.format === "EMBED")

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
        <DialogContent className="sm:max-w-[95vw] max-w-[95vw] w-[95vw] h-[92vh] max-h-[92vh] flex flex-col">
          <DialogHeader><DialogTitle>{viewing?.title}</DialogTitle></DialogHeader>
          {viewing && <ResourceViewer resource={viewing} />}
        </DialogContent>
      </Dialog>
    </div>
  )
}

function ResourceViewer({ resource }: { resource: LibraryResource }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["library-resource-url", resource.id],
    queryFn: () => getLibraryResourceUrlApi(resource.id),
    // Poll while an hls_encrypted upload is still transcoding — this used
    // to be a non-issue when uploads flipped straight to "ready", but now
    // there is a real async gap to bridge without a manual refresh.
    refetchInterval: (q) => {
      const status = q.state.data?.video_info?.status
      return status && status !== "ready" && status !== "failed" ? 4000 : false
    },
  })

  if (isLoading) return <p className="text-sm text-muted-foreground py-6">Loading document...</p>

  if (isInlineVideo(resource)) {
    // video_info drives an embed (iframe) vs. a direct upload (<video src>)
    // — a bare url string can't tell those apart, and an embed has no "url"
    // at all (only embed_url), so isError/!url here would wrongly treat a
    // successfully embedded video as a failed load.
    if (isError || !data?.video_info) {
      return <p className="text-sm text-destructive py-6">Couldn't load this video.</p>
    }
    return (
      <VideoPlayer
        info={data.video_info}
        title={resource.title}
        autoPlay
        className="w-full flex-1 min-h-0 rounded-lg bg-black"
      />
    )
  }

  if (isError || !data?.url) {
    return <p className="text-sm text-destructive py-6">Couldn't load this document.</p>
  }
  return <PdfViewer url={data.url} className="flex flex-col gap-3 flex-1 min-h-0" />
}

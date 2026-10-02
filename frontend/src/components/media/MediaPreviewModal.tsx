import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { PdfViewer } from "@/components/documents/PdfViewer"
import { VideoPlayer as GeneralVideoPlayer, type VideoPlaybackInfo } from "@/components/video/VideoPlayer"
import { VideoPlayer as CourseVideoPlayer } from "@/pages/learn/VideoPlayer"
import { ExternalLink, FileText, Video as VideoIcon } from "lucide-react"

export interface MediaPreviewModalProps {
  open: boolean
  onClose: () => void
  title: string
  type: "pdf" | "video"
  url?: string | null
  videoInfo?: VideoPlaybackInfo | null
  // When previewing course module videos with checkpoints:
  itemId?: string
  videoId?: string | null
  transcodeStatus?: string | null
}

export function MediaPreviewModal({
  open,
  onClose,
  title,
  type,
  url,
  videoInfo,
  itemId,
  videoId,
  transcodeStatus,
}: MediaPreviewModalProps) {
  const isPdf = type === "pdf"

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose() }}>
      <DialogContent
        className={
          isPdf
            ? "sm:max-w-[95vw] max-w-[95vw] w-[95vw] h-[92vh] max-h-[92vh] flex flex-col p-4 sm:p-6"
            : "sm:max-w-4xl max-w-4xl w-full flex flex-col p-4 sm:p-6"
        }
      >
        <DialogHeader className="flex flex-row items-center justify-between gap-4 pb-2 border-b border-border/60">
          <div className="flex items-center gap-2 min-w-0">
            {isPdf ? (
              <FileText className="size-5 text-primary shrink-0" />
            ) : (
              <VideoIcon className="size-5 text-primary shrink-0" />
            )}
            <DialogTitle className="truncate text-base sm:text-lg font-semibold">{title}</DialogTitle>
          </div>
          {url && isPdf && (
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors mr-6 shrink-0"
              title="Open in new browser tab"
            >
              <span>Open in tab</span>
              <ExternalLink size={13} />
            </a>
          )}
        </DialogHeader>

        <div className="flex-1 min-h-0 mt-3 flex flex-col justify-center">
          {isPdf ? (
            url ? (
              <PdfViewer url={url} className="flex flex-col gap-3 flex-1 min-h-0" />
            ) : (
              <div className="p-8 text-center text-muted-foreground text-sm">No PDF URL available to preview.</div>
            )
          ) : (
            // Video preview: Course module video with checkpoints, or general video player
            itemId && videoId ? (
              <div className="w-full rounded-xl overflow-hidden bg-black">
                <CourseVideoPlayer
                  itemId={itemId}
                  videoId={videoId}
                  transcodeStatus={transcodeStatus ?? "ready"}
                  onEnded={() => {}}
                />
              </div>
            ) : (
              <div className="w-full rounded-xl overflow-hidden bg-black">
                <GeneralVideoPlayer
                  info={videoInfo ?? { provider: "upload", mode: "direct", status: "ready", url: url ?? "" }}
                  title={title}
                  className="w-full max-h-[75vh]"
                />
              </div>
            )
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

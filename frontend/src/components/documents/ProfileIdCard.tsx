import { useRef, useState, useEffect } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Download, Upload, User, Link2, CheckCircle2, RefreshCw } from "lucide-react"
import { getIdCardApi, updateIdCardApi, downloadIdCardPdfApi } from "@/api/documents"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"

interface ProfileIdCardProps {
  role: string | null
  onPhotoUploaded?: (photoUrl: string) => void
}

export function ProfileIdCard({ role, onPhotoUploaded }: ProfileIdCardProps) {
  const qc = useQueryClient()
  const photoRef = useRef<HTMLInputElement>(null)

  const [linkedinInput, setLinkedinInput] = useState("")
  const [linkedinLoaded, setLinkedinLoaded] = useState(false)
  const [savedLinkedin, setSavedLinkedin] = useState(false)

  const card = useQuery({
    queryKey: ["id-card", role],
    queryFn: () => getIdCardApi(role ?? ""),
    enabled: !!role,
    staleTime: 0,
  })

  // Pre-fill LinkedIn once loaded
  useEffect(() => {
    if (card.data && !linkedinLoaded) {
      setLinkedinInput(card.data.linkedin_url ?? "")
      setLinkedinLoaded(true)
    }
  }, [card.data, linkedinLoaded])

  const uploadPhoto = useMutation({
    mutationFn: (file: File) => updateIdCardApi(role!, file, undefined),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["id-card", role] })
      if (data.photo_url && onPhotoUploaded) {
        onPhotoUploaded(data.photo_url)
      }
    },
  })

  const saveLinkedin = useMutation({
    mutationFn: () => updateIdCardApi(role!, undefined, linkedinInput || ""),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["id-card", role] })
      setSavedLinkedin(true)
      setTimeout(() => setSavedLinkedin(false), 2500)
    },
  })

  const downloadPdf = useMutation({
    mutationFn: () => downloadIdCardPdfApi(role!),
    onSuccess: (blob) => {
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `SpacePoint_ID_${card.data?.card_id ?? "card"}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    },
  })

  if (card.isLoading) {
    return (
      <div className="flex items-center justify-center p-8">
        <RefreshCw className="w-6 h-6 animate-spin text-primary" />
      </div>
    )
  }

  const cardSrc = card.data?.front_b64 ? `data:image/png;base64,${card.data.front_b64}` : null
  const backSrc = card.data?.back_b64 ? `data:image/png;base64,${card.data.back_b64}` : null

  return (
    <div className="flex flex-col gap-5 mt-6 w-full">
      {/* Photo and LinkedIn settings in a Card */}
      <Card>
        <CardContent className="p-5 flex flex-col gap-4">
          <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <User size={15} className="text-primary" />
            ID Card Settings
          </h3>

          <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center">
            {/* Upload Button & Status */}
            <div className="flex items-center gap-3">
              <div
                className="relative w-14 h-14 rounded-full bg-primary/10 flex items-center justify-center overflow-hidden border-2 border-border cursor-pointer group shrink-0"
                onClick={() => photoRef.current?.click()}
                title="Click to upload profile photo"
              >
                {card.data?.photo_url ? (
                  <img src={card.data.photo_url} alt="Profile" className="w-full h-full object-cover" />
                ) : (
                  <User size={22} className="text-primary" />
                )}
                <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center rounded-full">
                  <Upload size={16} className="text-white" />
                </div>
              </div>
              <div>
                <p className="text-xs font-semibold text-foreground">Profile Photo</p>
                <p className="text-[10px] text-muted-foreground mt-0.5">Required for card generation</p>
              </div>
            </div>

            <input
              ref={photoRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) uploadPhoto.mutate(f)
                e.currentTarget.value = ""
              }}
            />
            {uploadPhoto.isPending && (
              <span className="text-xs text-muted-foreground ml-auto animate-pulse">Uploading…</span>
            )}
          </div>

          {/* LinkedIn URL */}
          <div className="flex flex-col gap-1.5 border-t border-border pt-3">
            <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
              <Link2 size={11} /> LinkedIn URL
              <span className="font-normal normal-case text-[10px]">(adds QR code to ID card)</span>
            </label>
            <div className="flex gap-2">
              <input
                type="url"
                value={linkedinInput}
                onChange={(e) => setLinkedinInput(e.target.value)}
                placeholder="https://linkedin.com/in/yourname"
                className="flex-1 h-9 px-3 bg-background border border-border rounded-xl text-sm focus:outline-none focus:border-primary text-foreground placeholder:text-muted-foreground/50"
              />
              <Button
                size="sm"
                variant="outline"
                onClick={() => saveLinkedin.mutate()}
                disabled={saveLinkedin.isPending}
                className="gap-1.5 shrink-0"
              >
                {savedLinkedin ? <><CheckCircle2 size={13} /> Saved</> : "Save"}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ID Card Display */}
      <div>
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">
          ID Card Preview
        </h3>

        <div className="flex flex-col gap-6">
          {/* Card previews grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            {/* Front Card */}
            <div className="flex flex-col gap-2">
              <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider text-center">Front</span>
              <div className="relative rounded-2xl overflow-hidden border border-border bg-muted/20 aspect-[359/568] flex items-center justify-center">
                {cardSrc ? (
                  <img
                    src={cardSrc}
                    alt="ID card front"
                    className="w-full h-full object-contain"
                  />
                ) : (
                  <div className="text-center p-4">
                    <User size={32} className="mx-auto text-muted-foreground/40 mb-2" />
                    <p className="text-xs text-muted-foreground">Upload photo to render front</p>
                  </div>
                )}
              </div>
              {card.data?.front_b64 && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="w-full gap-1.5 text-xs text-muted-foreground hover:text-foreground"
                  onClick={() => {
                    if (!card.data) return
                    const link = document.createElement("a")
                    link.href = `data:image/png;base64,${card.data.front_b64}`
                    link.download = `SpacePoint_ID_Front_${card.data.card_id ?? "card"}.png`
                    link.click()
                  }}
                >
                  <Download size={12} />
                  Download Front Image
                </Button>
              )}
            </div>

            {/* Back Card */}
            <div className="flex flex-col gap-2">
              <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider text-center">Back</span>
              <div className="relative rounded-2xl overflow-hidden border border-border bg-muted/20 aspect-[359/568] flex items-center justify-center">
                {backSrc ? (
                  <img
                    src={backSrc}
                    alt="ID card back"
                    className="w-full h-full object-contain"
                  />
                ) : (
                  <div className="text-center p-4">
                    <User size={32} className="mx-auto text-muted-foreground/40 mb-2" />
                    <p className="text-xs text-muted-foreground">Upload photo to render back</p>
                  </div>
                )}
              </div>
              {card.data?.back_b64 && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="w-full gap-1.5 text-xs text-muted-foreground hover:text-foreground"
                  onClick={() => {
                    if (!card.data) return
                    const link = document.createElement("a")
                    link.href = `data:image/png;base64,${card.data.back_b64}`
                    link.download = `SpacePoint_ID_Back_${card.data.card_id ?? "card"}.png`
                    link.click()
                  }}
                >
                  <Download size={12} />
                  Download Back Image
                </Button>
              )}
            </div>
          </div>

          {/* Card info + global actions */}
          {card.data?.card_id && (
            <div className="flex flex-col gap-3 bg-muted/10 border border-border p-4 rounded-2xl">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div>
                  <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Card ID</p>
                  <p className="text-sm font-mono font-semibold text-foreground">{card.data.card_id}</p>
                </div>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    className="gap-1.5"
                    onClick={() => photoRef.current?.click()}
                    disabled={uploadPhoto.isPending}
                  >
                    <Upload size={13} />
                    {card.data?.photo_url ? "Change photo" : "Upload photo"}
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => downloadPdf.mutate()}
                    disabled={downloadPdf.isPending}
                    className="gap-1.5"
                  >
                    <Download size={13} />
                    {downloadPdf.isPending ? "Generating…" : "Download PDF"}
                  </Button>
                </div>
              </div>

              <div className="flex flex-col gap-1 text-[11px] text-muted-foreground border-t border-border pt-2.5">
                <p className={`flex items-center gap-1.5 ${card.data?.has_photo ? "text-emerald-600 dark:text-emerald-400" : ""}`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${card.data?.has_photo ? "bg-emerald-500" : "bg-muted-foreground/30"}`} />
                  Profile photo {card.data?.has_photo ? "on card" : "— click upload photo above to display"}
                </p>
                <p className={`flex items-center gap-1.5 ${card.data?.has_linkedin ? "text-emerald-600 dark:text-emerald-400" : ""}`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${card.data?.has_linkedin ? "bg-emerald-500" : "bg-muted-foreground/30"}`} />
                  LinkedIn QR {card.data?.has_linkedin ? "on card" : "— add your LinkedIn URL above to display"}
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

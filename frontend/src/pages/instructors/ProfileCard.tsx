import { useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Download, Upload, User, Link2, AlertCircle, RefreshCw, CheckCircle2 } from "lucide-react"
import { downloadIdCardPdfApi, getIdCardApi, getProfileApi, updateIdCardApi } from "@/api/instructors/instructor"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { PageHeader, Spinner } from "@/pages/instructors/components/common"
import { useAuth } from "@/context/AuthContext"

export default function ProfileCard() {
  const { currentUser } = useAuth()
  const qc = useQueryClient()
  const photoRef = useRef<HTMLInputElement>(null)
  const [linkedinInput, setLinkedinInput] = useState("")
  const [linkedinLoaded, setLinkedinLoaded] = useState(false)
  const [photoPreview, setPhotoPreview] = useState<string | null>(null)
  const [selectedPhoto, setSelectedPhoto] = useState<File | null>(null)
  const [saved, setSaved] = useState(false)

  const profile = useQuery({ queryKey: ["instructor-profile"], queryFn: getProfileApi })
  const card = useQuery({
    queryKey: ["instructor-id-card", currentUser?.role],
    queryFn: () => getIdCardApi(currentUser?.role ?? "instructor"),
    staleTime: 0,          // always refetch when navigating back
  })

  // Pre-fill LinkedIn input once profile loads
  if (profile.data && !linkedinLoaded) {
    setLinkedinInput(profile.data.linkedin_url ?? "")
    setLinkedinLoaded(true)
  }

  const update = useMutation({
    mutationFn: () => updateIdCardApi(selectedPhoto ?? undefined, linkedinInput || undefined, currentUser?.role ?? "instructor"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["instructor-id-card"] })
      qc.invalidateQueries({ queryKey: ["instructor-profile"] })
      setSelectedPhoto(null)
      setPhotoPreview(null)
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    },
  })

  const downloadPdf = useMutation({
    mutationFn: () => downloadIdCardPdfApi(currentUser?.role ?? "instructor"),
    onSuccess: (blob) => {
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `SpacePoint_ID_${card.data?.card_id ?? "card"}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    },
  })

  if (profile.isLoading || card.isLoading) return <Spinner />

  const hasPhoto = card.data?.has_photo || !!photoPreview
  const cardSrc = card.data?.front_b64 ? `data:image/png;base64,${card.data.front_b64}` : null

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Profile Card"
        subtitle="Your official SpacePoint ID card — generated live from your profile."
      />

      <div className="grid lg:grid-cols-2 gap-6 items-start">

        {/* ── Left: Card preview ─────────────────────────────── */}
        <div className="flex flex-col gap-4">
          <div className="relative rounded-2xl overflow-hidden border border-border bg-muted/30 flex items-center justify-center min-h-[320px]">
            {cardSrc ? (
              <img
                src={cardSrc}
                alt="Your SpacePoint ID card"
                className="w-full max-w-[280px] rounded-xl shadow-lg mx-auto"
              />
            ) : (
              <div className="flex flex-col items-center gap-3 py-12 px-6 text-center">
                <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center">
                  <User size={28} className="text-primary/60" />
                </div>
                <p className="text-sm font-medium text-foreground">No card generated yet</p>
                <p className="text-xs text-muted-foreground max-w-[200px]">
                  Upload a profile photo to generate your ID card
                </p>
              </div>
            )}
          </div>

          {/* Card meta */}
          {card.data?.card_id && (
            <div className="flex items-center justify-between px-1">
              <div>
                <p className="text-xs text-muted-foreground">Card ID</p>
                <p className="text-sm font-mono font-semibold text-foreground">{card.data.card_id}</p>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => downloadPdf.mutate()}
                disabled={!card.data?.has_photo || downloadPdf.isPending}
                className="gap-1.5"
              >
                <Download size={14} />
                {downloadPdf.isPending ? "Generating…" : "Download PDF"}
              </Button>
            </div>
          )}
        </div>

        {/* ── Right: Edit panel ──────────────────────────────── */}
        <Card>
          <CardContent className="p-5 flex flex-col gap-5">

            {/* Photo upload */}
            <div className="flex flex-col gap-2">
              <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Profile Photo
              </label>

              {!hasPhoto && (
                <div className="flex items-start gap-2 rounded-xl bg-amber-500/10 border border-amber-500/20 p-3">
                  <AlertCircle size={15} className="text-amber-500 mt-0.5 shrink-0" />
                  <p className="text-xs text-amber-700 dark:text-amber-400">
                    A profile photo is required to generate your card.
                  </p>
                </div>
              )}

              <div className="flex items-center gap-3">
                {/* Preview circle */}
                <div className="w-14 h-14 rounded-full border-2 border-border bg-muted flex items-center justify-center overflow-hidden shrink-0">
                  {photoPreview ? (
                    <img src={photoPreview} alt="Preview" className="w-full h-full object-cover" />
                  ) : profile.data?.photo_url ? (
                    <img src={profile.data.photo_url} alt="Current photo" className="w-full h-full object-cover" />
                  ) : (
                    <User size={22} className="text-muted-foreground" />
                  )}
                </div>

                <label className="cursor-pointer">
                  <input
                    ref={photoRef}
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={(e) => {
                      const f = e.target.files?.[0]
                      if (!f) return
                      setSelectedPhoto(f)
                      setPhotoPreview(URL.createObjectURL(f))
                    }}
                  />
                  <span className="inline-flex items-center gap-1.5 h-9 px-3 bg-secondary text-secondary-foreground text-xs font-semibold rounded-xl hover:opacity-80 transition-opacity">
                    <Upload size={13} />
                    {profile.data?.photo_url ? "Change photo" : "Upload photo"}
                  </span>
                </label>
              </div>
            </div>

            {/* LinkedIn */}
            <div className="flex flex-col gap-2">
              <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
                <Link2 size={12} /> LinkedIn URL
                <span className="text-[10px] font-normal normal-case">(optional — adds QR code to card)</span>
              </label>
              <input
                type="url"
                value={linkedinInput}
                onChange={(e) => setLinkedinInput(e.target.value)}
                placeholder="https://linkedin.com/in/yourname"
                className="h-10 px-3 bg-background border border-border rounded-xl text-sm focus:outline-none focus:border-primary text-foreground placeholder:text-muted-foreground/60"
              />
            </div>

            {/* Save / Regenerate */}
            <Button
              onClick={() => update.mutate()}
              disabled={update.isPending || (!selectedPhoto && !linkedinInput && !card.data?.card_id)}
              className="w-full gap-2"
            >
              {update.isPending ? (
                <><RefreshCw size={15} className="animate-spin" /> Generating card…</>
              ) : saved ? (
                <><CheckCircle2 size={15} /> Card updated!</>
              ) : cardSrc ? (
                <><RefreshCw size={15} /> Regenerate card</>
              ) : (
                <><Upload size={15} /> Generate card</>
              )}
            </Button>

            {update.isError && (
              <p className="text-xs text-red-500 text-center">
                Something went wrong. Please try again.
              </p>
            )}

            <p className="text-[10px] text-muted-foreground text-center">
              Your card is generated live — changes are reflected immediately.
              {card.data?.has_linkedin ? "" : " Add a LinkedIn URL to include a QR code."}
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

import { useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Download,
  ImageIcon,
  Zap,
  Pencil,
  Eye,
  Info,
  CreditCard,
} from "lucide-react"
import { downloadIdCardPdfApi, getIdCardApi, getProfileApi, updateIdCardApi } from "@/api/instructors/instructor"
import { Spinner } from "@/pages/instructors/components/common"
import { useAuth } from "@/context/AuthContext"

export default function ProfileCard() {
  const { currentUser } = useAuth()
  const role = currentUser?.role ?? "instructor"
  const qc = useQueryClient()
  const photoRef = useRef<HTMLInputElement>(null)

  const [linkedinInput, setLinkedinInput] = useState("")
  const [linkedinLoaded, setLinkedinLoaded] = useState(false)
  const [photoPreview, setPhotoPreview] = useState<string | null>(null)
  const [selectedPhoto, setSelectedPhoto] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const profile = useQuery({ queryKey: ["instructor-profile"], queryFn: getProfileApi })
  const card = useQuery({
    queryKey: ["instructor-id-card", role],
    queryFn: () => getIdCardApi(role),
    staleTime: 0,
  })

  if (card.data && !linkedinLoaded) {
    setLinkedinInput(card.data.linkedin_url ?? profile.data?.linkedin_url ?? "")
    setLinkedinLoaded(true)
  }

  const roleLabel = role === "facilitator" ? "Facilitator" : "Instructor"
  const hasCard = !!card.data?.front_b64
  const hasPhoto = card.data?.has_photo || !!photoPreview

  const generate = useMutation({
    mutationFn: () => updateIdCardApi(selectedPhoto ?? undefined, linkedinInput || undefined, role),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["instructor-id-card"] })
      qc.invalidateQueries({ queryKey: ["instructor-profile"] })
      setSelectedPhoto(null)
      setPhotoPreview(null)
      setError(null)
      setSuccess(`ID Card generated successfully! Your ${roleLabel.toLowerCase()} ID is ${data.card_id}.`)
      setTimeout(() => setSuccess(null), 5000)
    },
    onError: (err: any) => {
      setSuccess(null)
      setError(err?.response?.data?.detail || "Generation failed. Please try again.")
    },
  })

  const downloadPdf = useMutation({
    mutationFn: () => downloadIdCardPdfApi(role),
    onSuccess: (blob) => {
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `SpacePoint_ID_${card.data?.card_id ?? "card"}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    },
  })

  const handleGenerate = () => {
    setError(null)
    setSuccess(null)
    if (!linkedinInput.trim()) return setError("LinkedIn URL is required.")
    if (!hasPhoto) return setError("Profile photo is required.")
    generate.mutate()
  }

  if (profile.isLoading || card.isLoading) return <Spinner />

  const frontSrc = card.data?.front_b64 ? `data:image/png;base64,${card.data.front_b64}` : null
  const backSrc = card.data?.back_b64 ? `data:image/png;base64,${card.data.back_b64}` : null
  const issued = card.data?.generated_at
    ? new Date(card.data.generated_at).toLocaleDateString("en-GB", {
        day: "2-digit",
        month: "long",
        year: "numeric",
      })
    : "—"

  const previewPhoto = photoPreview ?? profile.data?.photo_url ?? card.data?.photo_url ?? null

  return (
    <div className="max-w-4xl mx-auto flex flex-col gap-8">
      {/* ── Hero ─────────────────────────────────────────────── */}
      <div className="relative overflow-hidden rounded-3xl border border-primary/20 bg-gradient-to-r from-background/80 to-card/80 p-8 backdrop-blur-xl">
        <div className="pointer-events-none absolute -right-20 -top-20 h-64 w-64 rounded-full bg-primary/20 blur-3xl mix-blend-screen" />
        <div className="relative z-10">
          <h1 className="font-display text-3xl font-bold text-foreground mb-2">{roleLabel} ID Card</h1>
          <p className="text-muted-foreground text-base max-w-xl">
            Generate your personalized SpacePoint {roleLabel} ID card. Your card will be created using
            your profile photo and LinkedIn profile URL.
          </p>
        </div>
      </div>

      {/* ── Card Details ─────────────────────────────────────── */}
      <div className="rounded-3xl border border-white/5 bg-card/60 backdrop-blur-xl p-8 flex flex-col gap-6">
        <h2 className="font-display text-xl font-bold text-foreground flex items-center gap-2">
          <Pencil size={18} className="text-primary" />
          Card Details
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Left */}
          <div className="flex flex-col gap-6">
            <div>
              <label className="block text-[11px] uppercase tracking-wider text-muted-foreground mb-1">
                Full Name
              </label>
              <div className="bg-background/50 border border-border rounded-lg p-3 text-sm text-muted-foreground font-medium">
                {currentUser?.full_name}
              </div>
            </div>

            <div>
              <label className="block text-[11px] uppercase tracking-wider text-muted-foreground mb-1">
                LinkedIn Profile URL <span className="text-red-400">*</span>
              </label>
              <input
                type="url"
                value={linkedinInput}
                onChange={(e) => setLinkedinInput(e.target.value)}
                placeholder="https://linkedin.com/in/yourprofile"
                className="w-full bg-background border border-border rounded-lg px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:border-primary transition-colors"
              />
            </div>
          </div>

          {/* Right: photo */}
          <div className="flex flex-col justify-between gap-3">
            <div>
              <label className="block text-[11px] uppercase tracking-wider text-muted-foreground mb-1">
                Profile Photo <span className="text-red-400">*</span>
              </label>
              <div
                onClick={() => photoRef.current?.click()}
                className="border-2 border-dashed border-border rounded-xl p-6 text-center cursor-pointer hover:border-primary/40 transition-colors flex flex-col justify-center items-center h-32"
              >
                {previewPhoto ? (
                  <img
                    src={previewPhoto}
                    alt="Profile preview"
                    className="w-16 h-16 rounded-full object-cover border-2 border-primary/40"
                  />
                ) : (
                  <>
                    <ImageIcon className="w-8 h-8 text-muted-foreground/50 mb-2" />
                    <p className="text-muted-foreground text-sm">Click to upload JPG or PNG</p>
                  </>
                )}
                <input
                  ref={photoRef}
                  type="file"
                  accept=".jpg,.jpeg,.png"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0]
                    if (!f) return
                    setSelectedPhoto(f)
                    setPhotoPreview(URL.createObjectURL(f))
                  }}
                />
              </div>
              {selectedPhoto && (
                <p className="text-xs text-primary mt-2 text-center truncate">{selectedPhoto.name}</p>
              )}
            </div>
          </div>
        </div>

        {/* Messages */}
        {error && (
          <div className="text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3">
            {error}
          </div>
        )}
        {success && (
          <div className="text-sm text-emerald-400 bg-emerald-500/10 border border-emerald-500/30 rounded-lg px-4 py-3">
            ✓ {success}
          </div>
        )}

        {/* Buttons */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-4 border-t border-white/5">
          <button
            onClick={handleGenerate}
            disabled={generate.isPending}
            className="w-full bg-primary text-primary-foreground font-bold py-3 rounded-xl hover:bg-primary/90 transition-all shadow-lg shadow-primary/20 flex items-center justify-center gap-2 disabled:opacity-60"
          >
            <Zap size={18} />
            {generate.isPending ? "Generating…" : hasCard ? "Regenerate ID Card" : "Generate ID Card"}
          </button>

          {hasCard && (
            <button
              onClick={() => downloadPdf.mutate()}
              disabled={downloadPdf.isPending}
              className="w-full bg-foreground/10 border border-border text-foreground font-bold py-3 rounded-xl hover:bg-foreground/20 transition-all flex items-center justify-center gap-2 min-h-[48px] disabled:opacity-60"
            >
              <Download size={18} className="text-primary" />
              {downloadPdf.isPending ? "Preparing…" : "Download ID Card as PDF"}
            </button>
          )}
        </div>

        {/* Note */}
        <div className="bg-primary/5 border border-primary/15 rounded-2xl p-5 text-sm text-muted-foreground">
          <div className="flex items-start gap-3">
            <Info size={18} className="text-primary shrink-0 mt-0.5" />
            <p>
              <strong className="text-foreground">Note:</strong> You can download and print this card in
              a standard <strong className="text-primary">CR80 format</strong> (measures 3.375" x 2.125" /
              85.60 mm x 54.00 mm) and place it in a card holder to be used in the workshops you deliver.
            </p>
          </div>
        </div>
      </div>

      {/* ── Card Preview ─────────────────────────────────────── */}
      <div className="rounded-3xl border border-white/5 bg-card/60 backdrop-blur-xl p-8 flex flex-col gap-6">
        <h2 className="font-display text-xl font-bold text-foreground flex items-center gap-2">
          <Eye size={18} className="text-primary" />
          Card Preview
        </h2>

        {generate.isPending ? (
          <div className="text-center py-8">
            <div className="w-10 h-10 border-2 border-white/10 border-t-primary rounded-full animate-spin mx-auto mb-3" />
            <p className="text-muted-foreground text-sm">Generating your ID card…</p>
          </div>
        ) : hasCard ? (
          <div className="flex flex-col gap-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="rounded-2xl border border-white/5 bg-card/40 overflow-hidden">
                <div className="px-4 pt-4 pb-1 text-[11px] uppercase tracking-wider text-muted-foreground font-medium">
                  Front
                </div>
                {frontSrc && <img src={frontSrc} alt="Front Card" className="w-full rounded-b-2xl" />}
              </div>
              <div className="rounded-2xl border border-white/5 bg-card/40 overflow-hidden">
                <div className="px-4 pt-4 pb-1 text-[11px] uppercase tracking-wider text-muted-foreground font-medium">
                  Back
                </div>
                {backSrc && <img src={backSrc} alt="Back Card" className="w-full rounded-b-2xl" />}
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs text-muted-foreground">
                ID: <span className="text-primary font-mono font-bold">{card.data?.card_id}</span>
              </span>
              <span className="text-muted-foreground/50">·</span>
              <span className="text-xs text-muted-foreground">Issued: {issued}</span>
            </div>
          </div>
        ) : (
          <div className="rounded-2xl border border-white/5 bg-card/40 p-12 text-center">
            <CreditCard className="w-16 h-16 text-muted-foreground/30 mx-auto mb-4" />
            <p className="text-muted-foreground text-sm">Your ID card will appear here after generation.</p>
          </div>
        )}
      </div>
    </div>
  )
}

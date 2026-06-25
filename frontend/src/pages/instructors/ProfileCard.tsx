import { useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Download, Upload } from "lucide-react"
import { generateIdCardApi, getIdCardApi, getProfileApi } from "@/api/instructors/instructor"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { PageHeader, Spinner } from "@/pages/instructors/components/common"

export default function ProfileCard() {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [linkedinUrl, setLinkedinUrl] = useState("")
  const [photo, setPhoto] = useState<File | null>(null)

  const profile = useQuery({ queryKey: ["instructor-profile"], queryFn: getProfileApi })
  const card = useQuery({ queryKey: ["instructor-id-card"], queryFn: getIdCardApi })

  const generate = useMutation({
    mutationFn: () => generateIdCardApi(photo!, linkedinUrl || profile.data?.linkedin_url || undefined),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["instructor-id-card"] })
      qc.invalidateQueries({ queryKey: ["instructor-profile"] })
      setPhoto(null)
    },
  })

  if (profile.isLoading || card.isLoading) return <Spinner />

  return (
    <div>
      <PageHeader title="Profile Card" subtitle="Generate your official SpacePoint instructor ID card." />

      {card.data?.front_url && (
        <div className="grid sm:grid-cols-2 gap-4 mb-6 max-w-md">
          <img src={card.data.front_url} alt="ID card front" className="rounded-xl border shadow-sm w-full" />
          <img src={card.data.back_url ?? ""} alt="ID card back" className="rounded-xl border shadow-sm w-full" />
        </div>
      )}

      {card.data?.card_id && (
        <p className="text-sm text-muted-foreground mb-4">
          Card ID: <span className="font-mono font-medium text-foreground">{card.data.card_id}</span>
          {card.data.pdf_url && (
            <a href={card.data.pdf_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 ml-3 text-primary hover:underline">
              <Download size={14} /> Download PDF
            </a>
          )}
        </p>
      )}

      <Card className="max-w-md">
        <CardContent className="p-5 space-y-4">
          <p className="text-sm font-semibold">{card.data?.front_url ? "Regenerate card" : "Generate your card"}</p>

          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1 block">Profile photo</label>
            <input ref={fileRef} type="file" accept="image/*" className="input" onChange={(e) => setPhoto(e.target.files?.[0] ?? null)} />
          </div>

          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1 block">LinkedIn URL (shown as QR code)</label>
            <input
              className="input" placeholder="https://linkedin.com/in/you"
              defaultValue={profile.data?.linkedin_url ?? ""}
              onChange={(e) => setLinkedinUrl(e.target.value)}
            />
          </div>

          <Button onClick={() => generate.mutate()} disabled={!photo || generate.isPending} className="w-full">
            <Upload size={16} className="mr-1.5" />
            {generate.isPending ? "Generating…" : "Generate card"}
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}

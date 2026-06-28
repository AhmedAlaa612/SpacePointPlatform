import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Save, Upload, CheckCircle2 } from "lucide-react"
import { getSettingsApi, upsertSettingApi, uploadAdminSignatureApi } from "@/api/admin/settings"
import { Spinner } from "@/pages/admin/components/common"

export default function Settings() {
  const qc = useQueryClient()
  const { data: settings, isLoading } = useQuery({ queryKey: ["admin-settings"], queryFn: getSettingsApi })
  
  const [signatoryName, setSignatoryName] = useState("")
  const [signatoryTitle, setSignatoryTitle] = useState("")
  const [loaded, setLoaded] = useState(false)
  const [savedName, setSavedName] = useState(false)
  const [savedTitle, setSavedTitle] = useState(false)

  if (settings && !loaded) {
    setSignatoryName(settings.admin_signatory_name ?? "")
    setSignatoryTitle(settings.admin_signatory_title ?? "")
    setLoaded(true)
  }

  const saveSignatoryName = useMutation({
    mutationFn: () => upsertSettingApi("admin_signatory_name", signatoryName),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-settings"] })
      setSavedName(true)
      setTimeout(() => setSavedName(false), 2000)
    },
  })

  const saveSignatoryTitle = useMutation({
    mutationFn: () => upsertSettingApi("admin_signatory_title", signatoryTitle),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-settings"] })
      setSavedTitle(true)
      setTimeout(() => setSavedTitle(false), 2000)
    },
  })

  const uploadSignature = useMutation({
    mutationFn: (file: File) => uploadAdminSignatureApi(file),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-settings"] }),
    onError: (err: any) => {
      alert(err?.response?.data?.detail || "Failed to upload signature image")
    }
  })

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-6 max-w-xl">
      <div>
        <h1 className="text-xl font-bold text-foreground tracking-tight">System Settings</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Manage system-wide defaults, document templates, and signatory configuration.
        </p>
      </div>

      <div className="flex flex-col gap-6">
        {/* Signatory Defaults Card */}
        <div className="bg-card border border-border rounded-2xl p-6 shadow-sm flex flex-col gap-5">
          <div>
            <h2 className="text-base font-semibold text-foreground">Signatory Defaults</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              These details are used as signatory information for certificates and letters across the platform.
            </p>
          </div>

          <div className="flex flex-col gap-4 border-b border-border pb-5">
            <div>
              <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1.5 block">
                Signatory Name
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={signatoryName}
                  onChange={(e) => setSignatoryName(e.target.value)}
                  placeholder="e.g. John Doe"
                  className="flex-1 h-10 px-3 bg-background border border-border rounded-xl text-sm focus:outline-none focus:border-primary text-foreground"
                />
                <button
                  onClick={() => saveSignatoryName.mutate()}
                  disabled={saveSignatoryName.isPending}
                  className="h-10 px-4 bg-primary text-primary-foreground font-semibold text-sm rounded-xl hover:opacity-90 transition-opacity flex items-center gap-1.5"
                >
                  <Save size={14} />
                  Save
                </button>
              </div>
              {savedName && (
                <p className="text-xs text-emerald-600 dark:text-emerald-400 mt-1 flex items-center gap-1">
                  <CheckCircle2 size={12} /> Signatory name saved
                </p>
              )}
            </div>

            <div>
              <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1.5 block">
                Signatory Title
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={signatoryTitle}
                  onChange={(e) => setSignatoryTitle(e.target.value)}
                  placeholder="e.g. Managing Director"
                  className="flex-1 h-10 px-3 bg-background border border-border rounded-xl text-sm focus:outline-none focus:border-primary text-foreground"
                />
                <button
                  onClick={() => saveSignatoryTitle.mutate()}
                  disabled={saveSignatoryTitle.isPending}
                  className="h-10 px-4 bg-primary text-primary-foreground font-semibold text-sm rounded-xl hover:opacity-90 transition-opacity flex items-center gap-1.5"
                >
                  <Save size={14} />
                  Save
                </button>
              </div>
              {savedTitle && (
                <p className="text-xs text-emerald-600 dark:text-emerald-400 mt-1 flex items-center gap-1">
                  <CheckCircle2 size={12} /> Signatory title saved
                </p>
              )}
            </div>
          </div>

          <div>
            <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2 block">
              Signature Image
            </label>
            <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
              <div className="relative overflow-hidden rounded-xl border border-border bg-muted/30 p-2 flex items-center justify-center min-h-[64px] min-w-[128px]">
                {settings?.admin_signature_url ? (
                  <img
                    src={settings.admin_signature_url}
                    alt="Current signature"
                    className="max-h-12 max-w-[200px] object-contain dark:invert"
                  />
                ) : (
                  <span className="text-xs text-muted-foreground italic">No signature uploaded</span>
                )}
              </div>
              
              <div className="flex flex-col gap-1.5">
                <label className="relative cursor-pointer h-9 px-4 bg-secondary text-secondary-foreground font-semibold text-xs rounded-xl hover:opacity-90 transition-opacity flex items-center gap-1.5 w-fit">
                  <Upload size={14} />
                  {uploadSignature.isPending ? "Uploading..." : "Upload Image"}
                  <input
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={(e) => {
                      const file = e.target.files?.[0]
                      if (file) uploadSignature.mutate(file)
                    }}
                  />
                </label>
                <p className="text-[10px] text-muted-foreground">
                  Supported formats: PNG, JPG, SVG. Transparent background recommended.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

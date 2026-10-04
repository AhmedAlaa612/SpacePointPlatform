import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Save, Upload, CheckCircle2, Bot, Ban } from "lucide-react"
import { getSettingsApi, upsertSettingApi, uploadAdminSignatureApi } from "@/api/admin/settings"
import { Spinner } from "@/pages/admin/components/common"
import { useToast } from "@/components/ui/toast"

export default function Settings() {
  const qc = useQueryClient()
  const toast = useToast()
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

  const isFinEnabled = settings?.fin_support_enabled !== "false"

  const toggleFin = useMutation({
    mutationFn: (enabled: boolean) =>
      upsertSettingApi("fin_support_enabled", enabled ? "true" : "false"),
    onSuccess: (_, enabled) => {
      qc.invalidateQueries({ queryKey: ["admin-settings"] })
      qc.invalidateQueries({ queryKey: ["lms-support-config"] })
      toast.success(enabled ? "Fin support messenger enabled for students" : "Fin support messenger disabled for students")
    },
    onError: () => {
      toast.error("Failed to update Fin support setting")
    },
  })

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
          Manage system-wide defaults, Fin student support assistant, and signatory configuration.
        </p>
      </div>

      <div className="flex flex-col gap-6">
        {/* Fin Student Support Assistant Card */}
        <div className="bg-card border border-border rounded-2xl p-6 shadow-sm flex flex-col gap-4">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary shrink-0 mt-0.5">
                <Bot size={20} />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-base font-semibold text-foreground">Fin Support Assistant (Intercom)</h2>
                  <span
                    className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold tracking-wide uppercase ${
                      isFinEnabled
                        ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20"
                        : "bg-muted text-muted-foreground border border-border"
                    }`}
                  >
                    {isFinEnabled ? "Active" : "Disabled"}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  Control whether Fin (the Intercom AI student support assistant) is visible to students on the learning platform (<code className="text-[11px] bg-muted px-1 py-0.5 rounded">/learn/*</code>).
                </p>
              </div>
            </div>

            <button
              type="button"
              disabled={toggleFin.isPending}
              onClick={() => toggleFin.mutate(!isFinEnabled)}
              className={`relative w-12 h-6 rounded-full transition-colors shrink-0 cursor-pointer ${
                isFinEnabled ? "bg-primary" : "bg-muted-foreground/30"
              }`}
              aria-label="Toggle Fin support assistant for students"
              aria-pressed={isFinEnabled}
            >
              <span
                className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${
                  isFinEnabled ? "translate-x-6" : ""
                }`}
              />
            </button>
          </div>

          <div className="text-[11px] text-muted-foreground bg-muted/40 rounded-xl p-3 border border-border/50">
            {isFinEnabled ? (
              <p className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400 font-medium">
                <CheckCircle2 size={13} />
                Students currently see the floating Fin launcher and can ask questions about missions, cohorts, and competitions.
              </p>
            ) : (
              <p className="flex items-center gap-1.5 text-muted-foreground font-medium">
                <Ban size={13} />
                Fin is completely turned off for students. No floating messenger or launcher widget is loaded on student pages.
              </p>
            )}
          </div>
        </div>

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

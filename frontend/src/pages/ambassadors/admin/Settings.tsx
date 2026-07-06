import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { getSettingsApi, updateSettingApi } from "@/api/ambassadors/admin"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { PageHeader, Spinner } from "@/pages/ambassadors/components/common"

export default function AmbassadorsAdminSettings() {
  return (
    <div>
      <PageHeader title="Ambassadors Admin" subtitle="Reward settings for leads, sessions and recruits." />
      <SettingsAdmin />
    </div>
  )
}

const REWARD_KEYS: { key: string; label: string; def: number }[] = [
  { key: "lead_points_reward", label: "Points per converted lead", def: 1000 },
  { key: "teacher_points_reward", label: "Points per recruited teacher", def: 500 },
  { key: "instructor_points_reward", label: "Points per recruited instructor", def: 500 },
  { key: "session_points_reward", label: "Points per completed session", def: 200 },
]

function SettingsAdmin() {
  const qc = useQueryClient()
  const { data: settings, isLoading } = useQuery({ queryKey: ["admin-settings"], queryFn: getSettingsApi })
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [saved, setSaved] = useState(false)

  const save = useMutation({
    mutationFn: async () => {
      const entries = REWARD_KEYS.map(({ key, def }) => [key, draft[key] ?? settings?.[key] ?? String(def)] as const)
      await Promise.all(entries.map(([key, value]) => updateSettingApi(key, value)))
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin-settings"] }); setSaved(true); setTimeout(() => setSaved(false), 2000) },
  })

  if (isLoading) return <Spinner />

  return (
    <Card className="max-w-xl">
      <CardHeader><CardTitle>Reward settings</CardTitle></CardHeader>
      <CardContent>
        <div className="space-y-4">
          {REWARD_KEYS.map(({ key, label, def }) => (
            <div key={key} className="flex items-center justify-between gap-3">
              <label className="text-sm">{label}</label>
              <div className="w-32">
                <input className="input" type="number" min={0} value={draft[key] ?? settings?.[key] ?? String(def)}
                  onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))} />
              </div>
            </div>
          ))}
        </div>
        <div className="flex items-center gap-3 mt-5">
          <Button onClick={() => save.mutate()} disabled={save.isPending}>{save.isPending ? "Saving…" : "Save changes"}</Button>
          {saved && <span className="text-sm text-green-600 dark:text-green-400">Saved ✓</span>}
        </div>
      </CardContent>
    </Card>
  )
}

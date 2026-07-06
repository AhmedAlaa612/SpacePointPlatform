import { useState } from "react"
import { Link } from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import { ExternalLink } from "lucide-react"
import { getUsersApi } from "@/api/admin/users"
import { getActivityLogApi, getAmbassadorNetworkApi, getFullNetworkApi } from "@/api/ambassadors/admin"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { EmptyState, PageHeader, Spinner } from "@/pages/ambassadors/components/common"
import { FullNetworkTree } from "@/pages/ambassadors/components/FullNetworkTree"
import { NetworkTree } from "@/pages/ambassadors/components/NetworkTree"
import { cn } from "@/lib/utils"

export default function AmbassadorsAdminNetwork() {
  return (
    <div>
      <PageHeader title="Ambassadors Admin" subtitle="Network across ambassadors, teachers and instructors." />
      <NetworkAdmin />
    </div>
  )
}

function NetworkAdmin() {
  const [view, setView] = useState<"full" | "ambassador">("full")
  const [selected, setSelected] = useState("")

  const users = useQuery({ queryKey: ["admin-users-all"], queryFn: getUsersApi })
  const ambassadors = (users.data ?? []).filter((u) => u.roles.includes("ambassador") && u.status === "active")

  const full = useQuery({ queryKey: ["admin-full-network"], queryFn: getFullNetworkApi, enabled: view === "full" })
  const single = useQuery({
    queryKey: ["admin-network", selected], queryFn: () => getAmbassadorNetworkApi(selected),
    enabled: view === "ambassador" && !!selected,
  })

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center gap-3 mb-4">
        <div className="flex rounded-lg border border-border overflow-hidden text-sm font-semibold w-fit">
          <button onClick={() => setView("full")} className={cn("px-4 py-2", view === "full" ? "bg-primary text-primary-foreground" : "text-muted-foreground")}>Full network</button>
          <button onClick={() => setView("ambassador")} className={cn("px-4 py-2", view === "ambassador" ? "bg-primary text-primary-foreground" : "text-muted-foreground")}>By ambassador</button>
        </div>
        {view === "ambassador" && (
          <select className="input !w-auto" value={selected} onChange={(e) => setSelected(e.target.value)}>
            <option value="">Select an ambassador…</option>
            {ambassadors.map((a) => <option key={a.id} value={a.id}>{a.full_name}</option>)}
          </select>
        )}
      </div>

      {view === "full" ? (
        full.isLoading || !full.data ? <Spinner /> : full.data.ambassadors.length === 0 ? (
          <EmptyState title="No active ambassadors yet" />
        ) : (
          <>
            <Card className="mb-5">
              <CardHeader><CardTitle>Platform network</CardTitle></CardHeader>
              <CardContent><FullNetworkTree ambassadors={full.data.ambassadors} /></CardContent>
            </Card>
            <ActivityLog />
          </>
        )
      ) : !selected ? (
        <EmptyState title="Pick an ambassador" hint="See their teacher/instructor network and sessions." />
      ) : single.isLoading || !single.data ? <Spinner /> : (
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>{single.data.ambassador.full_name}'s network</CardTitle>
            <Link to="/ambassadors/admin/ambassador/$ambassadorId" params={{ ambassadorId: selected }}>
              <Button size="sm" variant="outline"><ExternalLink size={14} className="mr-1.5" /> Full profile</Button>
            </Link>
          </CardHeader>
          <CardContent>
            <NetworkTree
              rootName={single.data.ambassador.full_name}
              teachers={single.data.teachers as any}
              instructors={single.data.instructors as any}
              sessions={single.data.sessions as any}
            />
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function ActivityLog() {
  const { data: events = [], isLoading } = useQuery({ queryKey: ["admin-activity"], queryFn: () => getActivityLogApi(80) })
  const KIND_STYLES: Record<string, string> = {
    points: "bg-green-50 text-green-600 dark:bg-green-950/30 dark:text-green-400",
    lead: "bg-blue-50 text-blue-600 dark:bg-blue-950/30 dark:text-blue-400",
    task: "bg-primary/15 text-primary",
    session: "bg-amber-50 text-amber-600 dark:bg-amber-950/30 dark:text-amber-400",
    signup: "bg-muted text-muted-foreground",
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Global activity</CardTitle>
        <p className="text-xs text-muted-foreground">All traffic across the platform, newest first.</p>
      </CardHeader>
      <CardContent>
        {isLoading ? <Spinner /> : events.length === 0 ? <EmptyState title="No activity yet" /> : (
          <div className="max-h-[420px] overflow-y-auto divide-y divide-border pr-1">
            {events.map((e, i) => (
              <div key={i} className="flex items-center justify-between gap-3 py-2.5">
                <div className="flex items-center gap-3 min-w-0">
                  <span className={cn("text-[10px] font-bold uppercase px-2 py-0.5 rounded-full shrink-0", KIND_STYLES[e.kind])}>{e.kind}</span>
                  <div className="min-w-0">
                    <p className="text-sm truncate">{e.actor && <span className="font-medium">{e.actor}</span>} {e.text}</p>
                    <p className="text-xs text-muted-foreground">{new Date(e.created_at).toLocaleString()}</p>
                  </div>
                </div>
                {e.amount != null && (
                  <span className={cn("text-sm font-semibold shrink-0", e.amount < 0 ? "text-destructive" : "text-green-600 dark:text-green-400")}>
                    {e.amount < 0 ? "" : "+"}{e.amount.toLocaleString()}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

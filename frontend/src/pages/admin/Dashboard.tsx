import { Link } from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import { Briefcase, GraduationCap, Network, CheckCircle2, ClipboardList } from "lucide-react"
import { getNotificationsApi } from "@/api/notifications"
import { getApplicationCountsApi } from "@/api/apply"
import { type Notification } from "@/types/shared"
import { Card, CardContent } from "@/components/ui/card"
import { PageHeader } from "@/pages/instructors/components/common"

interface DomainCardProps {
  to: string
  icon: React.ReactNode
  title: string
  notifications: Notification[]
  isLoading: boolean
}

function DomainCard({ to, icon, title, notifications, isLoading }: DomainCardProps) {
  return (
    <Card className="hover:border-primary/50 transition-all flex flex-col h-[380px] shadow-sm bg-card border-border overflow-hidden">
      <CardContent className="p-5 flex flex-col h-full gap-4">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border/40 pb-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center shrink-0">
              {icon}
            </div>
            <div>
              <p className="font-semibold text-foreground">{title}</p>
              <Link to={to} className="text-xs text-primary hover:underline font-medium">
                Manage Domain &rarr;
              </Link>
            </div>
          </div>
          {notifications.length > 0 && (
            <span className="flex h-5 px-2 items-center justify-center rounded-full bg-red-500/10 text-[10px] font-bold text-red-500">
              {notifications.length} unread
            </span>
          )}
        </div>

        {/* Notifications Log */}
        <div className="flex-1 overflow-y-auto pr-1 space-y-2.5">
          {isLoading ? (
            <div className="h-full flex items-center justify-center">
              <div className="w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin" />
            </div>
          ) : notifications.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center gap-1.5 text-center text-muted-foreground p-4">
              <CheckCircle2 size={24} className="text-emerald-500" />
              <div>
                <p className="text-xs font-semibold text-foreground">All caught up!</p>
                <p className="text-[10px]">No unread notifications for this domain.</p>
              </div>
            </div>
          ) : (
            notifications.map((n) => (
              <div
                key={n.id}
                className="p-3 bg-muted/30 border border-border/50 rounded-xl hover:bg-muted/50 transition-colors flex flex-col gap-1"
              >
                <p className="text-xs font-semibold text-foreground leading-snug">{n.title}</p>
                {n.body && <p className="text-[10px] text-muted-foreground line-clamp-2 leading-relaxed">{n.body}</p>}
                <p className="text-[9px] text-muted-foreground/60 mt-0.5">
                  {new Date(n.created_at).toLocaleDateString()} at {new Date(n.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </p>
              </div>
            ))
          )}
        </div>
      </CardContent>
    </Card>
  )
}

export default function AdminHub() {
  const { data: notifications = [], isLoading } = useQuery<Notification[]>({
    queryKey: ["notifications"],
    queryFn: getNotificationsApi,
    refetchInterval: 30_000,
  })

  const { data: appCounts } = useQuery({
    queryKey: ["admin-application-counts"],
    queryFn: getApplicationCountsApi,
    staleTime: 60_000,
  })

  const pendingApps = Object.values(appCounts ?? {}).reduce(
    (sum, statusMap) => sum + (statusMap["pending"] ?? 0), 0
  )

  const unread = notifications.filter((n) => !n.is_read)

  const getNotificationDomain = (n: Notification) => {
    if (n.type === "ambassador") return "ambassadors"
    if (n.type === "instructor") return "instructors"
    if (n.type === "intern") return "interns"

    const text = (n.title + " " + (n.body || "")).toLowerCase()
    if (
      text.includes("instructor") ||
      text.includes("payment") ||
      text.includes("contract") ||
      text.includes("workshop")
    ) {
      return "instructors"
    }
    if (
      text.includes("proposal") ||
      text.includes("epic") ||
      text.includes("intern") ||
      text.includes("team") ||
      text.includes("assigned to:") ||
      text.includes("task status")
    ) {
      return "interns"
    }
    return "ambassadors" // fallback
  }

  const ambassadorNotifications = unread.filter((n) => getNotificationDomain(n) === "ambassadors")
  const instructorNotifications = unread.filter((n) => getNotificationDomain(n) === "instructors")
  const internNotifications = unread.filter((n) => getNotificationDomain(n) === "interns")

  return (
    <div>
      <PageHeader title="Admin Dashboard" subtitle="Overview of platform domains and unread logs." />

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6 mt-6">
        <DomainCard
          to="/ambassadors/admin"
          icon={<Network size={20} />}
          title="Ambassadors"
          notifications={ambassadorNotifications}
          isLoading={isLoading}
        />
        <DomainCard
          to="/instructors/admin"
          icon={<GraduationCap size={20} />}
          title="Instructors"
          notifications={instructorNotifications}
          isLoading={isLoading}
        />
        <DomainCard
          to="/interns"
          icon={<Briefcase size={20} />}
          title="Interns"
          notifications={internNotifications}
          isLoading={isLoading}
        />
      </div>

      {/* Applications quick-link */}
      <div className="mt-6">
        <Link to="/admin/applications">
          <Card className="hover:border-primary/50 transition-all shadow-sm border-border">
            <CardContent className="p-5 flex items-center gap-4">
              <div className="w-10 h-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center shrink-0">
                <ClipboardList size={20} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-foreground">Applications</p>
                <p className="text-xs text-muted-foreground">Review incoming ambassador, intern, teacher and facilitator applications</p>
              </div>
              {pendingApps > 0 && (
                <span className="flex h-6 px-2.5 items-center justify-center rounded-full bg-amber-500/10 text-xs font-bold text-amber-600 dark:text-amber-400 shrink-0">
                  {pendingApps} pending
                </span>
              )}
            </CardContent>
          </Card>
        </Link>
      </div>
    </div>
  )
}

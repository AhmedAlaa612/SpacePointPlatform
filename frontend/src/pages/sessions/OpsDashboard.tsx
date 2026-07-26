import { useQuery } from "@tanstack/react-query"
import { BookOpen, CalendarDays, DollarSign, GraduationCap, Target, TrendingUp, Users } from "lucide-react"
import { getOpsDashboardApi, type OpsDashboardData } from "@/api/sessions/dashboard"
import { Card, CardContent } from "@/components/ui/card"
import { PageHeader, Spinner } from "@/pages/instructors/components/common"

interface KpiCardProps {
  label: string
  value: string
  icon: React.ReactNode
  trend?: string
}

function KpiCard({ label, value, icon, trend }: KpiCardProps) {
  return (
    <Card className="hover:border-primary/30 transition-all shadow-sm">
      <CardContent className="p-5 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
          <p className="mt-1 text-2xl font-bold text-foreground">{value}</p>
          {trend && <p className="mt-0.5 text-xs text-muted-foreground">{trend}</p>}
        </div>
        <div className="shrink-0 w-10 h-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center">
          {icon}
        </div>
      </CardContent>
    </Card>
  )
}

interface KpiDef {
  key: keyof OpsDashboardData
  label: string
  icon: React.ReactNode
  format: (v: OpsDashboardData[keyof OpsDashboardData]) => string
  trend?: (v: OpsDashboardData) => string | undefined
}

const KPI_DEFINITIONS: KpiDef[] = [
  {
    key: "students_trained",
    label: "Students Trained",
    icon: <GraduationCap size={20} />,
    format: (v) => `${v}`,
  },
  {
    key: "active_cohorts",
    label: "Active Cohorts",
    icon: <BookOpen size={20} />,
    format: (v) => `${v}`,
  },
  {
    key: "upcoming_meetings_7d",
    label: "Upcoming Sessions (7d)",
    icon: <CalendarDays size={20} />,
    format: (v) => `${v}`,
  },
  {
    key: "attendance_rate_30d",
    label: "Attendance Rate (30d)",
    icon: <TrendingUp size={20} />,
    format: (v) => `${(Number(v) * 100).toFixed(1)}%`,
  },
  {
    key: "unpaid_count",
    label: "Unpaid Registrations",
    icon: <DollarSign size={20} />,
    format: (v) => `${v}`,
    trend: (data) => `Total: AED ${data.unpaid_sum}`,
  },
  {
    key: "registrations_7d",
    label: "New Registrations (7d)",
    icon: <Users size={20} />,
    format: (v) => `${v}`,
  },
  {
    key: "open_calls_pending",
    label: "Open Staffing Calls",
    icon: <Target size={20} />,
    format: (v) => `${v}`,
  },
]

export default function OpsDashboard() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["ops-dashboard"],
    queryFn: getOpsDashboardApi,
    refetchInterval: 60_000,
    refetchIntervalInBackground: true,
    retry: 1,
    staleTime: 30_000,
  })

  return (
    <div>
      <PageHeader title="Operations Dashboard" subtitle="Real-time overview of sessions, registrations, and staffing." />
      {isLoading ? (
        <div className="mt-12"><Spinner /></div>
      ) : isError || !data ? (
        <p className="mt-12 text-sm text-destructive">Could not load dashboard data. {error instanceof Error ? error.message : ""}</p>
      ) : (
        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {KPI_DEFINITIONS.map((def) => (
            <KpiCard
              key={def.key}
              label={def.label}
              value={def.format(data[def.key])}
              icon={def.icon}
              trend={def.trend ? def.trend(data) : undefined}
            />
          ))}
        </div>
      )}
    </div>
  )
}

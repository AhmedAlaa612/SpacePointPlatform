import { useQuery } from "@tanstack/react-query"
import { CheckCircle2, ClipboardList, FileEdit, Ticket, XCircle } from "lucide-react"
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { getAdminOverviewApi, listApplicantsApi, listInvitationsApi } from "@/api/instructors/admin"
import { PageHeader, Spinner, StatCard } from "@/pages/instructors/components/common"

/**
 * Overview — stat row missing from the legacy tab-bar version (reference:
 * admin_dashboard.html Applicants view). The first stat row is derived
 * client-side from the same applicants/invitations lists already used by
 * the other admin pages. The second stat row + 3 charts (universities /
 * cities distribution + joined-users trend) come from the extended
 * GET /instructors/admin/overview endpoint.
 */

const ACCENT = "#A77DFF" // --primary (space-accent), resolved to a concrete hex for recharts
const DONUT_COLORS = ["#A77DFF", "#6DD3FB", "#F7B267", "#F25F5C", "#70C1B3", "#9381FF", "#5FAD56", "#F4A6C6"]

function SectionHeading({ title }: { title: string }) {
  return (
    <h3 className="text-lg font-bold mb-4 flex items-center">
      <span className="w-1.5 h-6 bg-primary rounded-full mr-3" />
      {title}
    </h3>
  )
}

export default function InstructorsAdminOverview() {
  const { data: applicants, isLoading: loadingApplicants } = useQuery({
    queryKey: ["admin-applicants"],
    queryFn: listApplicantsApi,
  })
  const { data: invitations, isLoading: loadingInvitations } = useQuery({
    queryKey: ["admin-invitations"],
    queryFn: listInvitationsApi,
  })
  const { data: overview, isLoading: loadingOverview } = useQuery({
    queryKey: ["admin-overview"],
    queryFn: getAdminOverviewApi,
  })

  if (loadingApplicants || loadingInvitations || loadingOverview) return <Spinner />

  const all = applicants ?? []
  const totalStarted = all.length
  const totalApproved = all.filter((a) => a.status === "approved").length
  const totalRejected = all.filter((a) => a.status === "rejected").length
  const totalDraft = all.filter((a) => a.status === "in_progress").length

  type Invitation = NonNullable<typeof invitations>[number]
  const topCode = (invitations ?? []).reduce<Invitation | null>((top, i) => {
    if (!top || i.used_count > top.used_count) return i
    return top
  }, null)

  const universityData = [...(overview?.university_distribution ?? [])]
    .sort((a, b) => b.count - a.count)
    .slice(0, 10)
  const cityData = overview?.city_distribution ?? []
  const trendData = overview?.signup_trend ?? []

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Overview" subtitle="Scholarship pipeline at a glance." />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <StatCard icon={<ClipboardList size={18} />} label="Total Started" value={totalStarted} />
        <StatCard icon={<CheckCircle2 size={18} />} label="Approved" value={totalApproved} />
        <StatCard icon={<XCircle size={18} />} label="Rejected" value={totalRejected} />
        <StatCard icon={<FileEdit size={18} />} label="Draft Apps" value={totalDraft} />
        <StatCard
          icon={<Ticket size={18} />}
          label="Top Code"
          value={topCode ? topCode.code : "—"}
          sub={topCode ? `${topCode.used_count} use(s)` : undefined}
        />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        <div className="rounded-2xl bg-card/70 dark:bg-card/60 backdrop-blur-xl ring-1 ring-black/5 dark:ring-white/10 p-6">
          <span className="text-sm text-muted-foreground block mb-1">Total Applicants</span>
          <span className="text-3xl font-bold">{overview?.total_applicants ?? 0}</span>
        </div>
        <div className="rounded-2xl bg-card/70 dark:bg-card/60 backdrop-blur-xl ring-1 ring-black/5 dark:ring-white/10 p-6">
          <span className="text-sm text-muted-foreground block mb-1">Total Instructors</span>
          <span className="text-3xl font-bold text-primary">{overview?.total_instructors ?? 0}</span>
        </div>
        <div className="rounded-2xl bg-card/70 dark:bg-card/60 backdrop-blur-xl ring-1 ring-black/5 dark:ring-white/10 p-6">
          <span className="text-sm text-muted-foreground block mb-1">Total Facilitators</span>
          <span className="text-3xl font-bold">{overview?.total_facilitators ?? 0}</span>
        </div>
        <div className="rounded-2xl bg-card/70 dark:bg-card/60 backdrop-blur-xl ring-1 ring-black/5 dark:ring-white/10 p-6">
          <span className="text-sm text-muted-foreground block mb-1">Active Users (30d)</span>
          <span className="text-3xl font-bold text-green-500 dark:text-green-400">{overview?.active_users_30d ?? 0}</span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div className="rounded-2xl bg-card/70 dark:bg-card/60 backdrop-blur-xl ring-1 ring-black/5 dark:ring-white/10 p-6">
          <SectionHeading title="Universities Distribution" />
          {universityData.length === 0 ? (
            <p className="text-sm text-muted-foreground py-8 text-center">No university data yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height={440}>
              <BarChart data={universityData} margin={{ top: 8, right: 8, left: 0, bottom: 150 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-muted-foreground/20" />
                <XAxis
                  dataKey="name"
                  angle={-45}
                  textAnchor="end"
                  interval={0}
                  height={165}
                  tickMargin={8}
                  tickFormatter={(value: string) => (value.length > 24 ? `${value.slice(0, 24)}…` : value)}
                  tick={{ fontSize: 11, fill: "currentColor" }}
                  className="text-muted-foreground"
                />
                <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "currentColor" }} className="text-muted-foreground" />
                <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12 }} />
                <Bar dataKey="count" name="Applicants" fill={ACCENT} radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="rounded-2xl bg-card/70 dark:bg-card/60 backdrop-blur-xl ring-1 ring-black/5 dark:ring-white/10 p-6">
          <SectionHeading title="Cities Distribution" />
          {cityData.length === 0 ? (
            <p className="text-sm text-muted-foreground py-8 text-center">No city data yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height={320}>
              <PieChart>
                <Pie
                  data={cityData}
                  dataKey="count"
                  nameKey="name"
                  innerRadius={60}
                  outerRadius={100}
                  paddingAngle={2}
                >
                  {cityData.map((entry, index) => (
                    <Cell key={entry.name} fill={DONUT_COLORS[index % DONUT_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12 }} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      <div className="rounded-2xl bg-card/70 dark:bg-card/60 backdrop-blur-xl ring-1 ring-black/5 dark:ring-white/10 p-6 w-full">
        <SectionHeading title="Joined Users Trend (Comparison Between Months)" />
        {trendData.length === 0 ? (
          <p className="text-sm text-muted-foreground py-8 text-center">No signup data yet.</p>
        ) : (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={trendData} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-muted-foreground/20" />
              <XAxis dataKey="month" tick={{ fontSize: 11, fill: "currentColor" }} className="text-muted-foreground" />
              <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "currentColor" }} className="text-muted-foreground" />
              <Tooltip contentStyle={{ borderRadius: 12, fontSize: 12 }} />
              <Line type="monotone" dataKey="count" name="Joined Users" stroke={ACCENT} strokeWidth={2.5} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}

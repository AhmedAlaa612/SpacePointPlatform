import { Link } from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import { Briefcase, GraduationCap, Network } from "lucide-react"
import { getAdminOverviewApi } from "@/api/instructors/admin"
import { Card, CardContent } from "@/components/ui/card"
import { PageHeader, Spinner } from "@/pages/instructors/components/common"

function DomainCard({
  to, icon, title, updates, disabled,
}: { to?: string; icon: React.ReactNode; title: string; updates: string[]; disabled?: boolean }) {
  const content = (
    <Card className={disabled ? "opacity-60" : "hover:border-primary transition-colors"}>
      <CardContent className="p-5">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center shrink-0">{icon}</div>
          <p className="font-semibold">{title}</p>
        </div>
        <div className="space-y-1">
          {updates.map((u) => (
            <p key={u} className="text-sm text-muted-foreground">{u}</p>
          ))}
        </div>
      </CardContent>
    </Card>
  )
  return disabled || !to ? content : <Link to={to}>{content}</Link>
}

export default function AdminHub() {
  const { data, isLoading } = useQuery({ queryKey: ["admin-overview"], queryFn: getAdminOverviewApi })

  if (isLoading) return <Spinner />

  return (
    <div>
      <PageHeader title="Admin" subtitle="Pick a domain to manage." />

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <DomainCard
          to="/instructors/admin"
          icon={<GraduationCap size={20} />}
          title="Instructors"
          updates={[
            `${data?.pending_applications ?? 0} application(s) to review`,
            `${data?.pending_payment_signatures ?? 0} payment letter(s) awaiting signature`,
            `${data?.total_instructors ?? 0} active instructor(s)`,
          ]}
        />
        <DomainCard
          to="/interns/admin"
          icon={<Briefcase size={20} />}
          title="Interns"
          updates={["Manage users and teams"]}
        />
        <DomainCard
          to="/ambassadors/admin"
          icon={<Network size={20} />}
          title="Ambassadors"
          updates={["Network, approvals, leads, sessions, titles & badges"]}
        />
      </div>
    </div>
  )
}

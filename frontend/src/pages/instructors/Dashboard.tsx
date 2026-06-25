import { Link } from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import { BookOpen, FileText, IdCard, Wallet } from "lucide-react"
import { listTrainingApi } from "@/api/instructors/training"
import { getPaymentSummaryApi } from "@/api/instructors/payments"
import { useAuth } from "@/context/AuthContext"
import { Card, CardContent } from "@/components/ui/card"
import { PageHeader, Spinner, StatCard } from "@/pages/instructors/components/common"

export default function InstructorDashboard() {
  const { currentUser } = useAuth()
  const training = useQuery({ queryKey: ["instructor-training"], queryFn: listTrainingApi })
  const summary = useQuery({ queryKey: ["instructor-payment-summary"], queryFn: getPaymentSummaryApi })

  if (training.isLoading || summary.isLoading) return <Spinner />

  const totalVideos = (training.data ?? []).flatMap((m) => m.videos).length
  const completedVideos = (training.data ?? []).flatMap((m) => m.videos).filter((v) => v.is_completed).length

  return (
    <div>
      <PageHeader title={`Welcome, ${currentUser?.full_name ?? "Instructor"}`} subtitle="Your SpacePoint instructor portal." />

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
        <StatCard icon={<Wallet size={20} />} label="Earned (AED)" value={summary.data?.total_earned_aed.toLocaleString() ?? 0}
          sub={summary.data?.pending_signature ? `${summary.data.pending_signature} pending signature` : "All signed"} />
        <StatCard icon={<BookOpen size={20} />} label="Training" value={`${completedVideos}/${totalVideos}`} sub="Videos completed" />
        <StatCard icon={<FileText size={20} />} label="Sessions" value={summary.data?.total_sessions ?? 0} sub="Workshops delivered" />
        <StatCard icon={<IdCard size={20} />} label="ID Card" value="—" sub="See Profile Card" />
      </div>

      <div className="grid sm:grid-cols-2 gap-4">
        <Link to="/instructors/training">
          <Card className="hover:border-primary transition-colors">
            <CardContent className="p-5">
              <p className="font-semibold">SatKit Training</p>
              <p className="text-sm text-muted-foreground mt-1">Watch training videos and track your progress.</p>
            </CardContent>
          </Card>
        </Link>
        <Link to="/instructors/library">
          <Card className="hover:border-primary transition-colors">
            <CardContent className="p-5">
              <p className="font-semibold">Library</p>
              <p className="text-sm text-muted-foreground mt-1">Shared workshop materials and resources.</p>
            </CardContent>
          </Card>
        </Link>
        <Link to="/instructors/payments">
          <Card className="hover:border-primary transition-colors">
            <CardContent className="p-5">
              <p className="font-semibold">Payments</p>
              <p className="text-sm text-muted-foreground mt-1">View and sign your facilitator payment letters.</p>
            </CardContent>
          </Card>
        </Link>
        <Link to="/instructors/profile-card">
          <Card className="hover:border-primary transition-colors">
            <CardContent className="p-5">
              <p className="font-semibold">Profile Card</p>
              <p className="text-sm text-muted-foreground mt-1">Generate your official SpacePoint ID card.</p>
            </CardContent>
          </Card>
        </Link>
      </div>
    </div>
  )
}

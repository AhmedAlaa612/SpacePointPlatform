import { useState } from "react"
import { Link } from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import { BookOpen, CheckCircle2, CreditCard, GraduationCap, Wallet } from "lucide-react"
import { listTrainingApi } from "@/api/instructors/training"
import { getPaymentSummaryApi } from "@/api/instructors/payments"
import { getIdCardApi } from "@/api/instructors/instructor"
import { useAuth } from "@/context/AuthContext"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Spinner } from "@/pages/instructors/components/common"
import { cn } from "@/lib/utils"

function GlassCard({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div className={cn("rounded-2xl bg-card/60 backdrop-blur-xl ring-1 ring-black/5 dark:ring-white/10 p-5", className)}>
      {children}
    </div>
  )
}

export default function InstructorDashboard() {
  const { currentUser } = useAuth()
  const training = useQuery({ queryKey: ["instructor-training"], queryFn: listTrainingApi })
  const summary = useQuery({ queryKey: ["instructor-payment-summary"], queryFn: getPaymentSummaryApi })
  const idCard = useQuery({ queryKey: ["instructor-id-card", "instructor"], queryFn: () => getIdCardApi("instructor") })
  const [cardView, setCardView] = useState<{ side: "front" | "back"; b64: string } | null>(null)

  if (training.isLoading || summary.isLoading) return <Spinner />

  const videos = (training.data ?? []).flatMap((m) => m.videos)
  const totalVideos = videos.length
  const completedVideos = videos.filter((v) => v.is_completed).length
  const proficiency = totalVideos ? Math.round((completedVideos / totalVideos) * 100) : 0

  const card = idCard.data
  const cardGenerated = !!(card?.card_id || card?.generated_at)
  const firstName = (currentUser?.full_name ?? "Instructor").split(" ")[0]

  const nextSteps = [
    {
      done: cardGenerated,
      icon: <CreditCard size={16} />,
      title: cardGenerated ? "Instructor ID Card — Generated ✓" : "Generate your Instructor ID Card",
      desc: "View or regenerate your SpacePoint ID card.",
      to: "/instructors/documents",
    },
    {
      done: completedVideos > 0,
      icon: <BookOpen size={16} />,
      title: "Start SatKit Hands-On Training",
      desc: "Access the video library and operational manuals for the SpacePoint physical kits.",
      to: "/instructors/training",
    },
  ]

  return (
    <div className="flex flex-col gap-6 animate-fade-in">
      {/* Hero */}
      <GlassCard className="relative overflow-hidden">
        <div className="pointer-events-none absolute -right-20 -top-24 h-64 w-64 rounded-full bg-primary/10 blur-3xl" />
        <div className="relative flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="max-w-xl">
            <h1 className="font-display text-3xl font-bold tracking-tight">Welcome aboard, {firstName}!</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              You are now an officially certified SpacePoint Instructor. Explore your dashboard to access training
              material, instructional resources, and classroom tools.
            </p>
          </div>
          <span className="inline-flex shrink-0 items-center gap-2 self-start rounded-full border border-emerald-500/30 bg-emerald-500/10 px-4 py-2 text-xs font-bold uppercase tracking-wider text-emerald-500 dark:text-emerald-400">
            <span className="h-2 w-2 rounded-full bg-emerald-500" /> Status: Active Instructor
          </span>
        </div>
      </GlassCard>

      {/* Stat cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {/* SatKit proficiency */}
        <GlassCard>
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">SatKit Proficiency</p>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="font-display text-4xl font-bold text-foreground">{proficiency}%</span>
            <span className="text-xs text-muted-foreground">Modules Completed</span>
          </div>
          <div className="mt-4 h-1.5 w-full overflow-hidden rounded-full bg-foreground/10">
            <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${proficiency}%` }} />
          </div>
        </GlassCard>

        {/* Classroom sessions */}
        <GlassCard>
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Classroom Sessions</p>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="font-display text-4xl font-bold text-foreground">{summary.data?.total_sessions ?? 0}</span>
            <span className="text-xs text-muted-foreground">
              {summary.data?.total_hours ? `${summary.data.total_hours}h logged` : "Hours Logged"}
            </span>
          </div>
          <p className="mt-4 text-xs text-primary">Feature unlocking soon</p>
        </GlassCard>

        {/* Instructor ID pin */}
        <GlassCard>
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Instructor ID Pin</p>
          <p className="mt-2 font-display text-2xl font-bold tracking-[0.15em] text-foreground">
            {card?.card_id ?? "—"}
          </p>
          <p className="mt-3 text-xs text-muted-foreground">Use this ID when requesting physical hardware kits.</p>
        </GlassCard>

        {/* Instructor ID card */}
        <GlassCard>
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Instructor ID Card</p>
          {cardGenerated ? (
            <>
              <span className="mt-2 inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-500 dark:text-emerald-400">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> Generated
              </span>
              <p className="mt-2 font-mono text-xs text-muted-foreground">{card?.card_id}</p>
              <div className="mt-3 flex gap-2">
                {card?.front_b64 && (
                  <button
                    onClick={() => setCardView({ side: "front", b64: card.front_b64! })}
                    className="rounded-lg border border-border px-2.5 py-1 text-xs font-medium text-foreground hover:bg-foreground/5"
                  >
                    View Front
                  </button>
                )}
                {card?.back_b64 && (
                  <button
                    onClick={() => setCardView({ side: "back", b64: card.back_b64! })}
                    className="rounded-lg border border-border px-2.5 py-1 text-xs font-medium text-foreground hover:bg-foreground/5"
                  >
                    View Back
                  </button>
                )}
              </div>
            </>
          ) : (
            <Link
              to="/instructors/documents"
              className="mt-3 inline-flex rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground hover:bg-primary/90"
            >
              Generate Card
            </Link>
          )}
        </GlassCard>
      </div>

      {/* Recommended next steps */}
      <GlassCard>
        <div className="mb-4 flex items-center gap-2">
          <GraduationCap size={18} className="text-primary" />
          <h2 className="font-display text-lg font-bold">Recommended Next Steps</h2>
        </div>
        <div className="flex flex-col gap-3">
          {nextSteps.map((s) => (
            <Link
              key={s.title}
              to={s.to}
              className="flex items-center gap-4 rounded-xl border border-border/60 bg-card/40 p-4 transition-colors hover:border-primary/40 hover:bg-foreground/5"
            >
              <span
                className={cn(
                  "flex h-9 w-9 shrink-0 items-center justify-center rounded-full",
                  s.done ? "bg-emerald-500/15 text-emerald-500 dark:text-emerald-400" : "bg-primary/10 text-primary",
                )}
              >
                {s.done ? <CheckCircle2 size={16} /> : s.icon}
              </span>
              <div className="min-w-0">
                <p className="text-sm font-semibold text-foreground">{s.title}</p>
                <p className="text-xs text-muted-foreground">{s.desc}</p>
              </div>
            </Link>
          ))}
        </div>
      </GlassCard>

      {/* Quick links */}
      <div className="grid gap-4 sm:grid-cols-3">
        <Link to="/instructors/library">
          <GlassCard className="h-full transition-colors hover:border-primary/40 hover:bg-foreground/5">
            <BookOpen size={18} className="text-primary" />
            <p className="mt-2 font-semibold">Library</p>
            <p className="mt-1 text-sm text-muted-foreground">Shared workshop materials and resources.</p>
          </GlassCard>
        </Link>
        <Link to="/instructors/payments">
          <GlassCard className="h-full transition-colors hover:border-primary/40 hover:bg-foreground/5">
            <Wallet size={18} className="text-primary" />
            <p className="mt-2 font-semibold">Payments</p>
            <p className="mt-1 text-sm text-muted-foreground">View and sign your facilitator payment letters.</p>
          </GlassCard>
        </Link>
        <Link to="/instructors/profile">
          <GlassCard className="h-full transition-colors hover:border-primary/40 hover:bg-foreground/5">
            <CreditCard size={18} className="text-primary" />
            <p className="mt-2 font-semibold">Profile</p>
            <p className="mt-1 text-sm text-muted-foreground">Your profile info and official SpacePoint ID card.</p>
          </GlassCard>
        </Link>
      </div>

      {/* ID card image viewer */}
      <Dialog open={!!cardView} onOpenChange={(o) => !o && setCardView(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Instructor ID Card — {cardView?.side === "front" ? "Front" : "Back"}</DialogTitle>
          </DialogHeader>
          {cardView && (
            <img
              src={`data:image/png;base64,${cardView.b64}`}
              alt={`ID card ${cardView.side}`}
              className="w-full rounded-xl border border-border"
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}

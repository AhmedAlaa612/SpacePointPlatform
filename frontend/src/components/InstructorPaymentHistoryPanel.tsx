import { useQuery } from "@tanstack/react-query"
import {
  Building2,
  Calendar,
  CalendarCheck,
  Clock,
  Download,
  ExternalLink,
  FileCheck2,
  TrendingUp,
  Wallet,
} from "lucide-react"
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { getInstructorPaymentHistoryApi } from "@/api/instructors/payments_admin"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/primitives"
import { cn } from "@/lib/utils"
import type { PaymentLetter } from "@/types/instructors"

const STATUS_BADGE: Record<PaymentLetter["status"], string> = {
  draft: "bg-muted/70 text-foreground border border-border",
  published:
    "bg-[#653F84]/12 text-[#653F84] dark:bg-purple-500/20 dark:text-purple-200 border border-[#653F84]/30",
  signed: "bg-[#653F84] text-white border border-[#653F84]",
  paid: "bg-emerald-600/15 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300 border border-emerald-600/35",
}

function letterTotal(l: PaymentLetter): number {
  return (
    l.sessions.reduce((s, x) => s + (x.compensation_aed || 0), 0) +
    l.addons.reduce((s, x) => s + (x.amount_aed || 0), 0)
  )
}

export function InstructorPaymentHistoryPanel({
  userId,
  compact = false,
  onOpenLetter,
}: {
  userId: string
  compact?: boolean
  onOpenLetter?: (letterId: string) => void
}) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["instructor-payment-history", userId],
    queryFn: () => getInstructorPaymentHistoryApi(userId),
    retry: false,
  })

  if (isLoading) {
    return (
      <div className="sp-subcard rounded-[10px] bg-card p-5">
        <Spinner className="py-8" size="sm" />
      </div>
    )
  }

  if (isError || !data) {
    return null
  }

  const kpis = [
    {
      label: "Total Paid",
      value: `AED ${data.total_paid_aed.toLocaleString()}`,
      icon: Wallet,
    },
    {
      label: "Paid Letters",
      value: data.paid_letters_count,
      icon: FileCheck2,
    },
    {
      label: "Paid Sessions",
      value: data.paid_sessions_count,
      icon: CalendarCheck,
    },
    {
      label: "Paid Hours",
      value: data.paid_hours_count,
      icon: Clock,
    },
    {
      label: "Avg / Session",
      value: `AED ${data.avg_aed_per_session.toLocaleString()}`,
      icon: TrendingUp,
    },
  ]

  const hasInFlight =
    data.draft_letters_count > 0 ||
    data.published_letters_count > 0 ||
    data.signed_letters_count > 0

  return (
    <div className="sp-subcard rounded-[10px] bg-card p-5 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <p className="text-xs font-extrabold uppercase tracking-wider text-muted-foreground">
            Payment History &amp; Analysis
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {data.bank_name && (
            <span className="inline-flex items-center gap-1.5 rounded-[10px] border border-border px-2.5 py-1 text-[11px] font-semibold text-foreground">
              <Building2 size={12} /> {data.bank_name}
            </span>
          )}
          <span
            className={cn(
              "inline-flex items-center rounded-[10px] px-2.5 py-1 text-[11px] font-bold uppercase tracking-wide",
              data.bank_details_complete
                ? "bg-emerald-600/15 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300 border border-emerald-600/35"
                : "bg-rose-600/12 text-rose-700 dark:bg-rose-500/20 dark:text-rose-300 border border-rose-600/30",
            )}
          >
            {data.bank_details_complete ? "Bank Ready" : "Bank Incomplete"}
          </span>
        </div>
      </div>

      {/* Paid-Only KPI Grid */}
      <div
        className={cn(
          "grid gap-3",
          compact ? "grid-cols-2" : "grid-cols-2 sm:grid-cols-3 lg:grid-cols-5",
        )}
      >
        {kpis.map((k) => {
          const Icon = k.icon
          return (
            <div
              key={k.label}
              className="rounded-[10px] border border-border bg-background p-3 flex items-center justify-between gap-2.5"
            >
              <div>
                <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                  {k.label}
                </p>
                <p className="mt-1 font-display text-lg font-extrabold text-foreground tabular-nums">
                  {k.value}
                </p>
              </div>
              <div className="w-8 h-8 rounded-[10px] bg-emerald-600/12 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300 flex items-center justify-center shrink-0">
                <Icon size={15} />
              </div>
            </div>
          )
        })}
      </div>

      {/* In-Flight Summary Chips */}
      {hasInFlight && (
        <div className="flex items-center gap-2 flex-wrap pt-1">
          {data.draft_letters_count > 0 && (
            <span className="rounded-[10px] border border-border px-2.5 py-1 text-xs font-semibold text-foreground">
              {data.draft_letters_count} Draft{data.draft_letters_count === 1 ? "" : "s"}
            </span>
          )}
          {data.published_letters_count > 0 && (
            <span className="rounded-[10px] border border-[#653F84]/30 bg-[#653F84]/10 px-2.5 py-1 text-xs font-semibold text-[#653F84] dark:text-purple-200">
              {data.published_letters_count} Published
            </span>
          )}
          {data.signed_letters_count > 0 && (
            <span className="rounded-[10px] bg-[#653F84] px-2.5 py-1 text-xs font-semibold text-white">
              {data.signed_letters_count} Signed
            </span>
          )}
          <span className="text-xs font-bold text-muted-foreground tabular-nums ml-auto">
            In-flight AED {data.pending_payout_aed.toLocaleString()}
          </span>
        </div>
      )}

      {/* Monthly Paid Bar Chart */}
      {data.monthly_paid.length > 0 && (
        <div className="rounded-[10px] border border-border bg-background p-4 space-y-2">
          <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
            Monthly Paid Payouts (AED)
          </p>
          <div className="h-[150px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={data.monthly_paid}
                margin={{ top: 6, right: 6, left: 0, bottom: 0 }}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="currentColor"
                  className="opacity-15"
                  vertical={false}
                />
                <XAxis
                  dataKey="month_label"
                  tick={{ fontSize: 11, fill: "currentColor" }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fontSize: 11, fill: "currentColor" }}
                  axisLine={false}
                  tickLine={false}
                  width={44}
                />
                <Tooltip
                  cursor={{ fill: "rgba(101, 63, 132, 0.08)" }}
                  contentStyle={{
                    borderRadius: "10px",
                    border: "1px solid hsl(var(--border))",
                    backgroundColor: "hsl(var(--popover))",
                    color: "hsl(var(--popover-foreground))",
                    fontSize: "12px",
                  }}
                  formatter={(val) => [`AED ${Number(val ?? 0).toLocaleString()}`, "Paid"]}
                />
                <Bar dataKey="amount_aed" fill="#653F84" radius={[6, 6, 0, 0]} maxBarSize={42} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Payment Letters History List */}
      <div className="space-y-2.5">
        <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
          Payment Letters ({data.letters.length})
        </p>

        {data.letters.length === 0 ? (
          <div className="rounded-[10px] border border-dashed border-border p-5 text-center text-xs font-medium text-muted-foreground">
            No payment letters recorded
          </div>
        ) : (
          <div className="space-y-2.5">
            {data.letters.map((l) => {
              const total = letterTotal(l)
              const pdfHref = l.signed_pdf_url ?? l.pdf_url
              const paidStr = l.paid_at
                ? new Date(l.paid_at).toLocaleDateString()
                : l.letter_date

              return (
                <div
                  key={l.id}
                  className="rounded-[10px] border border-border bg-background p-3.5 space-y-2.5"
                >
                  <div className="flex items-start justify-between gap-2 flex-wrap">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-xs font-mono font-bold text-foreground">
                          {l.reference}
                        </span>
                        <span
                          className={cn(
                            "inline-flex items-center rounded-[10px] px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide",
                            STATUS_BADGE[l.status],
                          )}
                        >
                          {l.status}
                        </span>
                        {l.batch_name && (
                          <span className="inline-flex items-center rounded-[10px] border border-border px-2 py-0.5 text-[11px] font-semibold text-foreground">
                            {l.batch_name}
                          </span>
                        )}
                      </div>

                      {paidStr && (
                        <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                          <Calendar size={11} />
                          <span>{l.status === "paid" ? `Paid ${paidStr}` : paidStr}</span>
                        </div>
                      )}
                    </div>

                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-extrabold text-foreground tabular-nums">
                        AED {total.toLocaleString()}
                      </span>
                      {pdfHref && (
                        <a href={pdfHref} target="_blank" rel="noreferrer">
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-7 px-2.5 rounded-[10px] border-border text-xs font-semibold"
                          >
                            <Download size={12} className="mr-1" /> PDF
                          </Button>
                        </a>
                      )}
                      {onOpenLetter && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => onOpenLetter(l.id)}
                          className="h-7 px-2.5 rounded-[10px] border-border text-xs font-semibold"
                        >
                          <ExternalLink size={12} className="mr-1" /> Open
                        </Button>
                      )}
                    </div>
                  </div>

                  {l.sessions.length > 0 && (
                    <div className="flex items-center gap-1.5 flex-wrap">
                      {l.sessions.map((s) => (
                        <span
                          key={s.id}
                          className="rounded-[10px] border border-border px-2 py-0.5 text-[11px] font-medium text-foreground"
                        >
                          {s.workshop_description} ({s.role})
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

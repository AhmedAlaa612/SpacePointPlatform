import { CheckCircle2 } from "lucide-react"

export interface FunnelStage {
  label: string
  value: number | string
  /** Numeric weight used to draw the funnel step height. */
  weight: number
}

export interface FunnelSideCard {
  title: string
  badge?: string
  subtitle?: string
  value: string | number
  ok?: boolean
}

interface AnalysisFunnelWidgetProps {
  stages: [FunnelStage, FunnelStage, FunnelStage]
  sideCards: [FunnelSideCard, FunnelSideCard, FunnelSideCard]
  footerText?: string
}

/**
 * 3-stage stepped funnel + 3 stacked KPI cards (Preply-inspired layout),
 * styled with the global SpacePoint theme tokens.
 */
export function AnalysisFunnelWidget({
  stages,
  sideCards,
  footerText,
}: AnalysisFunnelWidgetProps) {
  const maxW = Math.max(stages[0].weight, 1)
  // Normalize heights into [0..100] SVG viewBox (y=0 top, y=100 bottom),
  // keeping a smooth downward funnel silhouette.
  const r0 = Math.max(0.18, Math.min(1, stages[0].weight / maxW))
  const r1 = Math.max(0.1, Math.min(r0, stages[1].weight / maxW))
  const r2 = Math.max(0.05, Math.min(r1, stages[2].weight / maxW))
  const rEnd = Math.max(0.02, r2 * 0.55)

  const y0 = 100 - r0 * 82
  const y1 = 100 - r1 * 82
  const y2 = 100 - r2 * 82
  const y3 = 100 - rEnd * 82

  return (
    <div className="flex flex-col gap-2">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 items-stretch">
        {/* Left 2/3: 3-stage stepped funnel */}
        <div className="lg:col-span-2 bg-card rounded-[10px] flex flex-col justify-between overflow-hidden min-h-[260px]">
          <div className="grid grid-cols-3 flex-1">
            {stages.map((stage, idx) => (
              <div
                key={stage.label}
                className={`p-4 sm:p-5 flex flex-col justify-start ${
                  idx < 2 ? "border-r border-dashed border-border/50" : ""
                }`}
              >
                <span className="text-xs font-medium text-muted-foreground truncate">
                  {stage.label}
                </span>
                <span className="text-2xl sm:text-3xl font-bold text-foreground tabular-nums mt-1">
                  {stage.value}
                </span>
              </div>
            ))}
          </div>

          <div className="relative w-full h-28 sm:h-32">
            <svg
              viewBox="0 0 300 100"
              preserveAspectRatio="none"
              className="w-full h-full block"
              aria-hidden="true"
            >
              {/* Stage 1 */}
              <polygon
                points={`0,${y0} 100,${y1} 100,100 0,100`}
                fill="#A77DFF"
              />
              {/* Stage 2 */}
              <polygon
                points={`100,${y1} 200,${y2} 200,100 100,100`}
                fill="#653F84"
              />
              {/* Stage 3 */}
              <polygon
                points={`200,${y2} 300,${y3} 300,100 200,100`}
                fill="#3B1D54"
              />
              {/* Top slope highlight */}
              <polyline
                points={`0,${y0} 100,${y1} 200,${y2} 300,${y3}`}
                fill="none"
                stroke="#D7D2CB"
                strokeOpacity="0.45"
                strokeWidth="2"
              />
              {/* Dashed column dividers inside funnel */}
              <line
                x1="100"
                y1="0"
                x2="100"
                y2="100"
                stroke="currentColor"
                strokeOpacity="0.18"
                strokeDasharray="3 3"
                strokeWidth="1"
              />
              <line
                x1="200"
                y1="0"
                x2="200"
                y2="100"
                stroke="currentColor"
                strokeOpacity="0.18"
                strokeDasharray="3 3"
                strokeWidth="1"
              />
            </svg>
          </div>
        </div>

        {/* Right 1/3: 3 stacked metric cards */}
        <div className="flex flex-col gap-3 justify-between">
          {sideCards.map((card) => (
            <div
              key={card.title}
              className="bg-card rounded-[10px] p-4 flex-1 flex flex-col justify-between gap-2"
            >
              <div>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium text-foreground">
                    {card.title}
                  </span>
                  {card.badge && (
                    <span className="px-2 py-0.5 rounded-full bg-primary text-white text-[10px] font-semibold">
                      {card.badge}
                    </span>
                  )}
                </div>
                {card.subtitle && (
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {card.subtitle}
                  </p>
                )}
              </div>

              <div className="flex items-center justify-between gap-2">
                <span className="text-2xl font-bold text-foreground tabular-nums">
                  {card.value}
                </span>
                {card.ok && (
                  <CheckCircle2 size={18} className="text-emerald-500 shrink-0" />
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {footerText && (
        <p className="text-[11px] text-muted-foreground text-right">
          {footerText}
        </p>
      )}
    </div>
  )
}

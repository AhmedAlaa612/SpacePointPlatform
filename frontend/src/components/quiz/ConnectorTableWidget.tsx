import type { PinoutTableConfig } from "@/api/sessions/pre_session_quiz"
import { cn } from "@/lib/utils"

interface ConnectorTableWidgetProps {
  config: PinoutTableConfig
  mode: "interactive" | "builder" | "review" | "reference"
  /** For `interactive` and `review` modes: per-row list of selected column indices */
  selectedCells?: number[][]
  onToggleCell?: (rowIdx: number, colIdx: number) => void
  /** For `builder` mode */
  onChangeConfig?: (updated: PinoutTableConfig) => void
  disabled?: boolean
}

const ROW_PRESETS: { label: string; cells: [string, string, string] }[] = [
  { label: "3V3 / Main / GND", cells: ["3V3", "Main", "GND"] },
  { label: "I2C1 (SCL / Main / SDA)", cells: ["I2C1_SCL", "Main", "I2C1_SDA"] },
  { label: "SPI (MISO / Main / MOSI)", cells: ["SPI_MISO", "Main", "SPI_MOSI"] },
  { label: "SPI (CLK / Main / CS)", cells: ["SPI_CLK", "Main", "SPI_CS"] },
  { label: "UART1 (RX / Main / TX)", cells: ["UART1_RX", "Main", "UART1_TX"] },
]

export function ConnectorTableWidget({
  config,
  mode,
  selectedCells = [],
  onToggleCell,
  onChangeConfig,
  disabled = false,
}: ConnectorTableWidgetProps) {
  const columns = config.columns?.length ? config.columns : ["1", "2", "3"]
  const rows = config.rows ?? []

  // Builder helpers
  const updateHeader = (patch: Partial<PinoutTableConfig>) => {
    if (!onChangeConfig) return
    onChangeConfig({ ...config, ...patch })
  }

  const updateRowLabel = (rIdx: number, label: string) => {
    if (!onChangeConfig) return
    const nextRows = rows.map((r, i) => (i === rIdx ? { ...r, label } : r))
    onChangeConfig({ ...config, rows: nextRows })
  }

  const updateCell = (rIdx: number, cIdx: number, patch: { text?: string; is_correct?: boolean }) => {
    if (!onChangeConfig) return
    const nextRows = rows.map((r, i) => {
      if (i !== rIdx) return r
      const nextCells = r.cells.map((c, j) => (j === cIdx ? { ...c, ...patch } : c))
      return { ...r, cells: nextCells }
    })
    onChangeConfig({ ...config, rows: nextRows })
  }

  const addRow = (presetCells?: [string, string, string]) => {
    if (!onChangeConfig) return
    const nextPinNum = rows.length + 1
    const newCells = columns.map((_, idx) => ({
      text: presetCells ? (presetCells[idx] ?? "") : idx === 1 ? "Main" : "",
      is_correct: false,
    }))
    onChangeConfig({
      ...config,
      rows: [...rows, { label: `Pin ${nextPinNum}`, cells: newCells }],
    })
  }

  const removeRow = (rIdx: number) => {
    if (!onChangeConfig || rows.length <= 1) return
    onChangeConfig({
      ...config,
      rows: rows.filter((_, i) => i !== rIdx),
    })
  }

  return (
    <div className="flex flex-col gap-2.5 w-full">
      <div className="overflow-x-auto rounded-xl border-2 border-purple-900/40 dark:border-purple-500/30 shadow-sm bg-card">
        <table className="w-full border-collapse text-xs sm:text-sm">
          <thead>
            {/* Top Header Row: Connector Name (rowSpan=2) | Subtitle (colSpan=N) */}
            <tr>
              <th
                rowSpan={2}
                className="w-28 sm:w-36 border border-purple-900/30 dark:border-purple-500/30 bg-card p-2 text-center font-bold text-foreground align-middle"
              >
                {mode === "builder" ? (
                  <input
                    value={config.connector_name}
                    onChange={(e) => updateHeader({ connector_name: e.target.value })}
                    placeholder="J6"
                    className="w-full text-center font-bold bg-muted/50 border border-border rounded px-1.5 py-1 text-xs sm:text-sm focus:outline-none focus:border-primary"
                  />
                ) : (
                  <span className="text-sm sm:text-base font-extrabold tracking-tight">
                    {config.connector_name || "Connector"}
                  </span>
                )}
              </th>
              <th
                colSpan={columns.length}
                className="border border-purple-900/30 dark:border-purple-500/30 bg-card px-3 py-1.5 text-center font-bold text-foreground"
              >
                {mode === "builder" ? (
                  <input
                    value={config.header_subtitle}
                    onChange={(e) => updateHeader({ header_subtitle: e.target.value })}
                    placeholder="e.g. J61, J62, J63, J64, J65, J66"
                    className="w-full text-center font-semibold bg-muted/50 border border-border rounded px-2 py-1 text-xs focus:outline-none focus:border-primary"
                  />
                ) : (
                  <span>{config.header_subtitle || config.connector_name}</span>
                )}
              </th>
              {mode === "builder" && <th rowSpan={2} className="w-16 bg-muted/30 border border-purple-900/30" />}
            </tr>

            {/* Sub-header Row: Column Numbers (1 | 2 | 3) */}
            <tr className="bg-[#5b2d82] text-white">
              {columns.map((col, cIdx) => (
                <th
                  key={cIdx}
                  className="border border-purple-900/40 px-3 py-1 text-center font-bold tracking-wider"
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {rows.map((row, rIdx) => {
              const rowSelected = selectedCells[rIdx] ?? []
              return (
                <tr key={rIdx} className="group">
                  {/* Left Pin Label Cell */}
                  <td className="bg-[#5b2d82] text-white font-bold text-center px-2.5 py-2 border border-purple-900/40 whitespace-nowrap">
                    {mode === "builder" ? (
                      <input
                        value={row.label}
                        onChange={(e) => updateRowLabel(rIdx, e.target.value)}
                        className="w-20 text-center font-bold bg-white/15 text-white placeholder-white/60 rounded px-1.5 py-0.5 text-xs focus:outline-none focus:ring-1 focus:ring-white"
                      />
                    ) : (
                      row.label
                    )}
                  </td>

                  {/* Pinout Option Cells */}
                  {columns.map((_, cIdx) => {
                    const cell = row.cells[cIdx] ?? { text: "", is_correct: false }
                    const isSelected = rowSelected.includes(cIdx)
                    const isCorrect = Boolean(cell.is_correct)

                    if (mode === "builder") {
                      return (
                        <td
                          key={cIdx}
                          className={cn(
                            "border border-purple-900/35 dark:border-purple-400/35 p-1.5 transition-colors",
                            isCorrect
                              ? "bg-[#8e7cc3] dark:bg-[#6b3fa0] ring-2 ring-inset ring-[#5b2d82] dark:ring-purple-300"
                              : "bg-card"
                          )}
                        >
                          <div className="flex items-center gap-1">
                            <input
                              value={cell.text}
                              onChange={(e) => updateCell(rIdx, cIdx, { text: e.target.value })}
                              placeholder="Pin label"
                              className={cn(
                                "w-full min-w-[70px] text-center font-bold border rounded px-1.5 py-1 text-xs focus:outline-none focus:border-primary",
                                isCorrect
                                  ? "bg-white/90 text-slate-950 border-[#5b2d82]"
                                  : "bg-background text-foreground border-border"
                              )}
                            />
                            <button
                              type="button"
                              onClick={() => updateCell(rIdx, cIdx, { is_correct: !isCorrect })}
                              title={
                                isCorrect
                                  ? "Marked as correct jumper position (click to unmark)"
                                  : "Click to mark as correct jumper position"
                              }
                              className={cn(
                                "h-6 px-2 rounded-md flex items-center justify-center shrink-0 transition-all cursor-pointer border text-[10px] font-bold",
                                isCorrect
                                  ? "bg-[#5b2d82] text-white border-white shadow-sm"
                                  : "bg-muted text-muted-foreground border-border hover:text-foreground hover:border-purple-500"
                              )}
                            >
                              {isCorrect ? "On" : "Off"}
                            </button>
                          </div>
                        </td>
                      )
                    }

                    if (mode === "interactive") {
                      return (
                        <td
                          key={cIdx}
                          onClick={() => {
                            if (!disabled && onToggleCell) onToggleCell(rIdx, cIdx)
                          }}
                          className={cn(
                            "border border-purple-900/35 dark:border-purple-400/35 px-3 py-2.5 text-center font-bold select-none transition-all",
                            !disabled && "cursor-pointer",
                            isSelected
                              ? "bg-[#8e7cc3] dark:bg-[#7042a6] text-slate-950 dark:text-white ring-2 ring-inset ring-[#4a226b] dark:ring-purple-200 shadow-inner"
                              : "bg-card text-foreground hover:bg-[#8e7cc3]/25 dark:hover:bg-[#7042a6]/30"
                          )}
                        >
                          <span>{cell.text || "—"}</span>
                        </td>
                      )
                    }

                    if (mode === "reference") {
                      return (
                        <td
                          key={cIdx}
                          className={cn(
                            "border border-purple-900/35 dark:border-purple-400/35 px-3 py-2.5 text-center font-bold",
                            isCorrect
                              ? "bg-[#8e7cc3] dark:bg-[#7042a6] text-slate-950 dark:text-white ring-1 ring-inset ring-[#4a226b]/50"
                              : "bg-card text-foreground"
                          )}
                        >
                          <span>{cell.text || "—"}</span>
                        </td>
                      )
                    }

                    // mode === "review": compare instructor's `isSelected` with `isCorrect`
                    const hitCorrect = isSelected && isCorrect
                    const hitWrong = isSelected && !isCorrect
                    const missedCorrect = !isSelected && isCorrect

                    return (
                      <td
                        key={cIdx}
                        className={cn(
                          "border border-purple-900/35 dark:border-purple-400/35 px-3 py-2.5 text-center font-bold",
                          hitCorrect && "bg-emerald-600 dark:bg-emerald-600 text-white ring-2 ring-inset ring-emerald-800 dark:ring-emerald-300",
                          hitWrong && "bg-red-600 dark:bg-red-600 text-white ring-2 ring-inset ring-red-800 dark:ring-red-300",
                          missedCorrect && "bg-amber-400 dark:bg-amber-500 text-slate-950 ring-2 ring-inset ring-amber-700 dark:ring-amber-200",
                          !hitCorrect && !hitWrong && !missedCorrect && "bg-card text-foreground"
                        )}
                      >
                        <div className="flex items-center justify-center gap-1.5">
                          <span>{cell.text || "—"}</span>
                          {missedCorrect && (
                            <span className="text-[10px] font-extrabold uppercase px-1.5 py-0.2 rounded bg-slate-950/80 text-amber-300">
                              Expected
                            </span>
                          )}
                        </div>
                      </td>
                    )
                  })}

                  {/* Builder Delete Row Button */}
                  {mode === "builder" && (
                    <td className="border border-purple-900/25 p-1 text-center bg-muted/20">
                      <button
                        type="button"
                        onClick={() => removeRow(rIdx)}
                        disabled={rows.length <= 1}
                        className="px-2 py-1 text-[11px] font-medium text-muted-foreground hover:text-red-500 disabled:opacity-30 cursor-pointer"
                        title="Remove pin row"
                      >
                        Remove
                      </button>
                    </td>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Builder Toolbar for quick row insertion */}
      {mode === "builder" && (
        <div className="flex items-center gap-1.5 flex-wrap">
          <button
            type="button"
            onClick={() => addRow()}
            className="inline-flex items-center px-2.5 py-1 rounded-lg text-xs font-semibold bg-primary/10 text-primary hover:bg-primary/15 border border-primary/20 cursor-pointer transition-colors"
          >
            + Add Pin Row
          </button>
          <span className="text-[11px] text-muted-foreground ml-1">Quick add:</span>
          {ROW_PRESETS.map((preset) => (
            <button
              key={preset.label}
              type="button"
              onClick={() => addRow(preset.cells)}
              className="inline-flex items-center px-2 py-1 rounded-md text-[11px] font-medium bg-muted hover:bg-muted/80 text-foreground border border-border cursor-pointer transition-colors"
            >
              + {preset.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

import { jsPDF } from "jspdf"
import type { DashboardStats } from "@/types/ambassadors"
import type { TeacherSummary } from "@/api/ambassadors/teacher"
import logoUrl from "@/assets/logos/ambassador.svg"

const HELIO: [number, number, number] = [168, 128, 255]
const INK: [number, number, number] = [17, 17, 17]
const MUTED: [number, number, number] = [120, 120, 120]

/** Rasterise the SVG logo to a PNG data URL so jsPDF can embed it. */
async function loadLogo(targetH = 200): Promise<{ dataUrl: string; ratio: number } | null> {
  return new Promise((resolve) => {
    const img = new Image()
    img.crossOrigin = "anonymous"
    img.onload = () => {
      const ratio = img.naturalWidth && img.naturalHeight ? img.naturalWidth / img.naturalHeight : 4
      const h = targetH
      const w = Math.round(h * ratio)
      const canvas = document.createElement("canvas")
      canvas.width = w
      canvas.height = h
      const ctx = canvas.getContext("2d")
      if (!ctx) return resolve(null)
      ctx.drawImage(img, 0, 0, w, h)
      try {
        resolve({ dataUrl: canvas.toDataURL("image/png"), ratio })
      } catch {
        resolve(null)
      }
    }
    img.onerror = () => resolve(null)
    img.src = logoUrl
  })
}

/** Branded one-page ambassador impact report. */
export async function generateImpactReport(name: string, stats: DashboardStats) {
  const doc = new jsPDF({ unit: "mm", format: "a4" })
  const w = doc.internal.pageSize.getWidth()
  const M = 18 // page margin

  // ── Header ──
  const logo = await loadLogo()
  const logoH = 13
  if (logo) {
    doc.addImage(logo.dataUrl, "PNG", M, 16, logoH * logo.ratio, logoH)
  } else {
    doc.setTextColor(...INK)
    doc.setFont("helvetica", "bold")
    doc.setFontSize(20)
    doc.text("SpacePoint", M, 26)
  }
  doc.setTextColor(...MUTED)
  doc.setFont("helvetica", "normal")
  doc.setFontSize(10)
  doc.text("AMBASSADOR IMPACT REPORT", w - M, 24, { align: "right" })
  doc.text(new Date().toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" }), w - M, 30, { align: "right" })

  // divider rule
  doc.setDrawColor(...INK)
  doc.setLineWidth(0.8)
  doc.line(M, 38, w - M, 38)

  // ── Identity ──
  doc.setTextColor(...INK)
  doc.setFont("helvetica", "bold")
  doc.setFontSize(22)
  doc.text(name, M, 54)

  if (stats.current_title) {
    doc.setFont("helvetica", "bold")
    doc.setFontSize(10)
    const label = stats.current_title.name.toUpperCase()
    const tw = doc.getTextWidth(label) + 8
    doc.setFillColor(...HELIO)
    doc.roundedRect(M, 58, tw, 7, 3.5, 3.5, "F")
    doc.setTextColor(255, 255, 255)
    doc.text(label, M + 4, 62.8)
  }

  doc.setFont("helvetica", "normal")
  doc.setFontSize(11)
  doc.setTextColor(...MUTED)
  doc.text(
    `${stats.points_balance.toLocaleString()} lifetime points` +
      (stats.my_rank ? `   ·   Global rank #${stats.my_rank}` : ""),
    M,
    74,
  )

  // ── Metric cards (3 × 2 grid) ──
  const metrics: [string, number][] = [
    ["Students reached", stats.students_reached],
    ["Sessions delivered", stats.sessions_done],
    ["Active teachers", stats.active_teachers],
    ["Active instructors", stats.active_instructors],
    ["Leads converted", stats.converted_leads],
    ["Tasks completed", stats.completed_tasks],
  ]
  const cols = 3
  const gap = 6
  const cardW = (w - M * 2 - gap * (cols - 1)) / cols
  const cardH = 26
  const top = 84
  metrics.forEach(([label, value], i) => {
    const cx = M + (i % cols) * (cardW + gap)
    const cy = top + Math.floor(i / cols) * (cardH + gap)
    doc.setDrawColor(232, 232, 232)
    doc.setFillColor(250, 249, 252)
    doc.roundedRect(cx, cy, cardW, cardH, 3, 3, "FD")
    doc.setTextColor(...INK)
    doc.setFont("helvetica", "bold")
    doc.setFontSize(20)
    doc.text(value.toLocaleString(), cx + 6, cy + 13)
    doc.setFont("helvetica", "normal")
    doc.setFontSize(9)
    doc.setTextColor(...MUTED)
    doc.text(label.toUpperCase(), cx + 6, cy + 20)
  })

  let y = top + 2 * cardH + gap + 16

  // ── Badges ──
  const earned = stats.achievements.filter((a) => a.earned)
  if (earned.length) {
    doc.setTextColor(...INK)
    doc.setFont("helvetica", "bold")
    doc.setFontSize(12)
    doc.text(`Badges earned (${earned.length})`, M, y)
    y += 8
    doc.setFont("helvetica", "bold")
    doc.setFontSize(9)
    let x = M
    earned.forEach((b) => {
      const label = b.label
      const cw = doc.getTextWidth(label) + 8
      if (x + cw > w - M) {
        x = M
        y += 10
      }
      doc.setFillColor(244, 240, 252)
      doc.roundedRect(x, y - 5, cw, 7, 3.5, 3.5, "F")
      doc.setTextColor(101, 63, 132)
      doc.text(label, x + 4, y - 0.2)
      x += cw + 4
    })
  }

  // ── Footer ──
  const h = doc.internal.pageSize.getHeight()
  doc.setDrawColor(232, 232, 232)
  doc.setLineWidth(0.3)
  doc.line(M, h - 18, w - M, h - 18)
  doc.setTextColor(...MUTED)
  doc.setFont("helvetica", "normal")
  doc.setFontSize(8)
  doc.text("SpacePoint Global Ambassador Program", M, h - 12)
  doc.text("spacepoint.ae", w - M, h - 12, { align: "right" })

  doc.save(`${name.replace(/\s+/g, "_")}_Impact_Report.pdf`)
}

/** Branded one-page teacher impact report (reuses the ambassador layout). */
export async function generateTeacherImpactReport(name: string, summary: TeacherSummary) {
  const doc = new jsPDF({ unit: "mm", format: "a4" })
  const w = doc.internal.pageSize.getWidth()
  const M = 18

  const logo = await loadLogo()
  const logoH = 13
  if (logo) {
    doc.addImage(logo.dataUrl, "PNG", M, 16, logoH * logo.ratio, logoH)
  } else {
    doc.setTextColor(...INK)
    doc.setFont("helvetica", "bold")
    doc.setFontSize(20)
    doc.text("SpacePoint", M, 26)
  }
  doc.setTextColor(...MUTED)
  doc.setFont("helvetica", "normal")
  doc.setFontSize(10)
  doc.text("TEACHER IMPACT REPORT", w - M, 24, { align: "right" })
  doc.text(new Date().toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" }), w - M, 30, { align: "right" })

  doc.setDrawColor(...INK)
  doc.setLineWidth(0.8)
  doc.line(M, 38, w - M, 38)

  doc.setTextColor(...INK)
  doc.setFont("helvetica", "bold")
  doc.setFontSize(22)
  doc.text(name, M, 54)

  if (summary.current_title) {
    doc.setFont("helvetica", "bold")
    doc.setFontSize(10)
    const label = summary.current_title.name.toUpperCase()
    const tw = doc.getTextWidth(label) + 8
    doc.setFillColor(...HELIO)
    doc.roundedRect(M, 58, tw, 7, 3.5, 3.5, "F")
    doc.setTextColor(255, 255, 255)
    doc.text(label, M + 4, 62.8)
  }

  doc.setFont("helvetica", "normal")
  doc.setFontSize(11)
  doc.setTextColor(...MUTED)
  doc.text(`${summary.points_balance.toLocaleString()} lifetime points`, M, 74)

  const metrics: [string, number][] = [
    ["Students reached", summary.stats.students_reached],
    ["Sessions delivered", summary.stats.sessions_done],
    ["Upcoming sessions", summary.stats.upcoming],
  ]
  const cols = 3
  const gap = 6
  const cardW = (w - M * 2 - gap * (cols - 1)) / cols
  const cardH = 26
  const top = 84
  metrics.forEach(([label, value], i) => {
    const cx = M + (i % cols) * (cardW + gap)
    const cy = top + Math.floor(i / cols) * (cardH + gap)
    doc.setDrawColor(232, 232, 232)
    doc.setFillColor(250, 249, 252)
    doc.roundedRect(cx, cy, cardW, cardH, 3, 3, "FD")
    doc.setTextColor(...INK)
    doc.setFont("helvetica", "bold")
    doc.setFontSize(20)
    doc.text(value.toLocaleString(), cx + 6, cy + 13)
    doc.setFont("helvetica", "normal")
    doc.setFontSize(9)
    doc.setTextColor(...MUTED)
    doc.text(label.toUpperCase(), cx + 6, cy + 20)
  })

  let y = top + cardH + gap + 16

  const earned = (summary.achievements ?? []).filter((a) => a.earned)
  if (earned.length) {
    doc.setTextColor(...INK)
    doc.setFont("helvetica", "bold")
    doc.setFontSize(12)
    doc.text(`Badges earned (${earned.length})`, M, y)
    y += 8
    doc.setFont("helvetica", "bold")
    doc.setFontSize(9)
    let x = M
    earned.forEach((b) => {
      const cw = doc.getTextWidth(b.label) + 8
      if (x + cw > w - M) {
        x = M
        y += 10
      }
      doc.setFillColor(244, 240, 252)
      doc.roundedRect(x, y - 5, cw, 7, 3.5, 3.5, "F")
      doc.setTextColor(101, 63, 132)
      doc.text(b.label, x + 4, y - 0.2)
      x += cw + 4
    })
  }

  const h = doc.internal.pageSize.getHeight()
  doc.setDrawColor(232, 232, 232)
  doc.setLineWidth(0.3)
  doc.line(M, h - 18, w - M, h - 18)
  doc.setTextColor(...MUTED)
  doc.setFont("helvetica", "normal")
  doc.setFontSize(8)
  doc.text("SpacePoint Teacher Program", M, h - 12)
  doc.text("spacepoint.ae", w - M, h - 12, { align: "right" })

  doc.save(`${name.replace(/\s+/g, "_")}_Impact_Report.pdf`)
}

/** Ground Station telemetry report — ported from the legacy app's
 * `exportPdf.js`: a branded "Space Purple" cover, a chart screenshot
 * (html2canvas, same as the legacy report — a data-table alone can't show
 * a trend the way a rendered chart can), a per-metric min/max/avg/count
 * summary table, and the full readings table with page-break handling. */
interface GroundStationTelemetrySample {
  recorded_at: string
  temp?: number | null
  voltage?: number | null
  current?: number | null
  power?: number | null
  rssi?: number | null
  snr?: number | null
}

const GS_ACCENT: [number, number, number] = [155, 114, 192]
const GS_ACCENT_GLOW: [number, number, number] = [101, 63, 132]
const GS_BG_DARK: [number, number, number] = [13, 6, 24]
const GS_BG_MID: [number, number, number] = [36, 17, 52]
const GS_BG_CARD: [number, number, number] = [45, 24, 64]
const GS_WHITE: [number, number, number] = [255, 255, 255]

const GS_METRICS: { key: keyof GroundStationTelemetrySample; label: string; unit: string }[] = [
  { key: "temp", label: "Temperature", unit: "degC" },
  { key: "voltage", label: "Voltage", unit: "V" },
  { key: "current", label: "Current", unit: "mA" },
  { key: "power", label: "Power", unit: "mW" },
  { key: "rssi", label: "RSSI", unit: "dBm" },
]

function gsStats(rows: GroundStationTelemetrySample[]) {
  return GS_METRICS.map((m) => {
    const vals = rows.map((r) => r[m.key]).filter((v): v is number => v != null)
    if (!vals.length) return { ...m, min: "--", max: "--", avg: "--", count: 0 }
    const min = Math.min(...vals), max = Math.max(...vals)
    const avg = vals.reduce((a, b) => a + b, 0) / vals.length
    return { ...m, min: min.toFixed(2), max: max.toFixed(2), avg: avg.toFixed(2), count: vals.length }
  })
}

export async function buildGroundStationReport(
  deviceLabel: string,
  history: GroundStationTelemetrySample[],
  photoCount: number,
  chartElement?: HTMLElement | null,
) {
  const html2canvas = (await import("html2canvas")).default

  let chartImgData: string | null = null
  if (chartElement) {
    const snap = await html2canvas(chartElement, { backgroundColor: "#0d0618", scale: 2, useCORS: true, logging: false })
    chartImgData = snap.toDataURL("image/png")
  }

  const doc = new jsPDF({ orientation: "portrait", unit: "mm", format: "a4" })
  const PW = doc.internal.pageSize.getWidth()
  const PH = doc.internal.pageSize.getHeight()
  let y = 0

  const fill = (c: [number, number, number]) => doc.setFillColor(...c)
  const draw = (c: [number, number, number]) => doc.setDrawColor(...c)
  const color = (c: [number, number, number]) => doc.setTextColor(...c)

  fill(GS_BG_DARK)
  doc.rect(0, 0, PW, PH, "F")

  fill(GS_BG_MID)
  doc.rect(0, 0, PW, 32, "F")
  draw(GS_ACCENT_GLOW)
  doc.setLineWidth(0.8)
  doc.line(0, 32, PW, 32)

  doc.setFont("helvetica", "bold")
  doc.setFontSize(18)
  color(GS_WHITE)
  doc.text("Cube-Sat Ground Station", 14, 14)
  doc.setFont("helvetica", "normal")
  doc.setFontSize(10)
  color(GS_ACCENT)
  doc.text("TELEMETRY MISSION REPORT", 14, 21)

  doc.setFontSize(8)
  color(GS_WHITE)
  doc.text(`Generated: ${new Date().toLocaleString()}`, PW - 14, 12, { align: "right" })
  color(GS_ACCENT)
  doc.text(`Rig: ${deviceLabel}`, PW - 14, 20, { align: "right" })

  y = 42

  const pills: [string, string][] = [
    ["Samples", String(history.length)],
    ["Photos archived", String(photoCount)],
    ["Range", history.length ? `${new Date(history[0].recorded_at).toLocaleString()} → ${new Date(history[history.length - 1].recorded_at).toLocaleString()}` : "--"],
  ]
  const pillW = (PW - 28 - 6) / 3
  pills.forEach(([label, value], i) => {
    const px = 14 + i * (pillW + 3)
    fill(GS_BG_CARD); draw(GS_ACCENT_GLOW); doc.setLineWidth(0.3)
    doc.roundedRect(px, y, pillW, 12, 2, 2, "FD")
    doc.setFont("helvetica", "bold"); doc.setFontSize(6.5); color(GS_ACCENT)
    doc.text(label.toUpperCase(), px + 3, y + 4.5)
    doc.setFont("helvetica", "normal"); doc.setFontSize(7.5); color(GS_WHITE)
    doc.text(value.length > 40 ? value.slice(0, 39) + "…" : value, px + 3, y + 9.5)
  })
  y += 18

  if (chartImgData) {
    doc.setFont("helvetica", "bold"); doc.setFontSize(10); color(GS_ACCENT)
    doc.text("[ Chart ]", 14, y + 4)
    y += 8
    const chartH = 60
    fill(GS_BG_CARD)
    doc.rect(14, y, PW - 28, chartH, "F")
    doc.addImage(chartImgData, "PNG", 14, y, PW - 28, chartH)
    draw(GS_ACCENT_GLOW); doc.setLineWidth(0.3)
    doc.rect(14, y, PW - 28, chartH)
    y += chartH + 8
  }

  doc.setFont("helvetica", "bold"); doc.setFontSize(10); color(GS_ACCENT)
  doc.text("[ Metric Summary ]", 14, y + 4)
  y += 9

  const stats = gsStats(history)
  const statsColW = [(PW - 28) * 0.28, (PW - 28) * 0.18, (PW - 28) * 0.18, (PW - 28) * 0.18, (PW - 28) * 0.18]
  const statsHeaders = ["Metric", "Min", "Max", "Avg", "Readings"]
  fill([45, 30, 80])
  doc.rect(14, y, PW - 28, 7, "F")
  doc.setFont("helvetica", "bold"); doc.setFontSize(7.5); color(GS_WHITE)
  let cx = 14
  statsHeaders.forEach((h, i) => { doc.text(h, cx + 2, y + 5); cx += statsColW[i] })
  y += 7

  stats.forEach((s, si) => {
    fill(si % 2 === 0 ? GS_BG_CARD : GS_BG_MID)
    doc.rect(14, y, PW - 28, 7, "F")
    doc.setFont("helvetica", "normal"); doc.setFontSize(7.5); color(GS_WHITE)
    const cells = [`${s.label} (${s.unit})`, s.min, s.max, s.avg, String(s.count)]
    cx = 14
    cells.forEach((c, i) => { doc.text(c, cx + 2, y + 5); cx += statsColW[i] })
    y += 7
  })
  y += 8

  if (history.length > 0) {
    doc.setFont("helvetica", "bold"); doc.setFontSize(10); color(GS_ACCENT)
    doc.text("[ Data Table ]", 14, y + 4)
    y += 9

    const colW = [(PW - 28) * 0.28, (PW - 28) * 0.14, (PW - 28) * 0.14, (PW - 28) * 0.16, (PW - 28) * 0.14, (PW - 28) * 0.14]
    const headers = ["Time", "Temp", "Voltage", "Current", "Power", "RSSI"]
    fill([45, 30, 80])
    doc.rect(14, y, PW - 28, 6, "F")
    doc.setFont("helvetica", "bold"); doc.setFontSize(6.5); color(GS_WHITE)
    cx = 14
    headers.forEach((h, i) => { doc.text(h, cx + 1.5, y + 4.2); cx += colW[i] })
    y += 6

    doc.setFont("helvetica", "normal"); doc.setFontSize(6); color(GS_WHITE)
    history.forEach((row, ri) => {
      if (y + 6 > PH - 12) {
        doc.addPage()
        fill(GS_BG_DARK)
        doc.rect(0, 0, PW, PH, "F")
        y = 14
      }
      fill(ri % 2 === 0 ? GS_BG_CARD : GS_BG_MID)
      doc.rect(14, y, PW - 28, 6, "F")
      const cells = [
        new Date(row.recorded_at).toLocaleTimeString(),
        row.temp?.toFixed(1) ?? "--", row.voltage?.toFixed(2) ?? "--",
        row.current?.toFixed(1) ?? "--", row.power?.toFixed(1) ?? "--", row.rssi?.toFixed(0) ?? "--",
      ]
      cx = 14
      cells.forEach((c, i) => { doc.text(c, cx + 1.5, y + 4); cx += colW[i] })
      y += 6
    })
  }

  const totalPages = doc.internal.pages.length - 1
  for (let p = 1; p <= totalPages; p++) {
    doc.setPage(p)
    fill(GS_BG_MID)
    doc.rect(0, PH - 10, PW, 10, "F")
    draw(GS_ACCENT_GLOW); doc.setLineWidth(0.3)
    doc.line(0, PH - 10, PW, PH - 10)
    doc.setFont("helvetica", "normal"); doc.setFontSize(7); color(GS_ACCENT)
    doc.text("Cube-Sat Ground Station — Telemetry Export", 14, PH - 4)
    doc.text(`Page ${p} of ${totalPages}`, PW - 14, PH - 4, { align: "right" })
  }

  doc.save(`GroundStation_${deviceLabel.replace(/\s+/g, "_")}_Report.pdf`)
}

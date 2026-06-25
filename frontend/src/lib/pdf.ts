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

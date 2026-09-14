import { useEffect, useRef, useState } from "react"
import { apiBaseUrl, tokens } from "@/api/client"

/** Ground Station live WS client — connects to `/ws/ground-station/{deviceId}`,
 * JWT over the query string (a browser WebSocket() can't send an
 * Authorization header), same pattern as `useGameRunSocket`. Telemetry here
 * is genuinely externally-pushed (real hardware, not a computed simulation),
 * so unlike the Operate mission's 2s poll loop this is WS-driven. */

export type GroundStationMessage =
  | { type: "telemetry_frame"; payload: { data: Record<string, unknown>; recorded_at: string } }
  | { type: "command_queued"; payload: { id: string; name: string; arg: string | null; sent_by: string; queued_at: string } }
  | { type: "command_ack"; payload: { command_id: string; ok?: boolean; detail?: string; [k: string]: unknown } }
  | { type: "device_status"; payload: { status: "online" | "offline" } }
  | { type: "photo_added"; payload: { path: string; url: string; captured_at: string; lat?: number | null; lon?: number | null; alt?: number | null } }
  | { type: "alert"; payload: { id: string; alert_type: string; threshold: number; current_value: number; severity: string; occurred_at: string; message: string } }

const BASE_DELAY_MS = 1000
const MAX_DELAY_MS = 30000

export function useGroundStationSocket(deviceId: string | null, onMessage: (msg: GroundStationMessage) => void) {
  const [connected, setConnected] = useState(false)
  const onMessageRef = useRef(onMessage)
  onMessageRef.current = onMessage

  useEffect(() => {
    if (!deviceId) return

    let cancelled = false
    let ws: WebSocket | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let attempt = 0

    const connect = () => {
      const token = tokens.access
      if (!token) return

      const wsUrl = `${apiBaseUrl.replace(/^http/, "ws")}/ws/ground-station/${deviceId}?token=${encodeURIComponent(token)}`
      const socket = new WebSocket(wsUrl)
      ws = socket

      socket.onopen = () => {
        if (cancelled) return
        attempt = 0
        setConnected(true)
      }
      socket.onclose = () => {
        if (cancelled) return
        setConnected(false)
        const delay = Math.min(BASE_DELAY_MS * 2 ** attempt, MAX_DELAY_MS) * (0.75 + Math.random() * 0.5)
        attempt += 1
        reconnectTimer = setTimeout(connect, delay)
      }
      socket.onmessage = (ev) => {
        try {
          onMessageRef.current(JSON.parse(ev.data))
        } catch {
          // malformed frame — ignore rather than crash the console
        }
      }
    }

    connect()

    return () => {
      cancelled = true
      if (reconnectTimer) clearTimeout(reconnectTimer)
      ws?.close()
    }
  }, [deviceId])

  return { connected }
}

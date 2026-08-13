import { useEffect, useRef, useState } from "react"
import { apiBaseUrl, tokens } from "@/api/client"
import type { LeaderboardEntry, PublicQuestion, QuestionResult } from "@/api/games_live"

/** Live game WS client (Live Games Phase 2C, 8-5 transport / 8-7 first
 * consumer; world-class rework adds reconnect resilience) — connects to
 * `/ws/games/runs/{runId}`, JWT over the query string (a browser
 * WebSocket() can't send an Authorization header). Reconnects on `runId`
 * change (the caller's own `onMessage` handling `game_restarted` by
 * updating its `runId` state is what actually moves a client onto the new
 * run's channel) AND on any unexpected drop, with exponential backoff.
 *
 * Redis pub/sub has no replay/backfill — a message published while
 * disconnected is lost forever, not queued. Callers MUST treat the
 * returned `connected` boolean's false→true transition as "re-sync now"
 * (invalidate whatever queries the run depends on), not just "green dot is
 * back" — reconnecting alone doesn't recover anything that was missed. */

export type GameMessage =
  | { type: "question_started"; payload: PublicQuestion & { started_at: string } }
  | { type: "leaderboard_update"; payload: { blackout: boolean; question_id?: string; results?: QuestionResult[]; leaderboard?: LeaderboardEntry[] } }
  | { type: "question_added"; payload: unknown }
  | { type: "question_deleted"; payload: unknown }
  | { type: "game_restarted"; payload: { new_run_id: string } }
  | { type: "game_ended"; payload: Record<string, never> }
  | { type: "answer_ack"; payload: unknown }
  | { type: "participant_joined"; payload: { participant_id: string; nickname: string; avatar: string | null; joined_at: string | null } }
  | { type: "participant_updated"; payload: { participant_id: string; nickname: string; avatar: string | null } }
  | { type: "participant_answered"; payload: { participant_id: string } }

const BASE_DELAY_MS = 1000
const MAX_DELAY_MS = 30000

export function useGameRunSocket(runId: string | null, onMessage: (msg: GameMessage) => void) {
  const [connected, setConnected] = useState(false)
  const onMessageRef = useRef(onMessage)
  onMessageRef.current = onMessage

  useEffect(() => {
    if (!runId) return

    let cancelled = false
    let ws: WebSocket | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let attempt = 0

    const connect = () => {
      const token = tokens.access
      if (!token) return

      const wsUrl = `${apiBaseUrl.replace(/^http/, "ws")}/ws/games/runs/${runId}?token=${encodeURIComponent(token)}`
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
        // Jittered exponential backoff — retries indefinitely while
        // mounted, since a live class session can run 30-60+ min and a
        // transient wifi/network blip shouldn't need a manual page reload.
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
  }, [runId])

  return { connected }
}

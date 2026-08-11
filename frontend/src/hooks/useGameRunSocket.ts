import { useEffect, useRef, useState } from "react"
import { apiBaseUrl, tokens } from "@/api/client"
import type { LeaderboardEntry, PublicQuestion } from "@/api/games_live"

/** Live game WS client (Live Games Phase 2C, 8-5 transport / 8-7 first
 * consumer) — connects to `/ws/games/runs/{runId}`, JWT over the query
 * string (a browser WebSocket() can't send an Authorization header).
 * Reconnects automatically whenever `runId` changes — the caller's own
 * `onMessage` handling `game_restarted` by updating its `runId` state is
 * what actually moves a client onto the new run's channel; this hook
 * just reacts to that change. */

export type GameMessage =
  | { type: "question_started"; payload: PublicQuestion }
  | { type: "leaderboard_update"; payload: { blackout: boolean; leaderboard?: LeaderboardEntry[] } }
  | { type: "question_added"; payload: unknown }
  | { type: "question_deleted"; payload: unknown }
  | { type: "game_restarted"; payload: { new_run_id: string } }
  | { type: "game_ended"; payload: Record<string, never> }
  | { type: "answer_ack"; payload: unknown }

export function useGameRunSocket(runId: string | null, onMessage: (msg: GameMessage) => void) {
  const [connected, setConnected] = useState(false)
  const onMessageRef = useRef(onMessage)
  onMessageRef.current = onMessage

  useEffect(() => {
    if (!runId) return
    const token = tokens.access
    if (!token) return

    const wsUrl = `${apiBaseUrl.replace(/^http/, "ws")}/ws/games/runs/${runId}?token=${encodeURIComponent(token)}`
    const ws = new WebSocket(wsUrl)
    ws.onopen = () => setConnected(true)
    ws.onclose = () => setConnected(false)
    ws.onmessage = (ev) => {
      try {
        onMessageRef.current(JSON.parse(ev.data))
      } catch {
        // malformed frame — ignore rather than crash the console
      }
    }
    return () => ws.close()
  }, [runId])

  return { connected }
}

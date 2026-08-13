import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { isAxiosError } from "axios"
import { Pencil } from "lucide-react"
import { updateMyProfileApi } from "@/api/games_play"
import { AVATAR_PRESETS } from "./avatarPresets"
import { AvatarBadge } from "./AvatarBadge"

function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") return err.response.data.detail
  return fallback
}

/** Lobby-only nickname/avatar override for one game (D18) — a lighter,
 * uncapped sibling of the profile-level weekly-reroll (D2), not a
 * replacement for it. Click the avatar to edit in place; join first with
 * defaults, customize here — the operator's own stated order. */
export function AvatarNicknamePicker({
  runId, nickname, avatar, onUpdated,
}: {
  runId: string
  nickname: string
  avatar: string | null
  onUpdated: (p: { nickname: string; avatar: string | null }) => void
}) {
  const [editing, setEditing] = useState(false)
  const [draftNickname, setDraftNickname] = useState(nickname)
  const [draftAvatar, setDraftAvatar] = useState(avatar)
  const [error, setError] = useState("")

  const save = useMutation({
    mutationFn: () => updateMyProfileApi(runId, draftNickname.trim(), draftAvatar),
    onSuccess: (p) => { onUpdated({ nickname: p.nickname, avatar: p.avatar }); setEditing(false); setError("") },
    onError: (e: unknown) => setError(errorDetail(e, "Couldn't save — try again")),
  })

  if (!editing) {
    return (
      <button
        onClick={() => { setDraftNickname(nickname); setDraftAvatar(avatar); setError(""); setEditing(true) }}
        className="flex flex-col items-center gap-2 text-center cursor-pointer"
      >
        <div className="relative">
          <AvatarBadge avatar={avatar} nickname={nickname} size={96} />
          <span className="absolute -bottom-1 -right-1 w-6 h-6 rounded-full bg-primary text-primary-foreground flex items-center justify-center">
            <Pencil size={12} />
          </span>
        </div>
        <div>
          <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">Your callsign</p>
          <p className="font-display text-lg font-bold">{nickname}</p>
          <p className="text-xs text-muted-foreground mt-0.5">Only your callsign and avatar are shown to the class.</p>
        </div>
      </button>
    )
  }

  return (
    <div className="flex flex-col gap-3 items-center w-full max-w-xs">
      <AvatarBadge avatar={draftAvatar} nickname={draftNickname || nickname} size={96} />
      <input
        value={draftNickname} onChange={(e) => setDraftNickname(e.target.value)} maxLength={64}
        placeholder="Your callsign"
        className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm text-center focus:outline-none focus:border-primary transition-colors"
      />
      <div className="grid grid-cols-5 gap-2 w-full">
        {AVATAR_PRESETS.map((p) => {
          const Icon = p.icon
          const selected = draftAvatar === p.key
          return (
            <button
              key={p.key}
              onClick={() => setDraftAvatar(p.key)}
              title={p.label}
              className={`aspect-square flex items-center justify-center rounded-xl border cursor-pointer transition-colors ${
                selected
                  ? "border-primary bg-primary/14 text-primary ring-2 ring-primary/30"
                  : "border-border bg-card text-muted-foreground hover:border-primary/50"
              }`}
            >
              <Icon size={20} />
            </button>
          )
        })}
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
      <div className="flex gap-2 w-full">
        <button
          onClick={() => setEditing(false)}
          className="flex-1 h-9 border border-border rounded-xl text-xs font-medium text-foreground hover:bg-muted transition-colors cursor-pointer"
        >
          Cancel
        </button>
        <button
          onClick={() => save.mutate()}
          disabled={save.isPending || !draftNickname.trim()}
          className="flex-1 h-9 bg-primary text-primary-foreground rounded-xl text-xs font-semibold hover:opacity-90 transition-colors disabled:opacity-50 cursor-pointer"
        >
          {save.isPending ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  )
}

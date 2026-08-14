/** A mission's authors (mission_managers, 7B-7).
 *
 * The table and its three endpoints have existed since 7B-7 but were never
 * given a screen, so authorship could only be changed by writing SQL. It is
 * many-to-many on purpose — a mission written by an intern and revised by a
 * facilitator has two authors, and the model has always been able to say so.
 *
 * Two things this deliberately does:
 *
 * * **Names link to profiles.** An author credit that you can't click is
 *   just a string; the point of naming someone is being able to find out who
 *   they are.
 * * **It says what the role grants.** "Author" here is a real permission —
 *   stats, the review queue, and the mission's teaching content — but *not*
 *   its grading thresholds, which stay frozen while published. Ops assigning
 *   someone should know which of those they are handing over.
 */
import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { isAxiosError } from "axios"
import { Search, UserPlus, X } from "lucide-react"
import { searchStaffApi, type StaffOption } from "@/api/lms_admin"
import {
  listMissionAuthorsApi, addMissionAuthorApi, removeMissionAuthorApi,
} from "@/api/missions_admin"
import { UserProfileModal } from "@/components/UserProfileModal"

function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") return err.response.data.detail
  return fallback
}

export function MissionAuthorsSection({ missionId }: { missionId: string }) {
  const queryClient = useQueryClient()
  const [query, setQuery] = useState("")
  const [error, setError] = useState("")
  const [profileUserId, setProfileUserId] = useState<string | null>(null)

  const { data: authors = [], isLoading } = useQuery({
    queryKey: ["mission-authors", missionId],
    queryFn: () => listMissionAuthorsApi(missionId),
  })

  const { data: candidates = [] } = useQuery<StaffOption[]>({
    queryKey: ["mission-author-candidates", query],
    queryFn: () => searchStaffApi({ q: query }),
    enabled: query.trim().length >= 2,
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["mission-authors", missionId] })

  const add = useMutation({
    mutationFn: (userId: string) => addMissionAuthorApi(missionId, userId),
    onSuccess: () => { setQuery(""); setError(""); invalidate() },
    onError: (err) => setError(errorDetail(err, "Couldn't add that author.")),
  })

  const remove = useMutation({
    mutationFn: (userId: string) => removeMissionAuthorApi(missionId, userId),
    onSuccess: () => { setError(""); invalidate() },
    onError: (err) => setError(errorDetail(err, "Couldn't remove that author.")),
  })

  const assigned = new Set(authors.map((a) => a.user_id))
  const suggestions = candidates.filter((c) => !assigned.has(c.id)).slice(0, 6)

  return (
    <div className="flex flex-col gap-3">
      <div>
        <h3 className="text-lg font-bold flex items-center">
          <span className="w-1.5 h-6 bg-primary rounded-full mr-3" />
          Authors
        </h3>
        <p className="text-xs text-muted-foreground mt-1 max-w-[70ch] leading-relaxed">
          An author can see this mission's stats, review its submissions and edit its teaching
          content. They cannot change its grading thresholds while it is published — those stay
          frozen so a live edit can't retroactively re-grade work already submitted.
        </p>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : authors.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No authors assigned. Staff can still manage this mission — an author credit is for the
          person who owns it.
        </p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {authors.map((author) => (
            <span
              key={author.user_id}
              className="flex items-center gap-1.5 pl-3 pr-1.5 py-1 rounded-full ring-1 ring-border text-sm"
            >
              <button
                onClick={() => setProfileUserId(author.user_id)}
                className="hover:text-primary hover:underline transition-colors"
                title="Open profile"
              >
                {author.full_name}
              </button>
              <button
                onClick={() => remove.mutate(author.user_id)}
                disabled={remove.isPending}
                title="Remove author"
                className="size-5 rounded-full flex items-center justify-center text-muted-foreground hover:text-destructive hover:bg-muted transition-colors disabled:opacity-40"
              >
                <X size={12} />
              </button>
            </span>
          ))}
        </div>
      )}

      <div className="flex flex-col gap-1.5 max-w-md">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Add an author — search by name or email"
            className="w-full h-9 pl-9 pr-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </div>
        {suggestions.length > 0 && (
          <div className="flex flex-col rounded-xl ring-1 ring-border overflow-hidden">
            {suggestions.map((person) => (
              <button
                key={person.id}
                onClick={() => add.mutate(person.id)}
                disabled={add.isPending}
                className="flex items-center gap-2 px-3 py-2 text-left hover:bg-muted/50 transition-colors disabled:opacity-50"
              >
                <UserPlus size={14} className="text-muted-foreground shrink-0" />
                <span className="min-w-0 flex-1">
                  <span className="block text-sm truncate">{person.full_name}</span>
                  <span className="block text-[11px] text-muted-foreground truncate">{person.email}</span>
                </span>
              </button>
            ))}
          </div>
        )}
        {query.trim().length >= 2 && suggestions.length === 0 && (
          <p className="text-[11px] text-muted-foreground">No matching staff account.</p>
        )}
      </div>

      {error && <p className="text-xs text-destructive">{error}</p>}

      {profileUserId && (
        <UserProfileModal userId={profileUserId} onClose={() => setProfileUserId(null)} />
      )}
    </div>
  )
}

import { useState } from "react"
import { isAxiosError } from "axios"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { Pencil, Plus, Trash2, Trophy } from "lucide-react"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { ConfirmDialog, Modal, Field, ModalActions } from "@/pages/admin/components/common"
import { listGamesApi, createGameApi, updateGameApi, deleteGameApi, type Game } from "@/api/games_admin"

/** Live Quiz authoring (Live Games Phase 2C, 8-3) — the games list, same
 * shape as LmsCourses.tsx. Frame system in the shipped design starts one
 * level in (a specific game's editor); this is the index that gets you
 * there. */
export default function LmsGames() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [title, setTitle] = useState("")
  const [description, setDescription] = useState("")
  // Renaming and deleting were only reachable from inside a game's editor,
  // which meant fixing a typo in a title took three navigations and there
  // was no way at all to clear out a game you'd created by accident.
  const [editing, setEditing] = useState<Game | null>(null)
  const [deleting, setDeleting] = useState<Game | null>(null)

  const { data: games = [], isLoading } = useQuery<Game[]>({
    queryKey: ["games-admin"],
    queryFn: listGamesApi,
  })

  const createMutation = useMutation({
    mutationFn: () => createGameApi({ title, description: description || null }),
    onSuccess: (game) => {
      setCreateOpen(false); setTitle(""); setDescription("")
      queryClient.invalidateQueries({ queryKey: ["games-admin"] })
      void navigate({ to: `/lms-authoring/games/${game.id}` })
    },
  })

  const updateMutation = useMutation({
    mutationFn: () => updateGameApi(editing!.id, { title, description: description || null }),
    onSuccess: () => {
      setEditing(null); setTitle(""); setDescription("")
      queryClient.invalidateQueries({ queryKey: ["games-admin"] })
    },
  })

  const [deleteError, setDeleteError] = useState("")

  const deleteMutation = useMutation({
    mutationFn: () => deleteGameApi(deleting!.id),
    onSuccess: () => {
      setDeleting(null); setDeleteError("")
      queryClient.invalidateQueries({ queryKey: ["games-admin"] })
    },
    // A game that has been assigned to a session can't be deleted — the
    // assignment records what that session ran. The server says which, so
    // show its sentence rather than a generic failure.
    onError: (err) => setDeleteError(
      (isAxiosError(err) && typeof err.response?.data?.detail === "string")
        ? err.response.data.detail
        : "Couldn't delete this game.",
    ),
  })

  const openEdit = (game: Game) => {
    setEditing(game); setTitle(game.title); setDescription(game.description ?? "")
  }

  if (isLoading) return <Spinner />

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Live Quiz"
        subtitle="Build reusable question sets for live, synchronous games — ops assigns them to a session, the instructor runs them."
        action={
          <button
            onClick={() => setCreateOpen(true)}
            className="flex items-center gap-1.5 h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 transition-colors"
          >
            <Plus size={14} /> New game
          </button>
        }
      />

      {games.length === 0 ? (
        <EmptyState title="No games yet" hint="Create one to start writing questions." />
      ) : (
        <div className="flex flex-col gap-2">
          {games.map((game) => (
            <div
              key={game.id}
              onClick={() => void navigate({ to: `/lms-authoring/games/${game.id}` })}
              className="flex items-center gap-4 p-4 bg-card border border-border rounded-2xl hover:border-muted-foreground/30 transition-colors cursor-pointer"
            >
              <div className="w-11 h-11 rounded-xl bg-primary/10 flex items-center justify-center shrink-0 text-primary">
                <Trophy size={20} />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-foreground truncate">{game.title}</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {game.question_count} question{game.question_count === 1 ? "" : "s"}
                  {game.description ? ` · ${game.description}` : ""}
                </p>
              </div>
              <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
                <button
                  onClick={() => openEdit(game)}
                  title="Rename"
                  className="size-8 rounded-lg flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                >
                  <Pencil size={14} />
                </button>
                <button
                  onClick={() => setDeleting(game)}
                  title="Delete"
                  className="size-8 rounded-lg flex items-center justify-center text-muted-foreground hover:text-destructive hover:bg-muted transition-colors"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {editing && (
        <Modal title="Rename game" onClose={() => setEditing(null)}>
          <div className="flex flex-col gap-4">
            <Field label="Title">
              <input
                value={title} onChange={(e) => setTitle(e.target.value)} autoFocus
                className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary"
              />
            </Field>
            <Field label="Description (optional)">
              <textarea
                value={description} onChange={(e) => setDescription(e.target.value)} rows={2}
                className="w-full px-3 py-2 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary resize-none"
              />
            </Field>
            <ModalActions
              onCancel={() => setEditing(null)}
              onConfirm={() => title.trim() && updateMutation.mutate()}
              loading={updateMutation.isPending}
              disabled={!title.trim()}
              label="Save"
            />
          </div>
        </Modal>
      )}

      {deleting && (
        <ConfirmDialog
          title={`Delete "${deleting.title}"`}
          description={
            deleteError
            || `This removes the game and its ${deleting.question_count} question`
              + `${deleting.question_count === 1 ? "" : "s"}, and can't be undone. A game that `
              + `has already been assigned to a session can't be deleted at all.`
          }
          confirmLabel="Delete"
          destructive
          pending={deleteMutation.isPending}
          onCancel={() => { setDeleting(null); setDeleteError("") }}
          onConfirm={() => deleteMutation.mutate()}
        />
      )}

      {createOpen && (
        <Modal title="New game" onClose={() => setCreateOpen(false)}>
          <div className="flex flex-col gap-4">
            <Field label="Title">
              <input
                value={title} onChange={(e) => setTitle(e.target.value)} autoFocus
                className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary"
              />
            </Field>
            <Field label="Description (optional)">
              <textarea
                value={description} onChange={(e) => setDescription(e.target.value)} rows={2}
                className="w-full px-3 py-2 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary resize-none"
              />
            </Field>
            <ModalActions
              onCancel={() => setCreateOpen(false)}
              onConfirm={() => title.trim() && createMutation.mutate()}
              loading={createMutation.isPending}
              disabled={!title.trim()}
              label="Create"
            />
          </div>
        </Modal>
      )}
    </div>
  )
}

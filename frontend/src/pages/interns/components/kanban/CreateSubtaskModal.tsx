import { useState } from "react"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Plus, X } from "lucide-react"
import type { Epic, Task, User } from "@/types/interns"
import { getLeaderEpicsApi } from "@/api/interns/epics"
import { createLeaderTaskApi, assignLeaderTaskApi } from "@/api/interns/tasks"
import { createModuleApi } from "@/api/interns/modules"
import { getLeaderTeamMembersApi } from "@/api/interns/teams"

interface Props {
  open: boolean
  onClose: () => void
  tasksKey: string[]
}

export default function CreateTaskModal({ open, onClose, tasksKey }: Props) {
  const queryClient = useQueryClient()

  const [epicId,       setEpicId]       = useState("")
  const [moduleId,     setModuleId]     = useState("")
  const [title,        setTitle]        = useState("")
  const [description,  setDescription]  = useState("")
  const [dueDate,      setDueDate]      = useState("")
  const [expectedTime, setExpectedTime] = useState("")
  const [selectedUsers, setSelectedUsers] = useState<string[]>([])

  // inline module creation
  const [addingModule, setAddingModule] = useState(false)
  const [newModuleName, setNewModuleName] = useState("")
  const [newModuleDesc, setNewModuleDesc] = useState("")

  const { data: epics = [] } = useQuery<Epic[]>({
    queryKey: ["epics", "leader"],
    queryFn: getLeaderEpicsApi,
    enabled: open,
  })

  const { data: teamMembers = [] } = useQuery<User[]>({
    queryKey: ["leader", "team", "members"],
    queryFn: getLeaderTeamMembersApi,
    enabled: open,
  })

  const selectedEpic   = epics.find((e) => e.id === epicId)
  const modules        = selectedEpic?.modules ?? []
  const targetModule   = modules.find((m) => m.id === moduleId) ?? modules[0]

  const toggleUser = (id: string) =>
    setSelectedUsers((prev) => prev.includes(id) ? prev.filter((u) => u !== id) : [...prev, id])

  const createModuleMutation = useMutation({
    mutationFn: () => createModuleApi(epicId, { title: newModuleName.trim(), description: newModuleDesc.trim() || undefined }, "leader"),
    onSuccess: (mod) => {
      queryClient.invalidateQueries({ queryKey: ["epics", "leader"] })
      setModuleId(mod.id)
      setNewModuleName("")
      setNewModuleDesc("")
      setAddingModule(false)
    },
  })

  const mutation = useMutation({
    mutationFn: async () => {
      if (!targetModule) throw new Error("No module available")
      const task = await createLeaderTaskApi(targetModule.id, {
        title,
        description: description || undefined,
        due_date: dueDate ? new Date(dueDate).toISOString() : undefined,
        expected_time: expectedTime ? Number(expectedTime) : undefined,
      })
      if (selectedUsers.length > 0) {
        return assignLeaderTaskApi(task.id, selectedUsers)
      }
      return task
    },
    onSuccess: (created: Task) => {
      queryClient.setQueryData<Task[]>(tasksKey, (old = []) => [...old, created])
      queryClient.invalidateQueries({ queryKey: tasksKey })
      onClose()
    },
  })

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-md bg-white border border-gray-100 rounded-2xl p-0 overflow-hidden">
        <div className="p-6 flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold text-black">New task</DialogTitle>
          </DialogHeader>

          <div className="flex flex-col gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1.5">Epic *</label>
              <select
                value={epicId} onChange={(e) => { setEpicId(e.target.value); setModuleId(""); setSelectedUsers([]); setAddingModule(false) }}
                className="w-full h-10 px-3 border border-gray-200 rounded-xl text-sm text-black bg-white focus:outline-none focus:border-black transition-colors"
              >
                <option value="">Select epicâ€¦</option>
                {epics.map((e) => <option key={e.id} value={e.id}>{e.title}</option>)}
              </select>
            </div>

            {/* Module picker + inline create */}
            {selectedEpic && (
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="block text-xs font-medium text-gray-500">Module</label>
                  {!addingModule && (
                    <button type="button" onClick={() => setAddingModule(true)}
                      className="flex items-center gap-1 text-[11px] font-medium text-[#643f83] hover:text-[#4a2d63] transition-colors">
                      <Plus size={11} /> New module
                    </button>
                  )}
                </div>

                {addingModule ? (
                  <div className="flex flex-col gap-2">
                    <input
                      value={newModuleName} onChange={(e) => setNewModuleName(e.target.value)}
                      placeholder="Module name" autoFocus
                      className="w-full h-10 px-3 border border-gray-200 rounded-xl text-sm focus:outline-none focus:border-black transition-colors"
                    />
                    <textarea
                      value={newModuleDesc} onChange={(e) => setNewModuleDesc(e.target.value)}
                      placeholder="Scope / description â€” interns will read this" rows={2}
                      className="w-full px-3 py-2 border border-gray-200 rounded-xl text-sm resize-none focus:outline-none focus:border-black transition-colors"
                    />
                    <div className="flex gap-2">
                      <button type="button" onClick={() => createModuleMutation.mutate()}
                        disabled={!newModuleName.trim() || createModuleMutation.isPending}
                        className="h-9 px-4 bg-black text-white rounded-xl text-xs font-medium hover:bg-gray-900 transition-colors disabled:opacity-50">
                        {createModuleMutation.isPending ? "â€¦" : "Add"}
                      </button>
                      <button type="button" onClick={() => { setAddingModule(false); setNewModuleName(""); setNewModuleDesc("") }}
                        className="h-9 px-3 flex items-center gap-1 border border-gray-200 rounded-xl text-xs text-gray-400 hover:text-black transition-colors">
                        <X size={13} /> Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <select
                    value={targetModule?.id ?? ""} onChange={(e) => setModuleId(e.target.value)}
                    className="w-full h-10 px-3 border border-gray-200 rounded-xl text-sm text-black bg-white focus:outline-none focus:border-black transition-colors"
                  >
                    {modules.map((m) => <option key={m.id} value={m.id}>{m.title}</option>)}
                  </select>
                )}
              </div>
            )}

            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1.5">Title *</label>
              <input
                value={title} onChange={(e) => setTitle(e.target.value)}
                placeholder="What needs to be done?"
                className="w-full h-10 px-3 border border-gray-200 rounded-xl text-sm focus:outline-none focus:border-black transition-colors"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1.5">Description</label>
              <textarea
                value={description} onChange={(e) => setDescription(e.target.value)}
                placeholder="Optional detailsâ€¦" rows={2}
                className="w-full px-3 py-2.5 border border-gray-200 rounded-xl text-sm resize-none focus:outline-none focus:border-black transition-colors"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1.5">Due date</label>
                <input
                  type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)}
                  className="w-full h-10 px-3 border border-gray-200 rounded-xl text-sm text-black focus:outline-none focus:border-black transition-colors"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1.5">Expected hours</label>
                <input
                  type="number" min="0" step="0.5" value={expectedTime} onChange={(e) => setExpectedTime(e.target.value)}
                  placeholder="e.g. 3"
                  className="w-full h-10 px-3 border border-gray-200 rounded-xl text-sm focus:outline-none focus:border-black transition-colors"
                />
              </div>
            </div>

            {teamMembers.length > 0 && (
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1.5">Assign to</label>
                <div className="flex flex-col gap-1">
                  {teamMembers.map((u) => (
                    <label key={u.id} className="flex items-center gap-3 cursor-pointer p-2 rounded-xl hover:bg-gray-50 transition-colors">
                      <input type="checkbox" checked={selectedUsers.includes(u.id)} onChange={() => toggleUser(u.id)} className="rounded" />
                      <div className="flex items-center gap-2">
                        <div className="w-7 h-7 rounded-full bg-[#d6c7e1] text-[#643f83] text-xs font-semibold flex items-center justify-center flex-shrink-0">
                          {u.full_name.split(" ").map((n) => n[0]).join("").slice(0, 2).toUpperCase()}
                        </div>
                        <span className="text-sm text-black">{u.full_name}</span>
                      </div>
                    </label>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="flex gap-2 pt-1">
            <button onClick={onClose}
              className="flex-1 h-10 border border-gray-200 rounded-xl text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors">
              Cancel
            </button>
            <button
              onClick={() => mutation.mutate()}
              disabled={!title.trim() || !epicId || !targetModule || mutation.isPending}
              className="flex-1 h-10 bg-black text-white rounded-xl text-sm font-medium hover:bg-gray-900 transition-colors disabled:opacity-50"
            >
              {mutation.isPending ? "Creatingâ€¦" : "Create task"}
            </button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

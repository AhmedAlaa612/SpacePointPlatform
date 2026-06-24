import { api } from "@/api/client"
import type { Proposal } from "@/types/interns"

export const createProposalApi = (
  epicId: string,
  data: { title: string; description?: string }
) => api.post<Proposal>(`/interns/intern/epics/${epicId}/proposals`, data).then((r) => r.data)

export const getEpicProposalsApi = (epicId: string, role: "admin" | "leader") =>
  api.get<Proposal[]>(`/interns/${role}/epics/${epicId}/proposals`).then((r) => r.data)

export const getLeaderAllProposalsApi = () =>
  api.get<Proposal[]>("/interns/leader/proposals").then((r) => r.data)

export const getInternProposalsApi = () =>
  api.get<Proposal[]>("/interns/intern/proposals").then((r) => r.data)

export const reviewProposalApi = (
  proposalId: string,
  data: { status: string; review_note?: string },
  role: "admin" | "leader"
) => api.patch<Proposal>(`/interns/${role}/proposals/${proposalId}`, data).then((r) => r.data)

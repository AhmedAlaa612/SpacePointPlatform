import { api } from "@/api/client"
import type { Lead, LeadComment } from "@/types/ambassadors"

export const getLeadsApi = () => api.get<Lead[]>("/ambassadors/leads").then((r) => r.data)

export const createLeadApi = (data: {
  contact_name: string
  company?: string
  type: string
  notes?: string
}) => api.post<Lead>("/ambassadors/leads", data).then((r) => r.data)

export const updateLeadStatusApi = (id: string, status: string) =>
  api.put<Lead>(`/ambassadors/leads/${id}/status`, { status }).then((r) => r.data)

export const editLeadApi = (
  id: string,
  data: Partial<{ contact_name: string; company: string; type: string; notes: string }>
) => api.patch<Lead>(`/ambassadors/leads/${id}`, data).then((r) => r.data)

export const deleteLeadApi = (id: string) =>
  api.delete(`/ambassadors/leads/${id}`).then((r) => r.data)

export const getLeadCommentsApi = (id: string) =>
  api.get<LeadComment[]>(`/ambassadors/leads/${id}/comments`).then((r) => r.data)

export const addLeadCommentApi = (id: string, body: string) =>
  api.post<LeadComment>(`/ambassadors/leads/${id}/comments`, { body }).then((r) => r.data)

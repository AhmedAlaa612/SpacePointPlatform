import { api } from "@/api/client"
import type { InternProfile, RoleRequest } from "@/types/internship"

// Generic self-apply-for-an-extra-role — gated server-side by an allowlist
// (instructor -> intern only, today). See backend/app/routers/internship.py.
export const createRoleRequestApi = (data: { target_role: string; details: Record<string, unknown> }) =>
  api.post<RoleRequest>("/me/role-requests", data).then((r) => r.data)

export const getMyRoleRequestsApi = () =>
  api.get<RoleRequest[]>("/me/role-requests").then((r) => r.data)

export const getMyInternshipLetterApi = () =>
  api.get<InternProfile | null>("/intern/internship-letter").then((r) => r.data)

export const signInternshipLetterApi = (signature: string) =>
  api.post<InternProfile>("/intern/internship-letter/sign", { signature }).then((r) => r.data)

// ── Admin review ──────────────────────────────────────────────────────────

export const listRoleRequestsAdminApi = (params?: { status?: string; target_role?: string }) => {
  const q = new URLSearchParams()
  if (params?.status) q.set("status", params.status)
  if (params?.target_role) q.set("target_role", params.target_role)
  const query = q.toString() ? `?${q.toString()}` : ""
  return api.get<RoleRequest[]>(`/admin/role-requests${query}`).then((r) => r.data)
}

export interface InternshipApproveBody {
  salutation: string
  activity_description: string
  supervisor_title: string
  supervisor_name: string
  supervisor_email: string
  supervisor_phone: string
  city_id?: string
  duration_weeks?: number
  hours_per_week?: number
  ref_number_override?: number
  admin_notes?: string
}

export const approveRoleRequestApi = (id: string, body: InternshipApproveBody) =>
  api.post<RoleRequest>(`/admin/role-requests/${id}/approve`, body).then((r) => r.data)

export const rejectRoleRequestApi = (id: string, admin_notes?: string) =>
  api.post<RoleRequest>(`/admin/role-requests/${id}/reject`, { admin_notes }).then((r) => r.data)

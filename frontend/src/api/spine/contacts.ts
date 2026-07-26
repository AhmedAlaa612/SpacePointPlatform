import { api } from "@/api/client"
import type {
  ContactDetail,
  ContactRelationshipOut,
  ContactRoleEventOut,
  ContactSearchResponse,
  ContactUpdate,
  Organization,
  OrganizationCreate,
  OrganizationUpdate,
} from "@/types/spine"

export const searchContactsApi = (params: {
  q?: string
  role?: string
  lifecycle_stage?: string
  country?: string
  limit?: number
  offset?: number
}) => api.get<ContactSearchResponse>("/spine/contacts", { params }).then((r) => r.data)

export const getContactApi = (id: string) =>
  api.get<ContactDetail>(`/spine/contacts/${id}`).then((r) => r.data)

export const updateContactApi = (id: string, data: ContactUpdate) =>
  api.patch<ContactDetail>(`/spine/contacts/${id}`, data).then((r) => r.data)

export const getContactRoleHistoryApi = (id: string) =>
  api.get<ContactRoleEventOut[]>(`/spine/contacts/${id}/role-history`).then((r) => r.data)

export const createContactRelationshipApi = (
  contactId: string,
  data: { related_contact_id: string; relation: string }
) => api.post<ContactRelationshipOut>(`/spine/contacts/${contactId}/relationships`, data).then((r) => r.data)

export const listOrganizationsApi = (q?: string) =>
  api.get<Organization[]>("/spine/organizations", { params: q ? { q } : undefined }).then((r) => r.data)

export const createOrganizationApi = (data: OrganizationCreate) =>
  api.post<Organization>("/spine/organizations", data).then((r) => r.data)

export const getOrganizationApi = (id: string) =>
  api.get<Organization>(`/spine/organizations/${id}`).then((r) => r.data)

export const updateOrganizationApi = (id: string, data: OrganizationUpdate) =>
  api.patch<Organization>(`/spine/organizations/${id}`, data).then((r) => r.data)

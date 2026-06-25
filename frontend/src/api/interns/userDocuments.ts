import { api } from "@/api/client"

export const generateConfirmationLetterApi = (id: string) =>
  api.post<{ file_url: string }>(`/interns/admin/users/${id}/confirmation-letter`).then((r) => r.data)

export const generateCompletionLetterApi = (id: string) =>
  api.post<{ file_url: string }>(`/interns/admin/users/${id}/completion-letter`).then((r) => r.data)

export const generateCertificateApi = (id: string) =>
  api.post<{ file_url: string }>(`/interns/admin/users/${id}/certificate`).then((r) => r.data)

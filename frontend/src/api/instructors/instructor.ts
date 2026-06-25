import { api } from "@/api/client"
import type { BankDetails, IdCard, InstructorDocument, InstructorProfile } from "@/types/instructors"

export const getProfileApi = () =>
  api.get<InstructorProfile>("/instructors/profile").then((r) => r.data)

export const updateProfileApi = (data: { linkedin_url?: string }) =>
  api.put<InstructorProfile>("/instructors/profile", data).then((r) => r.data)

export const getIdCardApi = () =>
  api.get<IdCard | null>("/instructors/id-card").then((r) => r.data)

export const generateIdCardApi = (photo: File, linkedinUrl?: string) => {
  const form = new FormData()
  form.append("photo", photo)
  const qs = linkedinUrl ? `?linkedin_url=${encodeURIComponent(linkedinUrl)}` : ""
  return api.post<IdCard>(`/instructors/id-card${qs}`, form).then((r) => r.data)
}

export const getBankDetailsApi = () =>
  api.get<BankDetails>("/instructors/bank-details").then((r) => r.data)

export const updateBankDetailsApi = (data: Partial<BankDetails>) =>
  api.put<BankDetails>("/instructors/bank-details", data).then((r) => r.data)

export const listDocumentsApi = () =>
  api.get<InstructorDocument[]>("/instructors/documents").then((r) => r.data)

export const uploadDocumentApi = (documentType: string, file: File) => {
  const form = new FormData()
  form.append("file", file)
  return api.post<InstructorDocument>(
    `/instructors/documents?document_type=${encodeURIComponent(documentType)}`, form
  ).then((r) => r.data)
}

export const deleteDocumentApi = (docId: string) =>
  api.delete(`/instructors/documents/${docId}`).then((r) => r.data)

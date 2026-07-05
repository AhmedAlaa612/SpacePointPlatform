import { api } from "@/api/client"
import type { BankDetails, InstructorDocument, InstructorProfile } from "@/types/instructors"

export const getProfileApi = () =>
  api.get<InstructorProfile>("/instructors/profile").then((r) => r.data)

export const updateProfileApi = (data: { linkedin_url?: string }) =>
  api.put<InstructorProfile>("/instructors/profile", data).then((r) => r.data)

export const signContractApi = (signature: string) =>
  api.post<InstructorProfile>("/instructors/contract/sign", { signature }).then((r) => r.data)

import {
  getIdCardApi as getSharedIdCard,
  updateIdCardApi as updateSharedIdCard,
  downloadIdCardPdfApi as downloadSharedIdCardPdf,
} from "@/api/documents"

export const getIdCardApi = (role: string = "instructor") => getSharedIdCard(role)

/** Upload a new photo and/or set LinkedIn URL — returns freshly rendered card */
export const updateIdCardApi = (photo?: File, linkedinUrl?: string, role: string = "instructor") =>
  updateSharedIdCard(role, photo, linkedinUrl)

/** Download the PDF version of the card */
export const downloadIdCardPdfApi = (role: string = "instructor") => downloadSharedIdCardPdf(role)

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

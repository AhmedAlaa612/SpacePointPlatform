import { api } from "@/api/client"
import type { BankDetails, InstructorProfile } from "@/types/instructors"

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
  listDocumentsApi as listSharedDocuments,
  uploadDocumentApi as uploadSharedDocument,
  deleteDocumentApi as deleteSharedDocument,
} from "@/api/documents"

export const getIdCardApi = (role: string = "instructor") => getSharedIdCard(role)

/** Upload a new photo and/or set LinkedIn URL — returns freshly rendered card */
export const updateIdCardApi = (photo?: File, linkedinUrl?: string, role: string = "instructor") =>
  updateSharedIdCard(role, photo, linkedinUrl)

/** Download the PDF version of the card */
export const downloadIdCardPdfApi = (role: string = "instructor") => downloadSharedIdCardPdf(role)

export const listDocumentsApi = listSharedDocuments
export const uploadDocumentApi = uploadSharedDocument
export const deleteDocumentApi = deleteSharedDocument

export const getBankDetailsApi = () =>
  api.get<BankDetails>("/instructors/bank-details").then((r) => r.data)

export const updateBankDetailsApi = (data: Partial<BankDetails>) =>
  api.put<BankDetails>("/instructors/bank-details", data).then((r) => r.data)

import { api } from "@/api/client"
import type { MyDocuments, RecommendationLetter } from "@/types/documents"

export const getMyDocumentsApi = () =>
  api.get<MyDocuments>("/documents/me").then((r) => r.data)

export const generateRecommendationLetterApi = (data: {
  user_id: string
  recommendation_text: string
  signatory_name?: string
  signatory_title?: string
}) =>
  api.post<RecommendationLetter>("/documents/recommendation-letters", data).then((r) => r.data)

export const listRecommendationLettersApi = (userId: string) =>
  api.get<RecommendationLetter[]>(`/documents/recommendation-letters?user_id=${userId}`).then((r) => r.data)

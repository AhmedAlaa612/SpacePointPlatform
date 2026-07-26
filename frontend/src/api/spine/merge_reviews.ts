import { api } from "@/api/client"
import type { MergeResolveRequest, MergeReviewOut } from "@/types/spine"

export const getMergeReviewsApi = (status: string = "pending") =>
  api.get<MergeReviewOut[]>("/spine/merge-reviews", { params: { status } }).then((r) => r.data)

export const resolveMergeReviewApi = (id: string, data: MergeResolveRequest) =>
  api.post<MergeReviewOut>(`/spine/merge-reviews/${id}/resolve`, data).then((r) => r.data)

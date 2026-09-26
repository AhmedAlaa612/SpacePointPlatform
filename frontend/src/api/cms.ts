import { api } from "@/api/client";
import type {
  Article,
  ArticleCreateInput,
  ArticleUpdateInput,
  ArticleReviewInput,
  Sponsor,
  SponsorCreateInput,
  SponsorUpdateInput,
  MediaClipping,
  MediaClippingCreateInput,
  MediaClippingUpdateInput,
  StudentMission,
  StudentMissionCreateInput,
  StudentMissionUpdateInput,
  WebsiteLead,
  WebsiteLeadStatus,
} from "@/types/cms";

// ── Contributor Articles ──────────────────────────────────────────────────────

export async function getMyArticles(): Promise<Article[]> {
  const { data } = await api.get<Article[]>("/cms/articles/my");
  return data;
}

export async function getArticle(articleId: string): Promise<Article> {
  const { data } = await api.get<Article>(`/cms/articles/${articleId}`);
  return data;
}

export async function createArticle(payload: ArticleCreateInput): Promise<Article> {
  const { data } = await api.post<Article>("/cms/articles", payload);
  return data;
}

export async function updateArticle(articleId: string, payload: ArticleUpdateInput): Promise<Article> {
  const { data } = await api.patch<Article>(`/cms/articles/${articleId}`, payload);
  return data;
}

export async function deleteArticle(articleId: string): Promise<void> {
  await api.delete(`/cms/articles/${articleId}`);
}

// ── Operations Website CMS ───────────────────────────────────────────────────

export async function getAllArticles(params?: {
  status_filter?: string;
  category?: string;
}): Promise<Article[]> {
  const { data } = await api.get<Article[]>("/operations/website/articles", { params });
  return data;
}

export async function reviewArticle(
  articleId: string,
  payload: ArticleReviewInput
): Promise<Article> {
  const { data } = await api.post<Article>(`/operations/website/articles/${articleId}/review`, payload);
  return data;
}

// ── Sponsors ─────────────────────────────────────────────────────────────────

export async function getAllSponsors(): Promise<Sponsor[]> {
  const { data } = await api.get<Sponsor[]>("/operations/website/sponsors");
  return data;
}

export async function createSponsor(payload: SponsorCreateInput): Promise<Sponsor> {
  const { data } = await api.post<Sponsor>("/operations/website/sponsors", payload);
  return data;
}

export async function updateSponsor(sponsorId: string, payload: SponsorUpdateInput): Promise<Sponsor> {
  const { data } = await api.patch<Sponsor>(`/operations/website/sponsors/${sponsorId}`, payload);
  return data;
}

export async function deleteSponsor(sponsorId: string): Promise<void> {
  await api.delete(`/operations/website/sponsors/${sponsorId}`);
}

// ── Media Clippings ──────────────────────────────────────────────────────────

export async function getAllMediaClippings(): Promise<MediaClipping[]> {
  const { data } = await api.get<MediaClipping[]>("/operations/website/media");
  return data;
}

export async function createMediaClipping(payload: MediaClippingCreateInput): Promise<MediaClipping> {
  const { data } = await api.post<MediaClipping>("/operations/website/media", payload);
  return data;
}

export async function updateMediaClipping(
  clippingId: string,
  payload: MediaClippingUpdateInput
): Promise<MediaClipping> {
  const { data } = await api.patch<MediaClipping>(`/operations/website/media/${clippingId}`, payload);
  return data;
}

export async function deleteMediaClipping(clippingId: string): Promise<void> {
  await api.delete(`/operations/website/media/${clippingId}`);
}

// ── Student Missions ─────────────────────────────────────────────────────────

export async function getAllStudentMissions(): Promise<StudentMission[]> {
  const { data } = await api.get<StudentMission[]>("/operations/website/student-missions");
  return data;
}

export async function createStudentMission(payload: StudentMissionCreateInput): Promise<StudentMission> {
  const { data } = await api.post<StudentMission>("/operations/website/student-missions", payload);
  return data;
}

export async function updateStudentMission(
  missionId: string,
  payload: StudentMissionUpdateInput
): Promise<StudentMission> {
  const { data } = await api.patch<StudentMission>(`/operations/website/student-missions/${missionId}`, payload);
  return data;
}

export async function deleteStudentMission(missionId: string): Promise<void> {
  await api.delete(`/operations/website/student-missions/${missionId}`);
}

// ── Website Leads CRM ────────────────────────────────────────────────────────

export async function getWebsiteLeads(params?: {
  lead_type?: string;
  status_filter?: string;
}): Promise<WebsiteLead[]> {
  const { data } = await api.get<WebsiteLead[]>("/operations/website/leads", { params });
  return data;
}

export async function updateWebsiteLeadStatus(
  leadId: string,
  status: WebsiteLeadStatus
): Promise<WebsiteLead> {
  const { data } = await api.patch<WebsiteLead>(`/operations/website/leads/${leadId}`, { status });
  return data;
}

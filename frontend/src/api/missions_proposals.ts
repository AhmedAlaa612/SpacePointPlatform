/** Intern mission proposal pipeline (7B-6) — thin wrapper over
 * `/missions/proposals/*`. Types mirror `schemas/missions_proposals.py`. */
import { api } from "@/api/client";

export type ProposalStatus = "submitted" | "in_review" | "approved" | "rejected";

export interface MissionProposal {
  id: string;
  title: string;
  description: string;
  repo_url: string | null;
  zip_url: string | null;
  submitted_by: string;
  submitted_by_name: string;
  status: ProposalStatus;
  reviewed_by: string | null;
  review_notes: string | null;
  mission_id: string | null;
  created_at: string | null;
  decided_at: string | null;
}

export interface MissionProposalCreateInput {
  title: string;
  description: string;
  repo_url?: string | null;
}

export const myProposalsApi = () =>
  api.get<MissionProposal[]>("/missions/proposals/mine").then((r) => r.data);

export const createProposalApi = (data: MissionProposalCreateInput) =>
  api.post<MissionProposal>("/missions/proposals", data).then((r) => r.data);

export const uploadProposalZipApi = (proposalId: string, file: File) => {
  const form = new FormData();
  form.append("file", file);
  return api.post<MissionProposal>(`/missions/proposals/${proposalId}/zip`, form).then((r) => r.data);
};

export const proposalQueueApi = () =>
  api.get<MissionProposal[]>("/missions/proposals/queue").then((r) => r.data);

export const reviewProposalApi = (proposalId: string, data: { status: ProposalStatus; review_notes?: string | null }) =>
  api.post<MissionProposal>(`/missions/proposals/${proposalId}/review`, data).then((r) => r.data);

export const linkProposalMissionApi = (proposalId: string, missionId: string) =>
  api.post<MissionProposal>(`/missions/proposals/${proposalId}/link-mission`, { mission_id: missionId }).then((r) => r.data);

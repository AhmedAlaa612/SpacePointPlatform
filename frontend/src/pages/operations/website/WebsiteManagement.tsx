import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  FileText,
  Building2,
  Rocket,
  Newspaper,
  Mail,
  Plus,
  Search,
  ExternalLink,
  Edit,
  Trash2,
  CheckCircle2,
  Clock,
  AlertTriangle,
  Download,
  Eye,
  Globe,
  Sliders,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader, StatCard, EmptyState, Spinner } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { ArticleReviewModal } from "@/components/cms/ArticleReviewModal";
import { SponsorModal } from "@/components/cms/SponsorModal";
import { StudentMissionModal } from "@/components/cms/StudentMissionModal";
import { MediaClippingModal } from "@/components/cms/MediaClippingModal";
import { LeadDetailModal } from "@/components/cms/LeadDetailModal";

import {
  getAllArticles,
  reviewArticle,
  getAllSponsors,
  createSponsor,
  updateSponsor,
  deleteSponsor,
  getAllStudentMissions,
  createStudentMission,
  updateStudentMission,
  deleteStudentMission,
  getAllMediaClippings,
  createMediaClipping,
  updateMediaClipping,
  deleteMediaClipping,
  getWebsiteLeads,
  updateWebsiteLeadStatus,
} from "@/api/cms";

import type {
  Article,
  ArticleReviewInput,
  Sponsor,
  SponsorCreateInput,
  SponsorUpdateInput,
  StudentMission,
  StudentMissionCreateInput,
  StudentMissionUpdateInput,
  MediaClipping,
  MediaClippingCreateInput,
  MediaClippingUpdateInput,
  WebsiteLead,
  WebsiteLeadStatus,
} from "@/types/cms";

export default function WebsiteManagement() {
  const queryClient = useQueryClient();
  const toast = useToast();

  const [activeTab, setActiveTab] = useState<"articles" | "sponsors" | "missions" | "media" | "leads">("articles");

  // ─────────────────────────────────────────────────────────────────────────────
  // TAB 1: ARTICLES & EDITORIAL QUEUE
  // ─────────────────────────────────────────────────────────────────────────────
  const [articleStatusFilter, setArticleStatusFilter] = useState<string>("all");
  const [articleSearch, setArticleSearch] = useState("");
  const [selectedArticleForReview, setSelectedArticleForReview] = useState<Article | null>(null);

  const { data: articles = [], isLoading: loadingArticles } = useQuery({
    queryKey: ["website-articles"],
    queryFn: () => getAllArticles(),
  });

  const reviewMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ArticleReviewInput }) =>
      reviewArticle(id, payload),
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: ["website-articles"] });
      queryClient.invalidateQueries({ queryKey: ["my-articles"] });
      const actionName =
        vars.payload.action === "approve"
          ? "Article approved & published!"
          : vars.payload.action === "request_changes"
          ? "Feedback sent to author."
          : vars.payload.action === "unpublish"
          ? "Article unpublished to draft."
          : "Article archived.";
      toast?.success(actionName);
    },
    onError: (err: any) => {
      toast?.error(err?.response?.data?.detail || "Review action failed.");
    },
  });

  const filteredArticles = useMemo(() => {
    return articles.filter((art) => {
      const matchesStatus =
        articleStatusFilter === "all" || art.status === articleStatusFilter;
      const matchesSearch =
        articleSearch.trim() === "" ||
        art.title.toLowerCase().includes(articleSearch.toLowerCase()) ||
        art.author_display_name.toLowerCase().includes(articleSearch.toLowerCase()) ||
        art.category.toLowerCase().includes(articleSearch.toLowerCase());
      return matchesStatus && matchesSearch;
    });
  }, [articles, articleStatusFilter, articleSearch]);

  const articleCounts = useMemo(() => {
    const inReview = articles.filter((a) => a.status === "in_review").length;
    const published = articles.filter((a) => a.status === "published").length;
    const changes = articles.filter((a) => a.status === "changes_requested").length;
    return { inReview, published, changes, total: articles.length };
  }, [articles]);

  // ─────────────────────────────────────────────────────────────────────────────
  // TAB 2: SPONSORS & MARQUEE
  // ─────────────────────────────────────────────────────────────────────────────
  const [sponsorTierFilter, setSponsorTierFilter] = useState<string>("all");
  const [sponsorModalOpen, setSponsorModalOpen] = useState(false);
  const [sponsorToEdit, setSponsorToEdit] = useState<Sponsor | null>(null);

  const { data: sponsors = [], isLoading: loadingSponsors } = useQuery({
    queryKey: ["website-sponsors"],
    queryFn: getAllSponsors,
  });

  const saveSponsorMutation = useMutation({
    mutationFn: async (payload: SponsorCreateInput | SponsorUpdateInput) => {
      if (sponsorToEdit) {
        return updateSponsor(sponsorToEdit.id, payload);
      }
      return createSponsor(payload as SponsorCreateInput);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["website-sponsors"] });
      toast?.success(sponsorToEdit ? "Sponsor updated." : "Sponsor added.");
    },
    onError: (err: any) => {
      toast?.error(err?.response?.data?.detail || "Failed to save sponsor.");
    },
  });

  const toggleSponsorActiveMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      updateSponsor(id, { is_active }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["website-sponsors"] });
    },
  });

  const deleteSponsorMutation = useMutation({
    mutationFn: (id: string) => deleteSponsor(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["website-sponsors"] });
      toast?.success("Sponsor removed.");
    },
  });

  const filteredSponsors = useMemo(() => {
    return sponsors.filter(
      (s) => sponsorTierFilter === "all" || s.tier === sponsorTierFilter
    );
  }, [sponsors, sponsorTierFilter]);

  // ─────────────────────────────────────────────────────────────────────────────
  // TAB 3: STUDENT MISSIONS & SHOWCASE
  // ─────────────────────────────────────────────────────────────────────────────
  const [missionModalOpen, setMissionModalOpen] = useState(false);
  const [missionToEdit, setMissionToEdit] = useState<StudentMission | null>(null);

  const { data: missions = [], isLoading: loadingMissions } = useQuery({
    queryKey: ["website-student-missions"],
    queryFn: getAllStudentMissions,
  });

  const saveMissionMutation = useMutation({
    mutationFn: async (payload: StudentMissionCreateInput | StudentMissionUpdateInput) => {
      if (missionToEdit) {
        return updateStudentMission(missionToEdit.id, payload);
      }
      return createStudentMission(payload as StudentMissionCreateInput);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["website-student-missions"] });
      toast?.success(missionToEdit ? "Student mission updated." : "Student mission added.");
    },
    onError: (err: any) => {
      toast?.error(err?.response?.data?.detail || "Failed to save student mission.");
    },
  });

  const toggleMissionActiveMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      updateStudentMission(id, { is_active }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["website-student-missions"] });
    },
  });

  const deleteMissionMutation = useMutation({
    mutationFn: (id: string) => deleteStudentMission(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["website-student-missions"] });
      toast?.success("Student mission removed.");
    },
  });

  // ─────────────────────────────────────────────────────────────────────────────
  // TAB 4: PRESS & MEDIA COVERAGE
  // ─────────────────────────────────────────────────────────────────────────────
  const [mediaModalOpen, setMediaModalOpen] = useState(false);
  const [mediaToEdit, setMediaToEdit] = useState<MediaClipping | null>(null);

  const { data: mediaClippings = [], isLoading: loadingMedia } = useQuery({
    queryKey: ["website-media"],
    queryFn: getAllMediaClippings,
  });

  const saveMediaMutation = useMutation({
    mutationFn: async (payload: MediaClippingCreateInput | MediaClippingUpdateInput) => {
      if (mediaToEdit) {
        return updateMediaClipping(mediaToEdit.id, payload);
      }
      return createMediaClipping(payload as MediaClippingCreateInput);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["website-media"] });
      toast?.success(mediaToEdit ? "Media clipping updated." : "Media clipping added.");
    },
    onError: (err: any) => {
      toast?.error(err?.response?.data?.detail || "Failed to save media clipping.");
    },
  });

  const toggleMediaActiveMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      updateMediaClipping(id, { is_active }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["website-media"] });
    },
  });

  const deleteMediaMutation = useMutation({
    mutationFn: (id: string) => deleteMediaClipping(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["website-media"] });
      toast?.success("Media clipping deleted.");
    },
  });

  // ─────────────────────────────────────────────────────────────────────────────
  // TAB 5: WEBSITE LEADS CRM
  // ─────────────────────────────────────────────────────────────────────────────
  const [leadTypeFilter, setLeadTypeFilter] = useState<string>("all");
  const [leadStatusFilter, setLeadStatusFilter] = useState<string>("all");
  const [selectedLead, setSelectedLead] = useState<WebsiteLead | null>(null);

  const { data: leads = [], isLoading: loadingLeads } = useQuery({
    queryKey: ["website-leads", leadTypeFilter, leadStatusFilter],
    queryFn: () =>
      getWebsiteLeads({
        lead_type: leadTypeFilter === "all" ? undefined : leadTypeFilter,
        status_filter: leadStatusFilter === "all" ? undefined : leadStatusFilter,
      }),
  });

  const updateLeadMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: WebsiteLeadStatus }) =>
      updateWebsiteLeadStatus(id, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["website-leads"] });
      toast?.success("Lead status updated.");
    },
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Website Management & CMS"
        subtitle="Manage public marketing articles, sponsor logos, student mission showcases, media coverage, and inbound website leads."
      />

      {/* Main Tab Navigation */}
      <div className="flex items-center gap-2 border-b border-border pb-1 overflow-x-auto">
        {[
          {
            id: "articles",
            label: "Editorial Queue",
            icon: FileText,
            badge: articleCounts.inReview > 0 ? articleCounts.inReview : null,
          },
          { id: "sponsors", label: "Sponsors & Marquee", icon: Building2, count: sponsors.length },
          { id: "missions", label: "Student Missions", icon: Rocket, count: missions.length },
          { id: "media", label: "Media Coverage", icon: Newspaper, count: mediaClippings.length },
          { id: "leads", label: "Website Leads CRM", icon: Mail, count: leads.length },
        ].map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;

          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-semibold transition-all whitespace-nowrap ${
                isActive
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted/40"
              }`}
            >
              <Icon className="w-4 h-4" />
              <span>{tab.label}</span>
              {tab.badge !== null && (
                <span className="px-1.5 py-0.2 rounded-full text-[10px] font-bold bg-amber-500 text-black animate-pulse">
                  {tab.badge}
                </span>
              )}
              {tab.count !== undefined && !tab.badge && (
                <span
                  className={`text-[10px] px-1.5 py-0.2 rounded-full ${
                    isActive ? "bg-primary-foreground/20 text-primary-foreground" : "bg-muted text-muted-foreground"
                  }`}
                >
                  {tab.count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* ─────────────────────────────────────────────────────────────────────────────
          TAB 1: EDITORIAL ARTICLES
         ───────────────────────────────────────────────────────────────────────────── */}
      {activeTab === "articles" && (
        <div className="space-y-5 animate-in fade-in-0 duration-200">
          {/* Quick Stats */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <StatCard
              icon={<Clock className="w-5 h-5 text-blue-400" />}
              label="Pending Review"
              value={articleCounts.inReview}
              sub={articleCounts.inReview > 0 ? "Requires editor approval" : "All reviewed"}
            />
            <StatCard
              icon={<AlertTriangle className="w-5 h-5 text-amber-400" />}
              label="Changes Requested"
              value={articleCounts.changes}
              sub="With authors for edit"
            />
            <StatCard
              icon={<CheckCircle2 className="w-5 h-5 text-emerald-400" />}
              label="Published Online"
              value={articleCounts.published}
              sub="Live on public website"
            />
            <StatCard
              icon={<FileText className="w-5 h-5 text-primary" />}
              label="Total Articles"
              value={articleCounts.total}
              sub="All platform content"
            />
          </div>

          {/* Filtering Bar */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0">
              {[
                { id: "all", label: "All Statuses" },
                { id: "in_review", label: "Needs Review", highlight: articleCounts.inReview > 0 },
                { id: "changes_requested", label: "Changes Requested" },
                { id: "published", label: "Published" },
                { id: "draft", label: "Drafts" },
              ].map((filter) => (
                <button
                  key={filter.id}
                  onClick={() => setArticleStatusFilter(filter.id)}
                  className={`px-3 py-1.5 rounded-xl text-xs font-medium transition-all whitespace-nowrap ${
                    articleStatusFilter === filter.id
                      ? "bg-muted text-foreground border border-border font-semibold shadow-xs"
                      : filter.highlight
                      ? "bg-amber-500/10 text-amber-400 border border-amber-500/30"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {filter.label}
                </button>
              ))}
            </div>

            <div className="relative w-full sm:w-64">
              <input
                type="text"
                placeholder="Search articles or authors..."
                value={articleSearch}
                onChange={(e) => setArticleSearch(e.target.value)}
                className="w-full pl-9 pr-3 py-1.5 rounded-xl border border-border bg-card/60 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
              />
              <Search className="w-3.5 h-3.5 text-muted-foreground absolute left-3 top-2.5" />
            </div>
          </div>

          {/* Articles Table */}
          {loadingArticles ? (
            <Spinner size="lg" />
          ) : filteredArticles.length === 0 ? (
            <EmptyState title="No articles match current filters." />
          ) : (
            <div className="rounded-2xl border border-border bg-card/70 overflow-hidden shadow-xs">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-muted/40 border-b border-border text-muted-foreground uppercase text-[10px] tracking-wider font-semibold">
                    <tr>
                      <th className="py-3 px-4">Article</th>
                      <th className="py-3 px-4">Author</th>
                      <th className="py-3 px-4">Category</th>
                      <th className="py-3 px-4">Status</th>
                      <th className="py-3 px-4">Last Updated</th>
                      <th className="py-3 px-4 text-right">Editorial Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {filteredArticles.map((art) => (
                      <tr key={art.id} className="hover:bg-muted/20 transition-colors">
                        <td className="py-3 px-4">
                          <div className="font-semibold text-foreground text-sm line-clamp-1">
                            {art.title}
                          </div>
                          {art.summary && (
                            <div className="text-[11px] text-muted-foreground line-clamp-1 mt-0.5">
                              {art.summary}
                            </div>
                          )}
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap">
                          <div className="font-medium text-foreground">{art.author_display_name}</div>
                          <div className="text-[10px] text-muted-foreground">
                            {art.author_role || "Contributor"}
                          </div>
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap">
                          <span className="font-bold uppercase tracking-wider text-[10px] text-primary px-2 py-0.5 rounded-md bg-primary/10">
                            {art.category}
                          </span>
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap">
                          <span
                            className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-semibold ${
                              art.status === "in_review"
                                ? "bg-blue-500/10 text-blue-400 border border-blue-500/20"
                                : art.status === "changes_requested"
                                ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                                : art.status === "published"
                                ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                                : "bg-muted text-muted-foreground"
                            }`}
                          >
                            {art.status.replace("_", " ")}
                          </span>
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap text-muted-foreground text-[11px]">
                          {new Date(art.updated_at).toLocaleDateString()}
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap text-right">
                          <Button
                            size="xs"
                            variant={art.status === "in_review" ? "default" : "outline"}
                            onClick={() => setSelectedArticleForReview(art)}
                            className="gap-1.5"
                          >
                            <Sliders className="w-3 h-3" />
                            {art.status === "in_review" ? "Review & Decide" : "Manage"}
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Article Review Modal */}
          <ArticleReviewModal
            isOpen={!!selectedArticleForReview}
            onClose={() => setSelectedArticleForReview(null)}
            article={selectedArticleForReview}
            onReviewAction={async (id, payload) => {
              await reviewMutation.mutateAsync({ id, payload });
            }}
            isProcessing={reviewMutation.isPending}
          />
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────────────────────
          TAB 2: SPONSORS & MARQUEE
         ───────────────────────────────────────────────────────────────────────────── */}
      {activeTab === "sponsors" && (
        <div className="space-y-5 animate-in fade-in-0 duration-200">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-1.5 overflow-x-auto">
              {[
                { id: "all", label: "All Tiers" },
                { id: "partner", label: "Strategic Partners" },
                { id: "client", label: "Clients & Sponsors" },
                { id: "supporter", label: "Government / Supporters" },
                { id: "academic", label: "Academic" },
              ].map((tier) => (
                <button
                  key={tier.id}
                  onClick={() => setSponsorTierFilter(tier.id)}
                  className={`px-3 py-1.5 rounded-xl text-xs font-medium transition-all whitespace-nowrap ${
                    sponsorTierFilter === tier.id
                      ? "bg-muted text-foreground border border-border font-semibold shadow-xs"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {tier.label}
                </button>
              ))}
            </div>

            <Button
              size="sm"
              onClick={() => {
                setSponsorToEdit(null);
                setSponsorModalOpen(true);
              }}
              className="gap-1.5 self-end sm:self-auto"
            >
              <Plus className="w-4 h-4" />
              Add Brand Sponsor
            </Button>
          </div>

          {loadingSponsors ? (
            <Spinner size="lg" />
          ) : filteredSponsors.length === 0 ? (
            <EmptyState title="No sponsors found in this tier." />
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {filteredSponsors.map((sponsor) => (
                <div
                  key={sponsor.id}
                  className="rounded-2xl border border-border bg-card/70 p-4 flex flex-col justify-between gap-3 hover:border-primary/40 transition-all"
                >
                  <div className="space-y-3">
                    {/* Logo thumbnail */}
                    <div className="h-20 w-full rounded-xl bg-white/5 border border-border/60 flex items-center justify-center p-3 overflow-hidden">
                      <img
                        src={sponsor.logo_url}
                        alt={sponsor.name}
                        className="max-h-full max-w-full object-contain filter drop-shadow-sm"
                        onError={(e) => {
                          (e.target as HTMLElement).style.display = "none";
                        }}
                      />
                    </div>

                    <div>
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded bg-primary/10 text-primary">
                          {sponsor.tier}
                        </span>
                        <span className="text-[11px] text-muted-foreground font-mono">
                          Order: {sponsor.display_order}
                        </span>
                      </div>
                      <h4 className="font-bold text-sm text-foreground mt-1.5">{sponsor.name}</h4>
                      {sponsor.website_url && (
                        <a
                          href={sponsor.website_url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-[11px] text-primary hover:underline flex items-center gap-1 mt-0.5"
                        >
                          <Globe className="w-3 h-3" />
                          Visit Website
                        </a>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center justify-between pt-2 border-t border-border/60">
                    <label className="flex items-center gap-1.5 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={sponsor.is_active}
                        onChange={(e) =>
                          toggleSponsorActiveMutation.mutate({
                            id: sponsor.id,
                            is_active: e.target.checked,
                          })
                        }
                        className="w-3.5 h-3.5 rounded border-border text-primary focus:ring-primary"
                      />
                      <span className="text-[11px] text-muted-foreground">Active</span>
                    </label>

                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => {
                          setSponsorToEdit(sponsor);
                          setSponsorModalOpen(true);
                        }}
                        className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg"
                        title="Edit"
                      >
                        <Edit className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => {
                          if (confirm(`Remove sponsor "${sponsor.name}"?`)) {
                            deleteSponsorMutation.mutate(sponsor.id);
                          }
                        }}
                        className="p-1.5 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-lg"
                        title="Delete"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          <SponsorModal
            isOpen={sponsorModalOpen}
            onClose={() => setSponsorModalOpen(false)}
            onSave={async (payload) => {
              await saveSponsorMutation.mutateAsync(payload);
            }}
            sponsorToEdit={sponsorToEdit}
            isSaving={saveSponsorMutation.isPending}
          />
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────────────────────
          TAB 3: STUDENT MISSIONS & PROJECTS SHOWCASE
         ───────────────────────────────────────────────────────────────────────────── */}
      {activeTab === "missions" && (
        <div className="space-y-5 animate-in fade-in-0 duration-200">
          <div className="flex items-center justify-between">
            <p className="text-xs text-muted-foreground">
              Featuring <strong>{missions.length}</strong> student-authored space missions, high-altitude balloons, and robotics payloads.
            </p>
            <Button
              size="sm"
              onClick={() => {
                setMissionToEdit(null);
                setMissionModalOpen(true);
              }}
              className="gap-1.5"
            >
              <Plus className="w-4 h-4" />
              Add Student Mission
            </Button>
          </div>

          {loadingMissions ? (
            <Spinner size="lg" />
          ) : missions.length === 0 ? (
            <EmptyState title="No student missions found." />
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {missions.map((mission) => (
                <div
                  key={mission.id}
                  className="rounded-2xl border border-border bg-card/70 p-5 flex flex-col justify-between gap-4 hover:border-primary/40 transition-all"
                >
                  <div className="space-y-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <span className="text-[10px] font-bold uppercase tracking-wider text-primary px-2 py-0.5 rounded bg-primary/10">
                          {mission.category}
                        </span>
                        <h3 className="font-bold text-base text-foreground mt-1.5">
                          {mission.project_title}
                        </h3>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          Led by: <strong className="text-foreground">{mission.student_name}</strong>
                        </p>
                      </div>

                      {mission.photo_url && (
                        <div className="w-16 h-16 rounded-xl overflow-hidden border border-border bg-muted/20 shrink-0">
                          <img
                            src={mission.photo_url}
                            alt={mission.project_title}
                            className="w-full h-full object-cover"
                          />
                        </div>
                      )}
                    </div>

                    <p className="text-xs text-muted-foreground leading-relaxed line-clamp-3">
                      {mission.description}
                    </p>

                    {/* Metrics badges */}
                    {mission.metrics_json && Object.keys(mission.metrics_json).length > 0 && (
                      <div className="flex flex-wrap gap-1.5 pt-1">
                        {Object.entries(mission.metrics_json).map(([k, v]) => (
                          <span
                            key={k}
                            className="px-2 py-0.5 rounded-md bg-muted/60 border border-border/50 text-[10px] font-mono text-muted-foreground"
                          >
                            <strong>{k}:</strong> {String(v)}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="flex items-center justify-between pt-3 border-t border-border/60">
                    <div className="flex items-center gap-3">
                      {mission.docx_url && (
                        <a
                          href={mission.docx_url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-[11px] text-primary hover:underline flex items-center gap-1 font-medium"
                        >
                          <Download className="w-3 h-3" />
                          Report (.docx)
                        </a>
                      )}
                      <label className="flex items-center gap-1.5 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={mission.is_active}
                          onChange={(e) =>
                            toggleMissionActiveMutation.mutate({
                              id: mission.id,
                              is_active: e.target.checked,
                            })
                          }
                          className="w-3.5 h-3.5 rounded border-border text-primary focus:ring-primary"
                        />
                        <span className="text-[11px] text-muted-foreground">Showcase</span>
                      </label>
                    </div>

                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => {
                          setMissionToEdit(mission);
                          setMissionModalOpen(true);
                        }}
                        className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg"
                        title="Edit"
                      >
                        <Edit className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => {
                          if (confirm(`Remove student project "${mission.project_title}"?`)) {
                            deleteMissionMutation.mutate(mission.id);
                          }
                        }}
                        className="p-1.5 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-lg"
                        title="Delete"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          <StudentMissionModal
            isOpen={missionModalOpen}
            onClose={() => setMissionModalOpen(false)}
            onSave={async (payload) => {
              await saveMissionMutation.mutateAsync(payload);
            }}
            missionToEdit={missionToEdit}
            isSaving={saveMissionMutation.isPending}
          />
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────────────────────
          TAB 4: PRESS & MEDIA COVERAGE
         ───────────────────────────────────────────────────────────────────────────── */}
      {activeTab === "media" && (
        <div className="space-y-5 animate-in fade-in-0 duration-200">
          <div className="flex items-center justify-between">
            <p className="text-xs text-muted-foreground">
              Manage press releases, news features, and international space media clippings.
            </p>
            <Button
              size="sm"
              onClick={() => {
                setMediaToEdit(null);
                setMediaModalOpen(true);
              }}
              className="gap-1.5"
            >
              <Plus className="w-4 h-4" />
              Add Press Feature
            </Button>
          </div>

          {loadingMedia ? (
            <Spinner size="lg" />
          ) : mediaClippings.length === 0 ? (
            <EmptyState title="No media coverage records." />
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {mediaClippings.map((clipping) => (
                <div
                  key={clipping.id}
                  className="rounded-2xl border border-border bg-card/70 p-5 flex flex-col justify-between gap-3 hover:border-primary/40 transition-all"
                >
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-xs text-primary">{clipping.publisher_name}</span>
                      <div className="flex items-center gap-1.5">
                        {clipping.is_arabic && (
                          <span className="text-[10px] font-bold px-1.5 py-0.2 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
                            العربية (RTL)
                          </span>
                        )}
                        <span className="text-[10px] text-muted-foreground">
                          {new Date(clipping.published_date).toLocaleDateString()}
                        </span>
                      </div>
                    </div>

                    <h4
                      className="font-bold text-sm text-foreground leading-snug"
                      dir={clipping.is_arabic ? "rtl" : "ltr"}
                    >
                      {clipping.article_title}
                    </h4>

                    {clipping.snippet && (
                      <p
                        className="text-xs text-muted-foreground line-clamp-2 italic"
                        dir={clipping.is_arabic ? "rtl" : "ltr"}
                      >
                        "{clipping.snippet}"
                      </p>
                    )}
                  </div>

                  <div className="flex items-center justify-between pt-2 border-t border-border/60">
                    <a
                      href={clipping.article_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-xs text-primary hover:underline flex items-center gap-1 font-medium"
                    >
                      <ExternalLink className="w-3.5 h-3.5" />
                      Read Publication
                    </a>

                    <div className="flex items-center gap-1">
                      <label className="flex items-center gap-1.5 cursor-pointer mr-2">
                        <input
                          type="checkbox"
                          checked={clipping.is_active}
                          onChange={(e) =>
                            toggleMediaActiveMutation.mutate({
                              id: clipping.id,
                              is_active: e.target.checked,
                            })
                          }
                          className="w-3.5 h-3.5 rounded border-border text-primary focus:ring-primary"
                        />
                        <span className="text-[11px] text-muted-foreground">Active</span>
                      </label>

                      <button
                        onClick={() => {
                          setMediaToEdit(clipping);
                          setMediaModalOpen(true);
                        }}
                        className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg"
                        title="Edit"
                      >
                        <Edit className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => {
                          if (confirm(`Delete press clipping "${clipping.article_title}"?`)) {
                            deleteMediaMutation.mutate(clipping.id);
                          }
                        }}
                        className="p-1.5 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-lg"
                        title="Delete"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          <MediaClippingModal
            isOpen={mediaModalOpen}
            onClose={() => setMediaModalOpen(false)}
            onSave={async (payload) => {
              await saveMediaMutation.mutateAsync(payload);
            }}
            clippingToEdit={mediaToEdit}
            isSaving={saveMediaMutation.isPending}
          />
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────────────────────
          TAB 5: WEBSITE LEADS CRM
         ───────────────────────────────────────────────────────────────────────────── */}
      {activeTab === "leads" && (
        <div className="space-y-5 animate-in fade-in-0 duration-200">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <select
                value={leadTypeFilter}
                onChange={(e) => setLeadTypeFilter(e.target.value)}
                className="text-xs px-3 py-1.5 rounded-xl border border-border bg-card/60 text-foreground font-medium focus:outline-none focus:ring-2 focus:ring-primary/40"
              >
                <option value="all">All Lead Types</option>
                <option value="workshop_booking">Workshop Bookings</option>
                <option value="inquiry">General Inquiries</option>
                <option value="newsletter">Newsletter Signups</option>
              </select>

              <select
                value={leadStatusFilter}
                onChange={(e) => setLeadStatusFilter(e.target.value)}
                className="text-xs px-3 py-1.5 rounded-xl border border-border bg-card/60 text-foreground font-medium focus:outline-none focus:ring-2 focus:ring-primary/40"
              >
                <option value="all">All Statuses</option>
                <option value="new">New Inquiries</option>
                <option value="contacted">Contacted</option>
                <option value="converted">Converted</option>
                <option value="archived">Archived</option>
              </select>
            </div>

            <p className="text-xs text-muted-foreground">
              Total leads recorded: <strong>{leads.length}</strong>
            </p>
          </div>

          {loadingLeads ? (
            <Spinner size="lg" />
          ) : leads.length === 0 ? (
            <EmptyState title="No website leads recorded yet." />
          ) : (
            <div className="rounded-2xl border border-border bg-card/70 overflow-hidden shadow-xs">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-muted/40 border-b border-border text-muted-foreground uppercase text-[10px] tracking-wider font-semibold">
                    <tr>
                      <th className="py-3 px-4">Date</th>
                      <th className="py-3 px-4">Type</th>
                      <th className="py-3 px-4">Contact & Organization</th>
                      <th className="py-3 px-4">Email / Phone</th>
                      <th className="py-3 px-4">Program Interest</th>
                      <th className="py-3 px-4">Status</th>
                      <th className="py-3 px-4 text-right">Details</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {leads.map((lead) => (
                      <tr key={lead.id} className="hover:bg-muted/20 transition-colors">
                        <td className="py-3 px-4 whitespace-nowrap text-muted-foreground text-[11px]">
                          {new Date(lead.created_at).toLocaleDateString()}
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap">
                          <span className="font-bold uppercase tracking-wider text-[10px] text-primary px-2 py-0.5 rounded-md bg-primary/10">
                            {lead.lead_type.replace("_", " ")}
                          </span>
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap">
                          <div className="font-semibold text-foreground">
                            {lead.contact_name || "Newsletter Subscriber"}
                          </div>
                          {lead.organization_name && (
                            <div className="text-[11px] text-muted-foreground">{lead.organization_name}</div>
                          )}
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap">
                          <div className="text-foreground">{lead.email}</div>
                          {lead.phone && (
                            <div className="text-[11px] text-muted-foreground font-mono">{lead.phone}</div>
                          )}
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap text-muted-foreground">
                          {lead.program_interest || "—"}
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap">
                          <select
                            value={lead.status}
                            onChange={(e) =>
                              updateLeadMutation.mutate({
                                id: lead.id,
                                status: e.target.value as WebsiteLeadStatus,
                              })
                            }
                            className={`text-[11px] font-semibold px-2 py-0.5 rounded-lg border border-border bg-background focus:outline-none ${
                              lead.status === "new"
                                ? "text-blue-400"
                                : lead.status === "contacted"
                                ? "text-amber-400"
                                : lead.status === "converted"
                                ? "text-emerald-400"
                                : "text-muted-foreground"
                            }`}
                          >
                            <option value="new">New</option>
                            <option value="contacted">Contacted</option>
                            <option value="converted">Converted</option>
                            <option value="archived">Archived</option>
                          </select>
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap text-right">
                          <Button
                            size="xs"
                            variant="ghost"
                            onClick={() => setSelectedLead(lead)}
                            className="gap-1 text-primary"
                          >
                            <Eye className="w-3 h-3" />
                            View
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <LeadDetailModal
            isOpen={!!selectedLead}
            onClose={() => setSelectedLead(null)}
            lead={selectedLead}
            onStatusChange={async (status) => {
              if (selectedLead) {
                await updateLeadMutation.mutateAsync({ id: selectedLead.id, status });
                setSelectedLead({ ...selectedLead, status });
              }
            }}
            isUpdating={updateLeadMutation.isPending}
          />
        </div>
      )}
    </div>
  );
}

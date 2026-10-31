import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Plus, Trash2, Upload, Image as ImageIcon } from "lucide-react"
import { getErrorMessage } from "@/lib/utils"
import { Spinner } from "@/components/ui/primitives"
import { Modal, ModalActions } from "@/pages/admin/components/common"
import { useToast } from "@/components/ui/toast"
import { uploadWebsiteAsset } from "@/api/websiteConfig"
import { resolveWebsiteAsset } from "./WebsiteManagement"
import {
  getCaseStudiesHeader,
  updateCaseStudiesHeader,
  type CaseStudiesHeaderStatItem,
  type CaseStudiesHeaderPartnerItem,
} from "@/api/websiteCaseStudies"

const inputCls =
  "w-full h-10 rounded-xl border border-border bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none"

interface Props {
  isOpen: boolean
  onClose: () => void
}

export function WebsiteCaseStudiesHeaderModal({ isOpen, onClose }: Props) {
  const queryClient = useQueryClient()
  const toast = useToast()

  const { data: headerData, isLoading } = useQuery({
    queryKey: ["website-case-studies-header"],
    queryFn: getCaseStudiesHeader,
    enabled: isOpen,
  })

  const [stats, setStats] = useState<CaseStudiesHeaderStatItem[]>([])
  const [partners, setPartners] = useState<CaseStudiesHeaderPartnerItem[]>([])
  const [uploadingLogoIdx, setUploadingLogoIdx] = useState<number | null>(null)

  useEffect(() => {
    if (headerData) {
      setStats(headerData.stats || [])
      setPartners(headerData.partners || [])
    }
  }, [headerData])

  const saveMutation = useMutation({
    mutationFn: () =>
      updateCaseStudiesHeader({
        stats: stats.map((s) => ({ value: s.value.trim(), label: s.label.trim() })),
        partners: partners.map((p) => ({
          name: p.name.trim(),
          logo_url: p.logo_url.trim(),
          website_url: p.website_url?.trim() || null,
        })),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["website-case-studies-header"] })
      toast.success("Page header stats and partners saved")
      onClose()
    },
    onError: (err) => {
      toast.error(getErrorMessage(err, "Failed to update header and partners"))
    },
  })

  const handleUploadPartnerLogo = async (idx: number, file?: File | null) => {
    if (!file) return
    setUploadingLogoIdx(idx)
    try {
      const res = await uploadWebsiteAsset(file)
      const copy = [...partners]
      copy[idx] = { ...copy[idx], logo_url: res.url }
      setPartners(copy)
      toast.success("Partner logo uploaded")
    } catch (err) {
      toast.error(getErrorMessage(err, "Logo upload failed"))
    } finally {
      setUploadingLogoIdx(null)
    }
  }

  if (!isOpen) return null

  return (
    <Modal
      title="Case Studies Page Header & Partners"
      onClose={onClose}
      maxWidth="sm:max-w-4xl max-w-4xl"
    >
      <div className="flex flex-col gap-5 pt-1">
        <p className="text-xs text-muted-foreground">
          Configure the hero counter metrics and the &ldquo;TRUSTED BY OUR PARTNERS&rdquo; logo strip
          displayed specifically on the Case Studies marketing page.
        </p>

        {isLoading ? (
          <div className="py-12 flex justify-center">
            <Spinner />
          </div>
        ) : (
          <>
            {/* 1. HERO METRIC COUNTERS */}
            <div className="flex flex-col gap-3 p-4 rounded-2xl border border-border bg-card/60">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-foreground">
                    1. Hero Metric Numbers
                  </h3>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    The 4 summary statistics displayed in the dark hero banner (e.g. 1,000+ Students Trained).
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    setStats([...stats, { value: "", label: "" }])
                  }
                  className="h-8 px-3 rounded-lg bg-primary/10 hover:bg-primary/20 text-primary text-xs font-semibold inline-flex items-center gap-1.5 transition-colors"
                >
                  <Plus size={14} /> Add Metric
                </button>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-1">
                {stats.map((stat, idx) => (
                  <div
                    key={idx}
                    className="flex items-center gap-2.5 p-3 rounded-xl border border-border bg-background"
                  >
                    <div className="w-24 shrink-0">
                      <label className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground block mb-1">
                        Value
                      </label>
                      <input
                        type="text"
                        value={stat.value}
                        onChange={(e) => {
                          const copy = [...stats]
                          copy[idx] = { ...copy[idx], value: e.target.value }
                          setStats(copy)
                        }}
                        placeholder="1,000+"
                        className={inputCls}
                      />
                    </div>
                    <div className="flex-1 min-w-0">
                      <label className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground block mb-1">
                        Metric Label
                      </label>
                      <input
                        type="text"
                        value={stat.label}
                        onChange={(e) => {
                          const copy = [...stats]
                          copy[idx] = { ...copy[idx], label: e.target.value }
                          setStats(copy)
                        }}
                        placeholder="Students Trained"
                        className={inputCls}
                      />
                    </div>
                    <button
                      type="button"
                      onClick={() => setStats(stats.filter((_, i) => i !== idx))}
                      className="h-9 w-9 mt-4 rounded-xl border border-border text-muted-foreground hover:text-destructive hover:border-destructive/40 flex items-center justify-center shrink-0 transition-colors"
                      title="Remove stat"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>

              {stats.length === 0 && (
                <div className="text-center py-4 text-xs text-muted-foreground border border-dashed border-border rounded-xl">
                  No stats configured. Click &ldquo;+ Add Metric&rdquo; above.
                </div>
              )}
            </div>

            {/* 2. TRUSTED BY OUR PARTNERS */}
            <div className="flex flex-col gap-3 p-4 rounded-2xl border border-border bg-card/60">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-foreground">
                    2. Trusted by Our Partners Logos
                  </h3>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Logos appearing in the &ldquo;TRUSTED BY OUR PARTNERS&rdquo; row beneath the hero numbers.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    setPartners([
                      ...partners,
                      { name: "", logo_url: "", website_url: "" },
                    ])
                  }
                  className="h-8 px-3 rounded-lg bg-primary/10 hover:bg-primary/20 text-primary text-xs font-semibold inline-flex items-center gap-1.5 transition-colors"
                >
                  <Plus size={14} /> Add Partner
                </button>
              </div>

              <div className="flex flex-col gap-3 mt-1">
                {partners.map((partner, idx) => (
                  <div
                    key={idx}
                    className="flex flex-col md:flex-row items-start md:items-center gap-3 p-3.5 rounded-xl border border-border bg-background"
                  >
                    {/* Logo Preview */}
                    <div className="w-32 h-20 sm:w-40 sm:h-24 rounded-xl border border-white/10 bg-[#0B0510] flex items-center justify-center p-2.5 shrink-0 overflow-hidden relative shadow-inner">
                      {partner.logo_url ? (
                        <img
                          src={resolveWebsiteAsset(partner.logo_url)}
                          alt={partner.name || "Partner"}
                          className="max-h-16 max-w-full object-contain filter drop-shadow"
                          onError={(e) => {
                            e.currentTarget.style.display = "none"
                          }}
                        />
                      ) : (
                        <ImageIcon size={26} className="text-muted-foreground/50" />
                      )}
                    </div>

                    {/* Inputs */}
                    <div className="flex-1 grid grid-cols-1 sm:grid-cols-2 gap-2.5 w-full">
                      <div>
                        <label className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground block mb-1">
                          Partner Name
                        </label>
                        <input
                          type="text"
                          value={partner.name}
                          onChange={(e) => {
                            const copy = [...partners]
                            copy[idx] = { ...copy[idx], name: e.target.value }
                            setPartners(copy)
                          }}
                          placeholder="Higher Colleges of Technology"
                          className={inputCls}
                        />
                      </div>
                      <div>
                        <label className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground block mb-1">
                          Website URL (Optional)
                        </label>
                        <input
                          type="text"
                          value={partner.website_url || ""}
                          onChange={(e) => {
                            const copy = [...partners]
                            copy[idx] = { ...copy[idx], website_url: e.target.value }
                            setPartners(copy)
                          }}
                          placeholder="https://..."
                          className={inputCls}
                        />
                      </div>
                      <div className="sm:col-span-2">
                        <label className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground block mb-1">
                          Logo URL / Upload
                        </label>
                        <div className="flex items-center gap-2">
                          <input
                            type="text"
                            value={partner.logo_url}
                            onChange={(e) => {
                              const copy = [...partners]
                              copy[idx] = { ...copy[idx], logo_url: e.target.value }
                              setPartners(copy)
                            }}
                            placeholder="/assets/img/Case studies/Logos/..."
                            className={inputCls}
                          />
                          <label className="h-10 px-3.5 rounded-xl border border-border bg-card hover:bg-muted text-xs font-semibold inline-flex items-center gap-1.5 cursor-pointer shrink-0 transition-colors">
                            <Upload size={14} />
                            {uploadingLogoIdx === idx ? "Uploading..." : "Upload"}
                            <input
                              type="file"
                              accept="image/*"
                              className="hidden"
                              onChange={(e) => {
                                handleUploadPartnerLogo(idx, e.target.files?.[0])
                                e.target.value = ""
                              }}
                              disabled={uploadingLogoIdx === idx}
                            />
                          </label>
                        </div>
                      </div>
                    </div>

                    {/* Delete action */}
                    <button
                      type="button"
                      onClick={() =>
                        setPartners(partners.filter((_, i) => i !== idx))
                      }
                      className="h-9 w-9 rounded-xl border border-border text-muted-foreground hover:text-destructive hover:border-destructive/40 flex items-center justify-center shrink-0 transition-colors self-end md:self-center"
                      title="Remove partner"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>

              {partners.length === 0 && (
                <div className="text-center py-4 text-xs text-muted-foreground border border-dashed border-border rounded-xl">
                  No partners configured. Click &ldquo;+ Add Partner&rdquo; above.
                </div>
              )}
            </div>
          </>
        )}

        <ModalActions
          onCancel={onClose}
          onConfirm={() => saveMutation.mutate()}
          loading={saveMutation.isPending}
          disabled={saveMutation.isPending}
          label="Save Changes"
          confirmText="Save Changes"
        />
      </div>
    </Modal>
  )
}

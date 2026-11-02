import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { Star, MessageSquare, Filter, MessageCircle, User, AlertTriangle, Eye, EyeOff, ExternalLink } from "lucide-react"
import { getCourseRatingsApi, updateCourseApi, type CourseRatingsSummary, type CourseRatingDetail } from "@/api/lms_admin"
import { EmojiRating } from "@/components/ui/EmojiRating"
import { Spinner } from "@/components/ui/primitives"
import { UserProfileModal } from "@/components/UserProfileModal"
import { useToast } from "@/components/ui/toast"

const EMOJI_LABELS: Record<number, string> = {
  1: "Terrible",
  2: "Poor",
  3: "Average",
  4: "Great",
  5: "Amazing",
}

const BAR_COLORS: Record<number, string> = {
  5: "bg-emerald-500",
  4: "bg-green-500",
  3: "bg-amber-500",
  2: "bg-orange-500",
  1: "bg-red-500",
}

export function CourseFeedbackPanel({ courseId }: { courseId: string }) {
  const [filter, setFilter] = useState<string>("all")
  const [profileUserId, setProfileUserId] = useState<string | null>(null)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const toast = useToast()

  const { data, isLoading } = useQuery<CourseRatingsSummary>({
    queryKey: ["lms-admin-course-ratings", courseId],
    queryFn: () => getCourseRatingsApi(courseId),
    enabled: Boolean(courseId),
  })

  const visibilityMutation = useMutation({
    mutationFn: (newShowRating: boolean) => updateCourseApi(courseId, { show_rating: newShowRating }),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ["lms-admin-course-ratings", courseId] })
      queryClient.invalidateQueries({ queryKey: ["lms-admin-course", courseId] })
      queryClient.invalidateQueries({ queryKey: ["lms-admin-courses"] })
      toast.success(updated.show_rating ? "Course rating is now visible to students" : "Course rating is now hidden from students")
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail ?? "Failed to update rating visibility")
    },
  })

  if (isLoading) {
    return (
      <div className="p-8 bg-card border border-border rounded-2xl flex items-center justify-center">
        <Spinner />
      </div>
    )
  }

  const total = data?.total_count || 0
  const avg = data?.average_rating ?? null
  const distribution = data?.distribution || { "1": 0, "2": 0, "3": 0, "4": 0, "5": 0 }
  const ratings = data?.ratings || []
  const isRatingVisible = data?.show_rating ?? true
  const isAutoHidden = data?.rating_auto_hidden ?? false

  const withReviewsCount = ratings.filter((r) => Boolean(r.review_text?.trim())).length
  const positiveCount = (distribution["5"] || 0) + (distribution["4"] || 0)
  const positivePct = total > 0 ? Math.round((positiveCount / total) * 100) : 0

  // Filtered ratings
  const filteredRatings = ratings.filter((r) => {
    if (filter === "all") return true
    if (filter === "with_reviews") return Boolean(r.review_text?.trim())
    return String(r.rating) === filter
  })

  return (
    <div className="flex flex-col gap-5 p-4 sm:p-6 bg-card border border-border rounded-2xl max-w-full overflow-hidden">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="size-10 rounded-xl bg-amber-500/10 text-amber-500 flex items-center justify-center shrink-0">
            <Star className="size-5 fill-amber-500" />
          </div>
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-foreground truncate">Course Feedback & Ratings</h2>
            <p className="text-xs text-muted-foreground truncate">
              Real sentiment and reviews submitted by enrolled students
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap shrink-0">
          {/* Rating Visibility Controls */}
          <button
            type="button"
            onClick={() => visibilityMutation.mutate(!isRatingVisible)}
            disabled={visibilityMutation.isPending}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium border transition-colors cursor-pointer disabled:opacity-50 ${
              isRatingVisible
                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-500/20"
                : "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400 hover:bg-amber-500/20"
            }`}
            title={isRatingVisible ? "Hide course rating from student views" : "Show course rating to students"}
          >
            {isRatingVisible ? <Eye className="size-3.5" /> : <EyeOff className="size-3.5" />}
            <span>{isRatingVisible ? "Rating Visible to Students" : "Rating Hidden from Students"}</span>
          </button>

          {total > 0 && (
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-primary/10 text-primary whitespace-nowrap">
                {total} {total === 1 ? "Rating" : "Ratings"}
              </span>
              {withReviewsCount > 0 && (
                <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-muted text-muted-foreground hidden sm:flex items-center gap-1 whitespace-nowrap">
                  <MessageSquare className="size-3" /> {withReviewsCount}
                </span>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Auto-hidden Low Rating Banner */}
      {(!isRatingVisible || isAutoHidden) && (
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-700 dark:text-amber-300 text-xs">
          <div className="flex items-start sm:items-center gap-2 min-w-0">
            <AlertTriangle className="size-4 shrink-0 text-amber-500 mt-0.5 sm:mt-0" />
            <span>
              {isAutoHidden
                ? "Course rating was automatically hidden from student pages because overall rating fell below 4.0. An alert email was sent to admins."
                : "Course rating is currently hidden from student landing pages and catalog."}
            </span>
          </div>
          <button
            type="button"
            onClick={() => visibilityMutation.mutate(true)}
            disabled={visibilityMutation.isPending}
            className="px-3 py-1.5 rounded-lg bg-amber-500 text-white font-medium hover:bg-amber-600 transition-colors shrink-0 text-xs cursor-pointer disabled:opacity-50 self-start sm:self-auto"
          >
            Show Rating to Students
          </button>
        </div>
      )}

      {total === 0 ? (
        <div className="py-8 text-center flex flex-col items-center justify-center gap-2 text-muted-foreground border border-dashed border-border rounded-xl">
          <MessageCircle className="size-8 opacity-40 text-muted-foreground" />
          <p className="text-sm font-medium text-foreground">No student ratings yet</p>
          <p className="text-xs max-w-sm text-muted-foreground px-4">
            Once students complete this course and rate it, their reviews and sentiment scores will appear here.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-6">
          {/* Top Score & Distribution Summary */}
          <div className="grid grid-cols-1 md:grid-cols-[180px_1fr] gap-5 p-4 rounded-xl bg-muted/20 border border-border/80">
            {/* Left: Overall Score Card */}
            <div className="flex flex-col items-center justify-center text-center p-2 border-b md:border-b-0 md:border-r border-border/80 pr-0 md:pr-4">
              <div className="font-['Outfit'] text-4xl sm:text-5xl font-extrabold text-foreground tracking-tight">
                {avg !== null ? avg.toFixed(1) : "—"}
              </div>
              <div className="text-xs text-muted-foreground mt-1 mb-2">out of 5.0</div>
              <EmojiRating value={avg ? Math.round(avg) : 5} readOnly size="sm" />
              <p className="text-xs text-muted-foreground font-medium mt-3">
                {positivePct}% positive reviews (4-5 ★)
              </p>
            </div>

            {/* Right: Distribution Bars */}
            <div className="flex flex-col justify-center gap-2 min-w-0">
              {[5, 4, 3, 2, 1].map((level) => {
                const count = distribution[String(level)] || 0
                const pct = total > 0 ? Math.round((count / total) * 100) : 0
                return (
                  <button
                    key={level}
                    type="button"
                    onClick={() => setFilter(filter === String(level) ? "all" : String(level))}
                    className={`flex items-center gap-2 text-xs text-muted-foreground group hover:text-foreground transition-colors p-1 rounded-md text-left w-full min-w-0 ${
                      filter === String(level) ? "bg-muted/60 font-semibold text-foreground" : ""
                    }`}
                  >
                    <span className="w-12 sm:w-20 shrink-0 flex items-center gap-1 font-medium truncate">
                      <span>{level} ★</span>
                      <span className="text-[10px] text-muted-foreground/80 font-normal hidden sm:inline">
                        ({EMOJI_LABELS[level]})
                      </span>
                    </span>

                    <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden relative min-w-[50px]">
                      <div
                        className={`h-full rounded-full transition-all duration-300 ${BAR_COLORS[level]}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>

                    <span className="w-12 text-right tabular-nums text-muted-foreground shrink-0 text-[11px]">
                      {count} ({pct}%)
                    </span>
                  </button>
                )
              })}
            </div>
          </div>

          {/* Filters */}
          <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap text-xs">
            <span className="text-muted-foreground flex items-center gap-1 font-medium mr-1 shrink-0">
              <Filter className="size-3" /> Filter:
            </span>
            <button
              onClick={() => setFilter("all")}
              className={`px-3 py-1.5 rounded-lg font-medium transition-colors cursor-pointer ${
                filter === "all"
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted hover:bg-muted/80 text-foreground"
              }`}
            >
              All ({total})
            </button>
            {withReviewsCount > 0 && (
              <button
                onClick={() => setFilter("with_reviews")}
                className={`px-3 py-1.5 rounded-lg font-medium transition-colors cursor-pointer ${
                  filter === "with_reviews"
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted hover:bg-muted/80 text-foreground"
                }`}
              >
                Comments ({withReviewsCount})
              </button>
            )}
            {[5, 4, 3, 2, 1].map((level) => {
              const c = distribution[String(level)] || 0
              if (c === 0) return null
              return (
                <button
                  key={level}
                  onClick={() => setFilter(String(level))}
                  className={`px-2.5 py-1.5 rounded-lg font-medium transition-colors cursor-pointer ${
                    filter === String(level)
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted hover:bg-muted/80 text-foreground"
                  }`}
                >
                  {level} ★ ({c})
                </button>
              )
            })}
          </div>

          {/* Reviews List */}
          {filteredRatings.length === 0 ? (
            <div className="py-6 text-center text-xs text-muted-foreground border border-dashed border-border rounded-xl">
              No ratings match this filter.
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {filteredRatings.map((review) => (
                <ReviewItem
                  key={review.id}
                  review={review}
                  onOpenProfile={(uid) => setProfileUserId(uid)}
                  onManageStudent={(uid) => void navigate({ to: `/lms-authoring/students/${uid}` })}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {profileUserId && (
        <UserProfileModal
          userId={profileUserId}
          onClose={() => setProfileUserId(null)}
        />
      )}
    </div>
  )
}

function ReviewItem({
  review,
  onOpenProfile,
  onManageStudent,
}: {
  review: CourseRatingDetail
  onOpenProfile: (userId: string) => void
  onManageStudent: (userId: string) => void
}) {
  const dateStr = review.updated_at
    ? new Date(review.updated_at).toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      })
    : ""

  return (
    <div className="p-4 rounded-xl bg-card border border-border flex flex-col gap-3 min-w-0 overflow-hidden">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
        {/* User Info with Profile & Manage links */}
        <div className="flex items-center gap-2.5 min-w-0">
          <button
            type="button"
            onClick={() => onOpenProfile(review.user_id)}
            className="shrink-0 cursor-pointer hover:opacity-80 transition-opacity"
            title="View student profile"
          >
            {review.student_photo_url ? (
              <img
                src={review.student_photo_url}
                alt=""
                className="size-9 rounded-full object-cover ring-1 ring-border shrink-0"
              />
            ) : (
              <div className="size-9 rounded-full bg-primary/10 text-primary flex items-center justify-center font-bold text-xs shrink-0">
                {review.student_name ? review.student_name.slice(0, 2).toUpperCase() : <User className="size-4" />}
              </div>
            )}
          </button>

          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5 flex-wrap">
              <button
                type="button"
                onClick={() => onOpenProfile(review.user_id)}
                className="text-xs font-semibold text-foreground hover:text-primary transition-colors cursor-pointer text-left truncate max-w-[180px] sm:max-w-xs"
                title="Open student profile"
              >
                {review.student_name}
              </button>
              {review.student_email && (
                <span className="text-[11px] text-muted-foreground truncate hidden sm:inline">
                  · {review.student_email}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
              {dateStr && <span>{dateStr}</span>}
              <button
                type="button"
                onClick={() => onManageStudent(review.user_id)}
                className="text-primary hover:underline flex items-center gap-0.5 cursor-pointer font-medium"
                title="Open student manage & enrollment details page"
              >
                <span>Manage student</span>
                <ExternalLink className="size-2.5" />
              </button>
            </div>
          </div>
        </div>

        {/* Rating Stars + Badge */}
        <div className="flex items-center gap-2 self-start sm:self-auto shrink-0 pl-11 sm:pl-0">
          <div className="flex items-center gap-0.5" aria-label={`Rating: ${review.rating} out of 5 stars`}>
            {[1, 2, 3, 4, 5].map((star) => (
              <Star
                key={star}
                className={`size-3.5 ${
                  star <= review.rating
                    ? "fill-amber-400 text-amber-400"
                    : "text-muted-foreground/30 fill-transparent"
                }`}
              />
            ))}
          </div>
          <span className="text-xs font-semibold px-2 py-0.5 rounded-md bg-muted text-foreground">
            {review.rating}/5
          </span>
        </div>
      </div>

      {/* Review Text */}
      {review.review_text?.trim() ? (
        <div className="p-3 rounded-lg bg-muted/30 border border-border/60 text-xs text-foreground/90 leading-relaxed font-sans break-words whitespace-pre-wrap">
          "{review.review_text.trim()}"
        </div>
      ) : (
        <span className="text-[11px] text-muted-foreground/70 italic pl-1">
          Rated {review.rating}/5 without written feedback
        </span>
      )}
    </div>
  )
}

import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Star, MessageSquare, Filter, MessageCircle, User } from "lucide-react"
import { getCourseRatingsApi, type CourseRatingsSummary, type CourseRatingDetail } from "@/api/lms_admin"
import { EmojiRating } from "@/components/ui/EmojiRating"
import { Spinner } from "@/components/ui/primitives"

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

  const { data, isLoading } = useQuery<CourseRatingsSummary>({
    queryKey: ["lms-admin-course-ratings", courseId],
    queryFn: () => getCourseRatingsApi(courseId),
    enabled: Boolean(courseId),
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
    <div className="flex flex-col gap-5 p-6 bg-card border border-border rounded-2xl">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <div className="size-10 rounded-xl bg-amber-500/10 text-amber-500 flex items-center justify-center shrink-0">
            <Star className="size-5 fill-amber-500" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-foreground">Course Feedback & Ratings</h2>
            <p className="text-xs text-muted-foreground">
              Real sentiment and reviews submitted by enrolled students
            </p>
          </div>
        </div>

        {total > 0 && (
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-primary/10 text-primary">
              {total} {total === 1 ? "Rating" : "Ratings"}
            </span>
            {withReviewsCount > 0 && (
              <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-muted text-muted-foreground flex items-center gap-1">
                <MessageSquare className="size-3" /> {withReviewsCount} {withReviewsCount === 1 ? "Review" : "Reviews"}
              </span>
            )}
          </div>
        )}
      </div>

      {total === 0 ? (
        <div className="py-8 text-center flex flex-col items-center justify-center gap-2 text-muted-foreground border border-dashed border-border rounded-xl">
          <MessageCircle className="size-8 opacity-40 text-muted-foreground" />
          <p className="text-sm font-medium text-foreground">No student ratings yet</p>
          <p className="text-xs max-w-sm text-muted-foreground">
            Once enrolled students finish lessons and rate this course using the emojis, their reviews and sentiment scores will appear here.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-6">
          {/* Top Score & Distribution Summary */}
          <div className="grid grid-cols-1 md:grid-cols-[220px_1fr] gap-6 p-4 rounded-xl bg-muted/20 border border-border/80">
            {/* Left: Overall Score Card */}
            <div className="flex flex-col items-center justify-center text-center p-3 border-b md:border-b-0 md:border-r border-border/80 pr-0 md:pr-6">
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
            <div className="flex flex-col justify-center gap-2">
              {[5, 4, 3, 2, 1].map((level) => {
                const count = distribution[String(level)] || 0
                const pct = total > 0 ? Math.round((count / total) * 100) : 0
                return (
                  <button
                    key={level}
                    type="button"
                    onClick={() => setFilter(filter === String(level) ? "all" : String(level))}
                    className={`flex items-center gap-2 text-xs text-muted-foreground group hover:text-foreground transition-colors p-1 rounded-md text-left ${
                      filter === String(level) ? "bg-muted/60 font-semibold text-foreground" : ""
                    }`}
                  >
                    <span className="w-14 shrink-0 flex items-center gap-1 font-medium">
                      <span>{level} ★</span>
                      <span className="text-[10px] text-muted-foreground/80 font-normal">
                        ({EMOJI_LABELS[level]})
                      </span>
                    </span>

                    <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden relative">
                      <div
                        className={`h-full rounded-full transition-all duration-300 ${BAR_COLORS[level]}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>

                    <span className="w-10 text-right tabular-nums text-muted-foreground shrink-0 text-[11px]">
                      {count} ({pct}%)
                    </span>
                  </button>
                )
              })}
            </div>
          </div>

          {/* Filters */}
          <div className="flex items-center gap-2 flex-wrap text-xs">
            <span className="text-muted-foreground flex items-center gap-1 font-medium mr-1">
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
                With written comments ({withReviewsCount})
              </button>
            )}
            {[5, 4, 3, 2, 1].map((level) => {
              const c = distribution[String(level)] || 0
              if (c === 0) return null
              return (
                <button
                  key={level}
                  onClick={() => setFilter(String(level))}
                  className={`px-3 py-1.5 rounded-lg font-medium transition-colors cursor-pointer ${
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
                <ReviewItem key={review.id} review={review} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ReviewItem({ review }: { review: CourseRatingDetail }) {
  const dateStr = review.updated_at
    ? new Date(review.updated_at).toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      })
    : ""

  return (
    <div className="p-4 rounded-xl bg-card border border-border flex flex-col gap-2.5">
      <div className="flex items-start justify-between gap-3">
        {/* User Info */}
        <div className="flex items-center gap-2.5 min-w-0">
          {review.student_photo_url ? (
            <img
              src={review.student_photo_url}
              alt=""
              className="size-8 rounded-full object-cover ring-1 ring-border shrink-0"
            />
          ) : (
            <div className="size-8 rounded-full bg-primary/10 text-primary flex items-center justify-center font-bold text-xs shrink-0">
              {review.student_name ? review.student_name.slice(0, 2).toUpperCase() : <User className="size-4" />}
            </div>
          )}

          <div className="min-w-0">
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-xs font-semibold text-foreground truncate">
                {review.student_name}
              </span>
              {review.student_email && (
                <span className="text-[11px] text-muted-foreground truncate hidden sm:inline">
                  · {review.student_email}
                </span>
              )}
            </div>
            {dateStr && <span className="text-[11px] text-muted-foreground">{dateStr}</span>}
          </div>
        </div>

        {/* Rating Emoji + Star Badge */}
        <div className="flex items-center gap-2 shrink-0">
          <EmojiRating value={review.rating} readOnly size="sm" />
          <span className="text-xs font-semibold px-2 py-0.5 rounded-md bg-muted text-foreground">
            {review.rating}/5
          </span>
        </div>
      </div>

      {/* Review Text */}
      {review.review_text?.trim() ? (
        <div className="mt-1 p-3 rounded-lg bg-muted/30 border border-border/60 text-xs text-foreground/90 leading-relaxed font-sans">
          "{review.review_text.trim()}"
        </div>
      ) : (
        <span className="text-[11px] text-muted-foreground/70 italic">
          Rated {review.rating}/5 without written feedback
        </span>
      )}
    </div>
  )
}

import { useEffect, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { BookOpen, Globe, Layers, Search, Star, X } from "lucide-react";
import { fetchBooks, fetchPublicBooks } from "@/api/lms_books";
import { useAuth } from "@/context/AuthContext";
import { BookCover } from "@/components/lms/BookCover";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

function formatPrice(cents: number, currency: string): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency.toUpperCase(),
  }).format(cents / 100);
}

export default function LearnBooks() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const isAuthed = !!user;

  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");

  useEffect(() => {
    const id = setTimeout(() => setSearch(searchInput), 250);
    return () => clearTimeout(id);
  }, [searchInput]);

  const { data: books = [], isLoading } = useQuery({
    queryKey: [isAuthed ? "lms-books" : "lms-public-books", search],
    queryFn: () => (isAuthed ? fetchBooks(search || undefined) : fetchPublicBooks(search || undefined)),
  });

  return (
    <div className="mx-auto max-w-[1280px] px-5 sm:px-8 lg:px-12 py-8 sm:py-10 flex flex-col gap-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <h1 className="font-display text-3xl sm:text-4xl font-bold tracking-tight">Books</h1>
        <div className="relative w-full sm:w-80">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground pointer-events-none" />
          <input
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search books..."
            className="w-full h-10 pl-9 pr-9 border border-border bg-card text-foreground rounded-[10px] text-sm focus:outline-none focus:border-primary transition-colors"
          />
          {searchInput && (
            <button
              type="button"
              onClick={() => setSearchInput("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground cursor-pointer"
              aria-label="Clear search"
            >
              <X className="size-4" />
            </button>
          )}
        </div>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : books.length === 0 ? (
        <Card className="p-10 text-center rounded-[10px] border border-border">
          <BookOpen className="size-8 mx-auto text-muted-foreground mb-3" />
          <p className="text-base font-semibold text-foreground">
            {search ? `No books match "${search}".` : "No books published yet."}
          </p>
        </Card>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
          {books.map((book) => {
            const isPaid = book.access_mode === "paid" && book.price_cents != null && book.price_cents > 0;
            const cardKey = `${book.id}:${book.edition_id ?? book.item_id ?? (book.allowed_chapters?.join(",") || "full")}`;
            const detailSearch =
              book.edition_id || book.item_id
                ? {
                    ...(book.edition_id ? { editionId: book.edition_id } : {}),
                    ...(book.item_id ? { itemId: book.item_id } : {}),
                  }
                : undefined;
            return (
              <Card
                key={cardKey}
                onClick={() => void navigate({ to: `/learn/books/${book.id}`, search: detailSearch as never })}
                className="group cursor-pointer rounded-[10px] border border-border bg-card overflow-hidden flex flex-col hover:border-primary transition-colors p-0"
              >
                <div className="aspect-[3/4] w-full bg-muted overflow-hidden border-b border-border">
                  <BookCover
                    title={book.title}
                    coverUrl={book.cover_url}
                    coverPageUrl={book.cover_page_url}
                    chapterCount={book.chapter_count}
                    languages={book.languages}
                  />
                </div>

                <div className="p-4 flex flex-col gap-3 flex-1 justify-between">
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      {book.enrolled ? (
                        <span className="text-xs font-semibold px-2.5 py-1 rounded-[10px] bg-[#DCFCE7] text-[#15803D] dark:bg-green-950 dark:text-green-300">
                          Enrolled
                        </span>
                      ) : book.is_preview ? (
                        <span className="text-xs font-semibold px-2.5 py-1 rounded-[10px] bg-primary/10 text-primary">
                          Staff Preview
                        </span>
                      ) : isPaid ? (
                        <span className="text-xs font-semibold px-2.5 py-1 rounded-[10px] bg-primary/10 text-primary">
                          {formatPrice(book.price_cents!, book.currency)}
                        </span>
                      ) : book.access_mode === "invite" ? (
                        <span className="text-xs font-semibold px-2.5 py-1 rounded-[10px] bg-muted text-muted-foreground">
                          Program Access
                        </span>
                      ) : (
                        <span className="text-xs font-semibold px-2.5 py-1 rounded-[10px] bg-[#DCFCE7] text-[#15803D] dark:bg-green-950 dark:text-green-300">
                          Free
                        </span>
                      )}
                    </div>

                    <h2 className="font-display text-lg font-bold leading-snug text-foreground">
                      {book.title}
                    </h2>

                    <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground pt-0.5">
                      <span className="inline-flex items-center gap-1">
                        <Layers className="size-3.5 text-primary" />
                        {book.chapter_count} chapters
                      </span>
                      <span className="inline-flex items-center gap-1 uppercase">
                        <Globe className="size-3.5 text-primary" />
                        {book.languages.join(" / ")}
                      </span>
                      {book.enrolled && book.stars_earned > 0 && (
                        <span className="inline-flex items-center gap-1 text-primary font-medium">
                          <Star className="size-3.5 fill-primary" />
                          {book.stars_earned}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="space-y-3 pt-1">
                    {book.enrolled && book.completion_pct > 0 && (
                      <div className="space-y-1">
                        <div className="flex justify-between text-xs text-muted-foreground">
                          <span>Progress</span>
                          <span className="font-semibold text-foreground">{book.completion_pct}%</span>
                        </div>
                        <div className="h-2 w-full rounded-[10px] bg-muted overflow-hidden">
                          <div
                            className="h-full bg-primary rounded-[10px]"
                            style={{ width: `${Math.min(100, book.completion_pct)}%` }}
                          />
                        </div>
                      </div>
                    )}

                    <Button
                      type="button"
                      variant={book.enrolled ? "default" : "outline"}
                      className="w-full rounded-[10px]"
                      onClick={(e) => {
                        e.stopPropagation();
                        void navigate({
                          to: `/learn/books/${book.id}`,
                          search: detailSearch as never,
                        });
                      }}
                    >
                      {book.enrolled && book.completion_pct > 0 ? "Continue reading" : "More info"}
                    </Button>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

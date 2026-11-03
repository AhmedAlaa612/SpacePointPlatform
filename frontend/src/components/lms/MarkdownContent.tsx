import { useMemo } from "react";
import { marked } from "marked";
import { cn } from "@/lib/utils";

// Configure marked with github-flavored markdown & line breaks
marked.setOptions({
  gfm: true,
  breaks: true,
});

interface MarkdownContentProps {
  content: string;
  className?: string;
}

export function MarkdownContent({ content, className }: MarkdownContentProps) {
  const html = useMemo(() => {
    if (!content || !content.trim()) return "";
    try {
      // Parse markdown to HTML
      let parsed = marked.parse(content) as string;

      // Wrap tables in responsive container for mobile scroll
      parsed = parsed.replace(
        /<table([^>]*)>/gi,
        '<div class="w-full overflow-x-auto my-4 rounded-xl border border-border/60 shadow-xs"><table class="w-full text-left text-sm border-collapse" $1>'
      );
      parsed = parsed.replace(/<\/table>/gi, '</table></div>');

      return parsed;
    } catch (e) {
      console.error("Markdown parse error:", e);
      return content;
    }
  }, [content]);

  if (!content) return null;

  return (
    <div
      className={cn(
        "spacepoint-markdown max-w-full break-words leading-relaxed text-foreground/90 text-sm sm:text-base",
        "[&_h1]:text-2xl sm:[&_h1]:text-3xl [&_h1]:font-bold [&_h1]:tracking-tight [&_h1]:text-foreground [&_h1]:mb-4 [&_h1]:mt-6 [&_h1]:first:mt-0",
        "[&_h2]:text-xl sm:[&_h2]:text-2xl [&_h2]:font-bold [&_h2]:tracking-tight [&_h2]:text-foreground [&_h2]:mb-3 [&_h2]:mt-6 [&_h2]:pb-2 [&_h2]:border-b [&_h2]:border-border/40",
        "[&_h3]:text-lg sm:[&_h3]:text-xl [&_h3]:font-semibold [&_h3]:text-foreground [&_h3]:mb-2 [&_h3]:mt-5",
        "[&_h4]:text-base sm:[&_h4]:text-lg [&_h4]:font-semibold [&_h4]:text-purple-400 [&_h4]:mb-2 [&_h4]:mt-4",
        "[&_p]:mb-4 [&_p]:leading-relaxed last:[&_p]:mb-0",
        "[&_strong]:font-semibold [&_strong]:text-foreground",
        "[&_em]:italic [&_em]:text-foreground/80",
        "[&_ul]:list-disc [&_ul]:pl-5 sm:[&_ul]:pl-6 [&_ul]:mb-4 [&_ul]:space-y-1.5",
        "[&_ol]:list-decimal [&_ol]:pl-5 sm:[&_ol]:pl-6 [&_ol]:mb-4 [&_ol]:space-y-1.5",
        "[&_li]:leading-relaxed",
        "[&_blockquote]:border-l-4 [&_blockquote]:border-purple-500/80 [&_blockquote]:bg-purple-950/20 [&_blockquote]:px-4 [&_blockquote]:py-2.5 [&_blockquote]:rounded-r-xl [&_blockquote]:my-4 [&_blockquote]:italic [&_blockquote]:text-foreground/90",
        "[&_pre]:bg-[#101218] [&_pre]:text-emerald-400 [&_pre]:p-4 [&_pre]:rounded-xl [&_pre]:overflow-x-auto [&_pre]:text-xs sm:[&_pre]:text-sm [&_pre]:font-mono [&_pre]:border [&_pre]:border-border/60 [&_pre]:my-4 [&_pre]:max-w-full",
        "[&_code]:font-mono [&_code]:text-xs sm:[&_code]:text-sm [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:rounded-md [&_code]:bg-muted/80 [&_code]:text-purple-300 [&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_pre_code]:text-emerald-400",
        "[&_img]:rounded-xl [&_img]:border [&_img]:border-border/60 [&_img]:max-w-full [&_img]:h-auto [&_img]:my-4 [&_img]:shadow-md [&_img]:mx-auto [&_img]:block",
        "[&_table]:w-full [&_table]:border-collapse",
        "[&_th]:bg-muted/70 [&_th]:text-foreground [&_th]:font-semibold [&_th]:px-3 sm:[&_th]:px-4 [&_th]:py-2.5 [&_th]:text-xs sm:[&_th]:text-sm [&_th]:border-b [&_th]:border-border",
        "[&_td]:px-3 sm:[&_td]:px-4 [&_td]:py-2.5 [&_td]:text-xs sm:[&_td]:text-sm [&_td]:border-b [&_td]:border-border/40",
        "[&_tr:last-child_td]:border-b-0",
        "[&_a]:text-primary [&_a]:underline [&_a]:underline-offset-4 [&_a]:font-medium hover:[&_a]:text-primary/80",
        "[&_hr]:my-6 [&_hr]:border-border/50",
        className
      )}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

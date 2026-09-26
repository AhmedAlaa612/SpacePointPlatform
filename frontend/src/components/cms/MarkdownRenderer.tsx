import React from "react";

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

/**
 * Clean, safe client-side Markdown previewer with syntax highlighting styles,
 * typography support, and responsive layouts.
 */
export const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({ content, className = "" }) => {
  if (!content) {
    return <p className="text-muted-foreground italic text-sm">No content to preview.</p>;
  }

  // Parse lines into structured blocks
  const lines = content.split("\n");
  const elements: React.ReactNode[] = [];
  let inCodeBlock = false;
  let codeBuffer: string[] = [];
  let codeLang = "";
  let inList = false;
  let listItems: string[] = [];

  const flushList = () => {
    if (inList && listItems.length > 0) {
      elements.push(
        <ul key={`list-${elements.length}`} className="list-disc list-inside space-y-1 my-3 text-muted-foreground">
          {listItems.map((item, idx) => (
            <li key={idx} className="leading-relaxed">
              {renderInline(item)}
            </li>
          ))}
        </ul>
      );
      listItems = [];
      inList = false;
    }
  };

  const renderInline = (text: string): React.ReactNode => {
    // Basic inline formatting: bold, italic, inline code, links
    const parts: React.ReactNode[] = [];
    let keyIdx = 0;

    // Pattern for inline code, links, bold, italic
    const regex = /(\*\*.*?\*\*|\*.*?\*|`.*?`|\[.*?\]\(.*?\))/g;
    let match;
    let lastIndex = 0;

    while ((match = regex.exec(text)) !== null) {
      if (match.index > lastIndex) {
        parts.push(text.substring(lastIndex, match.index));
      }
      const token = match[0];
      if (token.startsWith("**") && token.endsWith("**")) {
        parts.push(
          <strong key={keyIdx++} className="font-semibold text-foreground">
            {token.slice(2, -2)}
          </strong>
        );
      } else if (token.startsWith("*") && token.endsWith("*")) {
        parts.push(
          <em key={keyIdx++} className="italic text-foreground/90">
            {token.slice(1, -1)}
          </em>
        );
      } else if (token.startsWith("`") && token.endsWith("`")) {
        parts.push(
          <code
            key={keyIdx++}
            className="px-1.5 py-0.5 rounded bg-muted/60 text-primary font-mono text-xs border border-border/50"
          >
            {token.slice(1, -1)}
          </code>
        );
      } else if (token.startsWith("[") && token.includes("](")) {
        const titleMatch = token.match(/\[(.*?)\]/);
        const urlMatch = token.match(/\((.*?)\)/);
        if (titleMatch && urlMatch) {
          parts.push(
            <a
              key={keyIdx++}
              href={urlMatch[1]}
              target="_blank"
              rel="noreferrer"
              className="text-primary hover:underline font-medium"
            >
              {titleMatch[1]}
            </a>
          );
        } else {
          parts.push(token);
        }
      }
      lastIndex = regex.lastIndex;
    }

    if (lastIndex < text.length) {
      parts.push(text.substring(lastIndex));
    }

    return parts.length > 0 ? parts : text;
  };

  lines.forEach((line, index) => {
    const trimmed = line.trim();

    // Code blocks
    if (trimmed.startsWith("```")) {
      flushList();
      if (!inCodeBlock) {
        inCodeBlock = true;
        codeLang = trimmed.slice(3).trim();
        codeBuffer = [];
      } else {
        inCodeBlock = false;
        elements.push(
          <div key={`code-${elements.length}`} className="my-4 rounded-xl bg-card border border-border overflow-hidden">
            {codeLang && (
              <div className="bg-muted/40 px-3 py-1 text-[11px] font-mono uppercase tracking-wider text-muted-foreground border-b border-border">
                {codeLang}
              </div>
            )}
            <pre className="p-4 text-xs font-mono overflow-x-auto text-foreground/90">
              <code>{codeBuffer.join("\n")}</code>
            </pre>
          </div>
        );
        codeBuffer = [];
      }
      return;
    }

    if (inCodeBlock) {
      codeBuffer.push(line);
      return;
    }

    // Unordered lists
    if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
      inList = true;
      listItems.push(trimmed.slice(2));
      return;
    } else {
      flushList();
    }

    // Headings
    if (trimmed.startsWith("# ")) {
      elements.push(
        <h1 key={`h1-${index}`} className="text-2xl font-bold font-display tracking-tight text-foreground mt-6 mb-3">
          {renderInline(trimmed.slice(2))}
        </h1>
      );
      return;
    }
    if (trimmed.startsWith("## ")) {
      elements.push(
        <h2 key={`h2-${index}`} className="text-xl font-bold font-display text-foreground mt-5 mb-2.5">
          {renderInline(trimmed.slice(3))}
        </h2>
      );
      return;
    }
    if (trimmed.startsWith("### ")) {
      elements.push(
        <h3 key={`h3-${index}`} className="text-lg font-semibold text-foreground mt-4 mb-2">
          {renderInline(trimmed.slice(4))}
        </h3>
      );
      return;
    }

    // Blockquote
    if (trimmed.startsWith("> ")) {
      elements.push(
        <blockquote
          key={`quote-${index}`}
          className="border-l-4 border-primary/60 pl-4 py-1 my-3 italic text-muted-foreground bg-primary/5 rounded-r"
        >
          {renderInline(trimmed.slice(2))}
        </blockquote>
      );
      return;
    }

    // Horizontal Rule
    if (trimmed === "---" || trimmed === "***") {
      elements.push(<hr key={`hr-${index}`} className="my-6 border-border" />);
      return;
    }

    // Blank lines
    if (trimmed === "") {
      return;
    }

    // Normal paragraph
    elements.push(
      <p key={`p-${index}`} className="my-2 text-sm leading-relaxed text-foreground/80">
        {renderInline(line)}
      </p>
    );
  });

  flushList();

  return <div className={`space-y-1 text-foreground ${className}`}>{elements}</div>;
};

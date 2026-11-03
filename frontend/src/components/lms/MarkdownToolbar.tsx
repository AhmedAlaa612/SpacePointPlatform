import {
  Bold, Italic, Heading2, Heading3, Code, Image as ImageIcon, Table as TableIcon, Quote, Link as LinkIcon, List,
} from "lucide-react";

interface MarkdownToolbarProps {
  onInsert: (prefix: string, suffix?: string, placeholder?: string) => void;
}

export function MarkdownToolbar({ onInsert }: MarkdownToolbarProps) {
  return (
    <div className="flex flex-wrap items-center gap-1 p-1.5 bg-muted/40 border border-border rounded-lg text-muted-foreground">
      <button
        type="button"
        title="Bold (**text**)"
        onClick={() => onInsert("**", "**", "bold text")}
        className="p-1.5 hover:bg-muted hover:text-foreground rounded transition-colors"
      >
        <Bold size={14} />
      </button>

      <button
        type="button"
        title="Italic (*text*)"
        onClick={() => onInsert("*", "*", "italic text")}
        className="p-1.5 hover:bg-muted hover:text-foreground rounded transition-colors"
      >
        <Italic size={14} />
      </button>

      <div className="h-4 w-px bg-border mx-0.5" />

      <button
        type="button"
        title="Heading 2 (## Heading)"
        onClick={() => onInsert("## ", "\n", "Heading 2")}
        className="p-1.5 hover:bg-muted hover:text-foreground rounded transition-colors text-xs font-bold"
      >
        <Heading2 size={14} />
      </button>

      <button
        type="button"
        title="Heading 3 (### Heading)"
        onClick={() => onInsert("### ", "\n", "Heading 3")}
        className="p-1.5 hover:bg-muted hover:text-foreground rounded transition-colors text-xs font-bold"
      >
        <Heading3 size={14} />
      </button>

      <div className="h-4 w-px bg-border mx-0.5" />

      <button
        type="button"
        title="Code Block (```cpp)"
        onClick={() => onInsert("```cpp\n", "\n```\n", "// Enter C++ code here")}
        className="p-1.5 hover:bg-muted hover:text-foreground rounded transition-colors"
      >
        <Code size={14} />
      </button>

      <button
        type="button"
        title="Bulleted List"
        onClick={() => onInsert("- ", "\n", "List item")}
        className="p-1.5 hover:bg-muted hover:text-foreground rounded transition-colors"
      >
        <List size={14} />
      </button>

      <button
        type="button"
        title="Callout Note (> **Note:** ...)"
        onClick={() => onInsert("> **Flight Note:** ", "\n", "Critical hardware explanation.")}
        className="p-1.5 hover:bg-muted hover:text-foreground rounded transition-colors"
      >
        <Quote size={14} />
      </button>

      <button
        type="button"
        title="Table"
        onClick={() =>
          onInsert(
            "\n| Pin / Signal | Description | Hex Address |\n| :--- | :--- | :--- |\n| ADD0 -> GND | Base Address | `0x48` |\n| ADD0 -> V+ | SpacePoint Flight Bus | `0x49` |\n",
            ""
          )
        }
        className="p-1.5 hover:bg-muted hover:text-foreground rounded transition-colors"
      >
        <TableIcon size={14} />
      </button>

      <div className="h-4 w-px bg-border mx-0.5" />

      <button
        type="button"
        title="Insert Image (![alt](url))"
        onClick={() => onInsert("![Diagram Description](", ")", "https://blog.seeedstudio.com/wp-content/uploads/2019/11/image-158.png")}
        className="p-1.5 hover:bg-muted hover:text-foreground rounded transition-colors"
      >
        <ImageIcon size={14} />
      </button>

      <button
        type="button"
        title="Link ([text](url))"
        onClick={() => onInsert("[", "](https://...)", "Link text")}
        className="p-1.5 hover:bg-muted hover:text-foreground rounded transition-colors"
      >
        <LinkIcon size={14} />
      </button>
    </div>
  );
}

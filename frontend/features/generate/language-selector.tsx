"use client";
import { cn } from "@/lib/utils";

const LANGUAGES = [
  { id: "python", label: "Python" },
  { id: "typescript", label: "TypeScript" },
  { id: "java", label: "Java" },
] as const;

type Language = typeof LANGUAGES[number]["id"];

interface Props {
  selected: Language;
  onSelect: (lang: Language) => void;
}

export function LanguageSelector({ selected, onSelect }: Props) {
  return (
    <div className="flex gap-1.5">
      {LANGUAGES.map((lang) => (
        <button
          key={lang.id}
          onClick={() => onSelect(lang.id)}
          className={cn(
            "px-3 py-1.5 rounded-md text-xs font-mono font-medium border transition-all duration-150",
            selected === lang.id
              ? "bg-ink text-canvas border-ink"
              : "bg-canvas text-ink-3 border-border-2 hover:border-border-3 hover:text-ink"
          )}
        >
          {lang.label}
        </button>
      ))}
    </div>
  );
}

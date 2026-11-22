import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** Landing-section heading: small eyebrow, title, supporting copy.
 * `level="h1"` when the heading is the page's main title (exactly one
 * h1 per page — SEO/accessibility); otherwise h2. */
export function SectionHeading({
  eyebrow,
  title,
  description,
  align = "center",
  level = "h2",
  className,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  align?: "center" | "left";
  level?: "h1" | "h2";
  className?: string;
}) {
  const Heading = level === "h1" ? "h1" : "h2";
  return (
    <div
      className={cn(
        "max-w-2xl",
        align === "center" ? "mx-auto text-center" : "text-left",
        className,
      )}
    >
      {eyebrow ? (
        <p className="text-sm font-bold uppercase tracking-widest text-brand-600">{eyebrow}</p>
      ) : null}
      <Heading className="mt-2 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">{title}</Heading>
      {description ? (
        <p className="mt-3 text-base leading-relaxed text-slate-600">{description}</p>
      ) : null}
    </div>
  );
}

export type { ReactNode };

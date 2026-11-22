import { cn } from "@/lib/utils";

/**
 * Decorative Pakistan map watermark — a simplified inline SVG outline.
 * aria-hidden, very low contrast, positioned behind content only in
 * brand/landing sections. It must never sit over body text and never
 * reduce readability. The outline is intentionally simplified; it is a
 * decorative mark, not a cartographic document.
 */
export function PakistanMapWatermark({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 100 100"
      fill="none"
      className={cn("pointer-events-none absolute select-none", className)}
    >
      <path
        d="M56 3 L44 5 L34 8 L28 12 L24 18 L20 26 L16 32 L12 40 L9 48 L7 56 L9 64 L14 72 L18 80 L26 86 L36 89 L46 88 L56 86 L64 80 L70 72 L76 62 L82 52 L88 42 L92 32 L90 22 L84 14 L76 8 L66 4 Z"
        fill="currentColor"
      />
    </svg>
  );
}

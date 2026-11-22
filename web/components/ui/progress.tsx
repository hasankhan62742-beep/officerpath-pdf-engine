import { cn } from "@/lib/utils";

/** Determinate progress bar (0–100). Label is announced to assistive tech. */
export function Progress({
  value,
  label,
  tone = "brand",
  className,
}: {
  value: number;
  label?: string;
  tone?: "brand" | "success" | "info" | "accent";
  className?: string;
}) {
  const clamped = Math.max(0, Math.min(100, value));
  const bar =
    tone === "success"
      ? "bg-success-600"
      : tone === "info"
        ? "bg-info-600"
        : tone === "accent"
          ? "bg-accent-600"
          : "bg-brand-600";
  return (
    <div className={cn("w-full", className)}>
      <div
        role="progressbar"
        aria-valuenow={clamped}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label ?? "Progress"}
        className="h-2.5 w-full overflow-hidden rounded-full bg-slate-200"
      >
        <div
          className={cn("h-full rounded-full transition-[width] duration-300", bar)}
          style={{ width: `${clamped}%` }}
        />
      </div>
      {label ? (
        <p className="mt-1.5 text-xs font-medium text-slate-600">
          {label} — {clamped}%
        </p>
      ) : null}
    </div>
  );
}

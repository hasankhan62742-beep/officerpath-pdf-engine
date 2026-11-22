import { cn } from "@/lib/utils";

/** Indeterminate loading spinner (CSS only). */
export function Spinner({ className }: { className?: string }) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={cn(
        "inline-block size-5 animate-spin rounded-full border-2 border-slate-300 border-t-brand-600",
        className,
      )}
    />
  );
}

/** Full-area loading state with an accessible label. */
export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      <Spinner className="size-8" />
      <p className="text-sm font-medium text-slate-600">{label}</p>
    </div>
  );
}

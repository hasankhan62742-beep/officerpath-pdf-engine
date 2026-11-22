import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";

/** Empty state: what is missing, what to do next, and the action that does it. */
export function EmptyState({
  title,
  description,
  actionLabel,
  actionHref,
  onAction,
}: {
  title: string;
  description: string;
  actionLabel?: string;
  actionHref?: string;
  onAction?: () => void;
}) {
  return (
    <div className="flex flex-col items-center rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-6 py-12 text-center">
      <div
        aria-hidden
        className="mb-4 flex size-12 items-center justify-center rounded-full bg-brand-100 text-xl font-bold text-brand-700"
      >
        ○
      </div>
      <h3 className="text-base font-semibold text-slate-900">{title}</h3>
      <p className="mt-1 max-w-md text-sm leading-relaxed text-slate-600">{description}</p>
      {actionLabel ? (
        <Button href={actionHref} onClick={onAction} className="mt-5" size="md">
          {actionLabel}
        </Button>
      ) : null}
    </div>
  );
}

/** Error state with a retry action. */
export function ErrorState({
  title = "Something went wrong",
  description = "Please try again. If the problem continues, contact support.",
  onRetry,
}: {
  title?: string;
  description?: string;
  onRetry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center rounded-2xl border border-danger-100 bg-danger-50 px-6 py-12 text-center"
    >
      <div
        aria-hidden
        className="mb-4 flex size-12 items-center justify-center rounded-full bg-danger-100 text-xl font-bold text-danger-700"
      >
        !
      </div>
      <h3 className="text-base font-semibold text-slate-900">{title}</h3>
      <p className="mt-1 max-w-md text-sm leading-relaxed text-slate-600">{description}</p>
      {onRetry ? (
        <Button variant="secondary" onClick={onRetry} className="mt-5">
          Try again
        </Button>
      ) : null}
    </div>
  );
}

export type { ReactNode };

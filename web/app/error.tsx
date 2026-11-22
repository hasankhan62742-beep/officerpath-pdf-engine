"use client";

import { Button } from "@/components/ui/button";

/** Route error boundary. `reset` retries rendering the failed segment. */
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center px-4 py-24 text-center sm:px-6">
      <h1 className="text-2xl font-bold text-slate-900">Something went wrong</h1>
      <p className="mt-2 text-base leading-relaxed text-slate-600">
        This page could not be loaded. Please try again — if the problem
        continues, contact support.
      </p>
      {error?.digest ? (
        <p className="mt-3 text-xs text-slate-400">Error reference: {error.digest}</p>
      ) : null}
      <div className="mt-6 flex flex-col gap-3 sm:flex-row">
        <Button onClick={reset}>Try again</Button>
        <Button href="/" variant="secondary">
          Go to home page
        </Button>
      </div>
    </div>
  );
}

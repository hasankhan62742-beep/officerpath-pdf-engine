// OfficerPath AI — result route (Phase 2, M8).
//
// Same Next 16 pattern as the exam route: the test id is a
// dynamic param, so the client view renders inside a Suspense
// boundary (Cache Components rule).

import { Suspense } from "react";
import { Spinner } from "@/components/ui/spinner";
import { ResultClient } from "@/components/dashboard/result-client";

export const instant = false;

export default async function TestResultPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <Suspense
      fallback={
        <div className="flex items-center gap-2 py-16 text-slate-600">
          <Spinner /> Loading your result…
        </div>
      }
    >
      <ResultClient id={id} />
    </Suspense>
  );
}

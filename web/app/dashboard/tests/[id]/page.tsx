// OfficerPath AI — test detail route (Phase 2, M6).
//
// Same Next 16 pattern as the question detail route: the test
// id is a dynamic param, so the client view renders inside a
// Suspense boundary (Cache Components rule).

import { Suspense } from "react";
import { Spinner } from "@/components/ui/spinner";
import { TestDetailClient } from "@/components/dashboard/test-detail-client";

export const instant = false;

export default async function TestDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <Suspense
      fallback={
        <div className="flex items-center gap-2 py-16 text-slate-600">
          <Spinner /> Loading the test…
        </div>
      }
    >
      <TestDetailClient id={id} />
    </Suspense>
  );
}

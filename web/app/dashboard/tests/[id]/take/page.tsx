// OfficerPath AI — exam route (Phase 2, M7).
//
// Same Next 16 pattern as the test detail route: the test id is
// a dynamic param, so the client view renders inside a Suspense
// boundary (Cache Components rule).

import { Suspense } from "react";
import { Spinner } from "@/components/ui/spinner";
import { ExamClient } from "@/components/dashboard/exam-client";

export const instant = false;

export default async function TakeTestPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <Suspense
      fallback={
        <div className="flex items-center gap-2 py-16 text-slate-600">
          <Spinner /> Loading the exam…
        </div>
      }
    >
      <ExamClient id={id} />
    </Suspense>
  );
}

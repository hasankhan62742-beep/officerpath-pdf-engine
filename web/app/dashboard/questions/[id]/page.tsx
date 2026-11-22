// OfficerPath AI — question detail route (Phase 2, M5).
//
// Same Next 16 pattern as the document detail route: the
// question id is a dynamic param, so the client view renders
// inside a Suspense boundary (Cache Components rule).

import { Suspense } from "react";
import { Spinner } from "@/components/ui/spinner";
import { QuestionDetailClient } from "@/components/dashboard/question-detail-client";

export const instant = false;

export default async function QuestionDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <Suspense
      fallback={
        <div className="flex items-center gap-2 py-16 text-slate-600">
          <Spinner /> Loading the question…
        </div>
      }
    >
      <QuestionDetailClient id={id} />
    </Suspense>
  );
}

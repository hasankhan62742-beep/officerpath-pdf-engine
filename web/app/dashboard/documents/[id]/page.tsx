// OfficerPath AI — document detail route (Phase 2, M4).
//
// Server wrapper: the document id is a dynamic param, not known
// until request time, so the client detail view (which reads it
// with useParams-equivalent data) renders inside a Suspense
// boundary — the fallback streams during prerendering (Next 16
// Cache Components rule for useParams on dynamic routes).

import { Suspense } from "react";
import { Spinner } from "@/components/ui/spinner";
import { DocumentDetailClient } from "@/components/dashboard/document-detail-client";

// This route is allowed to block: the document id is a dynamic
// param and the shared header reads the pathname, so the route
// has no static shell to validate. `instant = false` opts this
// route (and only this route) out of the static-shell check —
// the page still streams behind its Suspense fallback.
export const instant = false;

export default async function DocumentDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <Suspense
      fallback={
        <div className="flex items-center gap-2 py-16 text-slate-600">
          <Spinner /> Loading the document…
        </div>
      }
    >
      <DocumentDetailClient id={id} />
    </Suspense>
  );
}

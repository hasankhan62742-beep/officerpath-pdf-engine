// OfficerPath AI — one named study collection (B1/B2).
//
// Server wrapper: the slug is a dynamic param, not known until
// request time, so the client detail view renders inside a
// Suspense boundary — the fallback streams during prerendering
// (Next 16 Cache Components rule for useParams on dynamic routes).

import { Suspense } from "react";
import { Spinner } from "@/components/ui/spinner";
import { CollectionDetailClient } from "@/components/collections/collection-detail-client";

// This route is allowed to block: the slug is a dynamic param
// and the shared header reads the pathname, so the route has no
// static shell to validate. `instant = false` opts this route
// (and only this route) out of the static-shell check — the page
// still streams behind its Suspense fallback.
export const instant = false;

export default async function CollectionDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  return (
    <div className="mx-auto max-w-7xl px-4 py-14 sm:px-6 lg:px-8">
      <Suspense
        fallback={
          <div className="flex items-center gap-2 py-16 text-slate-600">
            <Spinner /> Loading the collection…
          </div>
        }
      >
        <CollectionDetailClient slug={slug} />
      </Suspense>
    </div>
  );
}

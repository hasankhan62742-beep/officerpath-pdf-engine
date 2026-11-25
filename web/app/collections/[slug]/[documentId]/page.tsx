// OfficerPath AI — read one collection document (B1/B2).
//
// Server wrapper: the slug and document id are dynamic params,
// not known until request time, so the client read view renders
// inside a Suspense boundary — the fallback streams during
// prerendering (Next 16 Cache Components rule for useParams on
// dynamic routes).

import { Suspense } from "react";
import { Spinner } from "@/components/ui/spinner";
import { CollectionReadClient } from "@/components/collections/collection-read-client";

// This route is allowed to block: the params are dynamic and
// the shared header reads the pathname, so the route has no
// static shell to validate. `instant = false` opts this route
// (and only this route) out of the static-shell check — the page
// still streams behind its Suspense fallback.
export const instant = false;

export default async function CollectionReadPage({
  params,
}: {
  params: Promise<{ slug: string; documentId: string }>;
}) {
  const { slug, documentId } = await params;
  return (
    <div className="mx-auto max-w-7xl px-4 py-14 sm:px-6 lg:px-8">
      <Suspense
        fallback={
          <div className="flex items-center gap-2 py-16 text-slate-600">
            <Spinner /> Loading the paper…
          </div>
        }
      >
        <CollectionReadClient key={documentId} slug={slug} documentId={documentId} />
      </Suspense>
    </div>
  );
}

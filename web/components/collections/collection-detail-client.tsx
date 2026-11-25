// OfficerPath AI — one named study collection (B1/B2).
//
// Public: the collection's papers/documents with titles and
// counts. Reading a document's questions needs a login — the
// read page enforces that (user decision #1).
//
// Public page: no React Query here (providers live in the
// dashboard/admin layouts only, M10) — plain fetch on mount.

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Alert } from "@/components/ui/alert";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { SectionHeading } from "@/components/ui/section-heading";
import { Spinner } from "@/components/ui/spinner";
import {
  collectionBlurb,
  CollectionDocumentRow,
} from "@/components/landing/collections-section";
import { ApiError, getStudyCollection, type StudyCollection } from "@/lib/api";

export function CollectionDetailClient({ slug }: { slug: string }) {
  const [collection, setCollection] = useState<StudyCollection | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getStudyCollection(slug)
      .then((res) => {
        if (!cancelled) setCollection(res);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) setNotFound(true);
        else setError(err instanceof Error ? err.message : "The collection did not load.");
      });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  if (notFound) {
    return (
      <EmptyState
        title="Collection not found"
        description="That collection does not exist, or its name changed. See all collections instead."
      />
    );
  }

  if (error) {
    return (
      <ErrorState
        title="Could not load the collection"
        description={error}
        onRetry={() => window.location.reload()}
      />
    );
  }

  if (!collection) {
    return (
      <div className="flex items-center gap-2 py-16 text-slate-600">
        <Spinner /> Loading the collection…
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <Link href="/collections" className="text-sm font-medium text-brand-700 hover:underline">
          ← All collections
        </Link>
        <div className="mt-2">
          <SectionHeading
            title={collection.name}
            description={collectionBlurb(collection.name)}
            level="h1"
            align="left"
          />
        </div>
        <p className="mt-3 text-sm text-slate-600">
          {collection.question_count.toLocaleString("en-US")} question
          {collection.question_count === 1 ? "" : "s"} in {collection.document_count}{" "}
          document{collection.document_count === 1 ? "" : "s"} ·{" "}
          <Link href="/login" className="font-medium text-brand-700 hover:underline">
            Sign in
          </Link>{" "}
          to read them.
        </p>
      </div>

      {collection.documents.length === 0 ? (
        <EmptyState
          title="No documents yet"
          description="This collection has no documents. The next import will appear here."
        />
      ) : (
        <ul className="space-y-4">
          {collection.documents.map((doc) => (
            <CollectionDocumentRow key={doc.id} collection={collection} doc={doc} />
          ))}
        </ul>
      )}

      <Alert tone="info" title="Reading needs a free account">
        Opening a paper&apos;s questions requires a login — the list above is
        public, the questions are not.
      </Alert>
    </div>
  );
}

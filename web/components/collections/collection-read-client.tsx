// OfficerPath AI — read one collection document (B1/B2).
//
// Login-gated reading mode (user decision #1): the list of
// papers is public, but opening a paper's questions requires a
// signed-in account. MCQs render with all four options and the
// correct one marked; Q+A cards (no options, answer in
// ``explanation``) render as Q+A cards (decision #4) — the
// shared ReadingCard handles both shapes.
//
// Reading mode: a warm paper background with a readable font —
// neither too small nor too big — per the user's reading-mode
// design instruction.
//
// Public page: no React Query here (providers live in the
// dashboard/admin layouts only, M10) — plain fetch on mount.

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { Pagination } from "@/components/ui/pagination";
import { SectionHeading } from "@/components/ui/section-heading";
import { Spinner } from "@/components/ui/spinner";
import { ReadingCard } from "@/components/dashboard/reading-card";
import {
  ApiError,
  getSessionToken,
  getStudyCollection,
  listStudyCollectionDocumentQuestions,
  type DocumentQuestionsResponse,
  type StudyCollection,
} from "@/lib/api";

const PAGE_SIZE = 10;

export function CollectionReadClient({
  slug,
  documentId,
}: {
  slug: string;
  documentId: string;
}) {
  const [collection, setCollection] = useState<StudyCollection | null>(null);
  const [collectionError, setCollectionError] = useState<string | null>(null);
  const [token, setToken] = useState<string | null | undefined>(undefined);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<DocumentQuestionsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getStudyCollection(slug)
      .then((res) => {
        if (!cancelled) setCollection(res);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setCollectionError(
            err instanceof Error ? err.message : "The collection did not load.",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  useEffect(() => {
    let cancelled = false;
    getSessionToken().then((t) => {
      if (!cancelled) setToken(t);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const doc = collection?.documents.find((d) => d.id === documentId) ?? null;

  // A fetch is in flight when the shown data is missing or stale
  // for the requested page — derived from the data, not a state
  // the effect would have to set synchronously
  // (react-hooks/set-state-in-effect). While a new page loads,
  // the previous page stays visible.
  const fetching =
    token !== null &&
    token !== undefined &&
    doc !== null &&
    error === null &&
    (data === null || data.offset !== (page - 1) * PAGE_SIZE);
  // When the requested page changes, a previous fetch error no
  // longer applies — cleared during render, the React pattern for
  // resetting state on a value change.
  const fetchKey = `${token ?? ""}|${slug}|${documentId}|${page}`;
  const [prevFetchKey, setPrevFetchKey] = useState(fetchKey);
  if (prevFetchKey !== fetchKey) {
    setPrevFetchKey(fetchKey);
    setError(null);
  }

  useEffect(() => {
    if (token == null || !doc) return;
    let cancelled = false;
    listStudyCollectionDocumentQuestions(token, slug, documentId, {
      limit: PAGE_SIZE,
      offset: (page - 1) * PAGE_SIZE,
    })
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          setError("This paper is not part of that collection.");
        } else {
          setError(err instanceof Error ? err.message : "The questions did not load.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [token, slug, documentId, page, doc?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (collectionError) {
    return (
      <ErrorState
        title="Could not load the collection"
        description={collectionError}
        onRetry={() => window.location.reload()}
      />
    );
  }

  if (!collection) {
    return (
      <div className="flex items-center gap-2 py-16 text-slate-600">
        <Spinner /> Loading the paper…
      </div>
    );
  }

  if (!doc) {
    return (
      <EmptyState
        title="Paper not found"
        description="That paper is not part of this collection. See the collection instead."
      />
    );
  }

  const next = `/collections/${slug}/${documentId}`;

  return (
    <div className="space-y-8">
      <div>
        <Link
          href={`/collections/${slug}`}
          className="text-sm font-medium text-brand-700 hover:underline"
        >
          ← {collection.name}
        </Link>
        <div className="mt-2">
          <SectionHeading
            title={doc.title}
            description={`${collection.name} · ${doc.question_count.toLocaleString("en-US")} questions`}
            level="h1"
            align="left"
          />
        </div>
      </div>

      {token === undefined ? (
        <div className="flex items-center gap-2 py-8 text-slate-600">
          <Spinner /> Checking your session…
        </div>
      ) : token === null ? (
        <Card className="p-6">
          <CardTitle>Sign in to read the questions</CardTitle>
          <CardDescription>
            Opening a paper&apos;s questions needs a free account — the list is
            public, the questions are not. Your documents and results stay
            private to you.
          </CardDescription>
          <div className="mt-5 flex flex-col gap-3 sm:flex-row">
            <Button href={`/login?next=${next}`}>Sign in</Button>
            <Button href="/register" variant="secondary">
              Create a free account
            </Button>
          </div>
        </Card>
      ) : fetching && !data ? (
        <div className="flex items-center gap-2 py-8 text-slate-600">
          <Spinner /> Loading the questions…
        </div>
      ) : error || !data ? (
        <ErrorState
          title="Could not load the questions"
          description={error ?? "The engine did not answer. Check that it is running and try again."}
          onRetry={() => window.location.reload()}
        />
      ) : data.total === 0 ? (
        <EmptyState
          title="No questions yet"
          description="This paper has no stored questions. The next import will appear here."
        />
      ) : (
        <>
          <dl className="grid grid-cols-2 gap-4 text-center sm:grid-cols-4">
            <div className="rounded-xl bg-white px-2 py-3 ring-1 ring-slate-200">
              <dt className="text-xs font-medium text-slate-500">Questions</dt>
              <dd className="text-2xl font-bold text-slate-900">{data.counts.questions ?? 0}</dd>
            </div>
            <div className="rounded-xl bg-white px-2 py-3 ring-1 ring-slate-200">
              <dt className="text-xs font-medium text-slate-500">Answered</dt>
              <dd className="text-2xl font-bold text-slate-900">{data.counts.answered ?? 0}</dd>
            </div>
            <div className="rounded-xl bg-white px-2 py-3 ring-1 ring-slate-200">
              <dt className="text-xs font-medium text-slate-500">Unknown</dt>
              <dd className="text-2xl font-bold text-slate-900">{data.counts.unknown ?? 0}</dd>
            </div>
            <div className="rounded-xl bg-white px-2 py-3 ring-1 ring-slate-200">
              <dt className="text-xs font-medium text-slate-500">Q&amp;A cards</dt>
              <dd className="text-2xl font-bold text-slate-900">{data.qa_pairs ?? 0}</dd>
            </div>
          </dl>

          {data.qa_pairs > 0 ? (
            <Alert tone="info" title={`Q&A cards: ${data.qa_pairs}`}>
              This paper also contains {data.qa_pairs} question-and-answer
              {data.qa_pairs === 1 ? "" : "s"} (answers without options). They
              are shown below as Q&amp;A cards — never forced into four options.
            </Alert>
          ) : null}

          {/* Reading mode: warm paper background, readable type. */}
          <div className="rounded-3xl bg-gradient-to-b from-amber-50 via-orange-50/60 to-white px-3 py-6 ring-1 ring-amber-100 sm:px-6 sm:py-8">
            <div className="space-y-4">
              {data.questions.map((q, i) => (
                <ReadingCard
                  key={q.question_id}
                  q={q}
                  position={(page - 1) * PAGE_SIZE + i + 1}
                />
              ))}
            </div>
            <p className="mt-6 text-sm text-slate-600">
              Showing {(page - 1) * PAGE_SIZE + 1}–
              {Math.min(page * PAGE_SIZE, data.total)} of{" "}
              {data.total.toLocaleString("en-US")} questions.
            </p>
            <div className="mt-3">
              <Pagination
                page={page}
                totalPages={Math.max(1, Math.ceil(data.total / PAGE_SIZE))}
                onPageChange={setPage}
              />
            </div>
          </div>
        </>
      )}
    </div>
  );
}

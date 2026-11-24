// OfficerPath AI — mistake notebook (Phase 2, M8, GAP-8).
//
// Real list from GET /api/v1/collections?collection_type=mistake:
// every question this student answered incorrectly in a submitted
// test, written by the submit flow itself. Notes are editable,
// each entry can be bookmarked, and "Practice mistakes" builds a
// new test from the ORIGINAL snapshots of those attempts — never
// from the live bank — so a later bank correction cannot change
// the practice test.

"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { Pagination } from "@/components/ui/pagination";
import { SectionHeading } from "@/components/ui/section-heading";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import {
  ApiError,
  createCollection,
  createTestFromMistakes,
  deleteCollection,
  getSessionToken,
  listCollections,
  updateCollectionNote,
  type CollectionItem,
} from "@/lib/api";
import { formatMathText } from "@/lib/mathText";
import { formatDateTime } from "@/lib/utils";

const PAGE_SIZE = 20;

function MistakeCard({
  item,
  bookmarkId,
  onNoteSaved,
  onRemoved,
}: {
  item: CollectionItem;
  bookmarkId: string | null;
  onNoteSaved: () => void;
  onRemoved: () => void;
}) {
  const queryClient = useQueryClient();
  const [note, setNote] = useState(item.note ?? "");
  const [noteError, setNoteError] = useState("");
  const [actionError, setActionError] = useState("");
  const [busy, setBusy] = useState(false);

  async function run(fn: (token: string) => Promise<unknown>, after: () => void) {
    setActionError("");
    setBusy(true);
    try {
      const token = await getSessionToken();
      if (!token) throw new Error("You need to sign in.");
      await fn(token);
      await queryClient.invalidateQueries({ queryKey: ["collections"] });
      after();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  const q = item.question;
  return (
    <Card>
      
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="danger">Mistake</Badge>
          {bookmarkId ? <Badge tone="info">Bookmarked</Badge> : null}
          <span className="text-xs text-slate-500">
            Added {formatDateTime(item.created_at)}
            {q ? ` · from ${q.document_title}` : ""}
          </span>
        </div>
        {q ? (
          <>
            <p className="mt-2 whitespace-pre-wrap text-slate-800">{formatMathText(q.text)}</p>
            {q.options.length > 0 ? (
              <ul className="mt-3 space-y-1">
                {q.options.map((text, idx) => {
                  const isCorrect = idx === q.correct_index;
                  return (
                    <li
                      key={idx}
                      className={
                        isCorrect
                          ? "rounded-md bg-success-50 px-3 py-1.5 text-sm text-success-900 ring-1 ring-success-200"
                          : "rounded-md bg-slate-50 px-3 py-1.5 text-sm text-slate-700"
                      }
                    >
                      <span className="font-semibold">{String.fromCharCode(65 + idx)}. </span>
                      {formatMathText(text)}
                      {isCorrect ? " — stored answer" : ""}
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="mt-3 text-sm text-slate-600">
                This question has no options (Q&amp;A pair).
              </p>
            )}
            {q.correct_index === -1 ? (
              <p className="mt-3 text-sm text-info-800">
                Answer unknown — the stored answer was never verified.
              </p>
            ) : null}
            {q.explanation ? (
              <div className="mt-3 rounded-md bg-info-50 px-3 py-2 ring-1 ring-info-200">
                <p className="text-xs font-semibold text-info-800">Explanation</p>
                <p className="mt-1 whitespace-pre-wrap text-sm text-info-900">{formatMathText(q.explanation)}</p>
              </div>
            ) : (
              <p className="mt-3 text-sm text-slate-600">
                No explanation was stored for this question.
              </p>
            )}
          </>
        ) : (
          <p className="mt-2 text-sm text-slate-600">
            The question behind this entry is no longer available.
          </p>
        )}

        <div className="mt-4 space-y-2">
          <Textarea
            label="Your note"
            id={`note-${item.id}`}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Why did you get this wrong? Write a reminder for next time."
            rows={2}
          />
          {noteError ? (
            <Alert tone="danger" title="Could not save the note">
              {noteError}
            </Alert>
          ) : null}
          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              size="sm"
              disabled={busy || note === (item.note ?? "")}
              onClick={() => {
                setNoteError("");
                void run(
                  (token) => updateCollectionNote(token, item.id, note.trim() || null),
                  onNoteSaved,
                );
              }}
            >
              Save note
            </Button>
            <Button
              variant="secondary"
              size="sm"
              disabled={busy}
              onClick={() => {
                void run(
                  async (token) => {
                    if (bookmarkId) {
                      await deleteCollection(token, bookmarkId);
                    } else {
                      await createCollection(token, {
                        question_id: item.question_id,
                        collection_type: "bookmark",
                      });
                    }
                  },
                  () => undefined,
                );
              }}
            >
              {bookmarkId ? "Remove bookmark" : "Bookmark"}
            </Button>
            <Button
              variant="danger"
              size="sm"
              disabled={busy}
              onClick={() => {
                void run((token) => deleteCollection(token, item.id), onRemoved);
              }}
            >
              Remove from notebook
            </Button>
          </div>
          {actionError ? (
            <Alert tone="danger" title="Action failed">
              {actionError}
            </Alert>
          ) : null}
        </div>
      
    </Card>
  );
}

export default function MistakesPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [practiceError, setPracticeError] = useState("");

  const mistakesQuery = useQuery({
    queryKey: ["collections", "mistake", page],
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new Error("You need to sign in to view your notebook.");
      return listCollections(token, {
        collection_type: "mistake",
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
      });
    },
  });

  const bookmarksQuery = useQuery({
    queryKey: ["collections", "bookmark", "all"],
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new Error("You need to sign in to view your notebook.");
      return listCollections(token, { collection_type: "bookmark", limit: 200, offset: 0 });
    },
  });

  const practiceMutation = useMutation({
    mutationFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new Error("You need to sign in to practice your mistakes.");
      return createTestFromMistakes(token, { name: "Mistake practice" });
    },
    onSuccess: (test) => {
      void queryClient.invalidateQueries({ queryKey: ["tests"] });
      router.push(`/dashboard/tests/${test.test_id}`);
    },
    onError: (err) => {
      setPracticeError(
        err instanceof ApiError ? err.message : "Could not start a practice test.",
      );
    },
  });

  if (mistakesQuery.isPending || bookmarksQuery.isPending) {
    return (
      <div className="flex items-center gap-2 py-16 text-slate-600">
        <Spinner /> Loading your mistake notebook…
      </div>
    );
  }

  if (mistakesQuery.isError) {
    return (
      <ErrorState
        title="Could not load your notebook"
        description={
          mistakesQuery.error instanceof Error
            ? mistakesQuery.error.message
            : "Something went wrong."
        }
        onRetry={() => void mistakesQuery.refetch()}
      />
    );
  }

  const { collections, total } = mistakesQuery.data;
  const bookmarkByQuestion = new Map(
    (bookmarksQuery.data?.collections ?? []).map((b) => [b.question_id, b.id]),
  );

  return (
    <div className="space-y-6">
      <SectionHeading
        title="Mistake notebook"
        description="Every question you answered incorrectly in a submitted test. Practice them again — the practice test uses the exact questions you saw, even if the bank was corrected since."
      />

      {practiceError ? (
        <Alert tone="danger" title="Could not start a practice test">
          {practiceError}
        </Alert>
      ) : null}

      <div>
        <Button
          loading={practiceMutation.isPending}
          disabled={collections.length === 0}
          title={collections.length === 0 ? "No mistakes to practice yet." : undefined}
          onClick={() => {
            setPracticeError("");
            practiceMutation.mutate();
          }}
        >
          Practice mistakes
        </Button>
        <p className="mt-2 text-sm text-slate-600">
          Creates a new test from your {total} mistake
          {total === 1 ? "" : "s"} — the newest attempt of each question.
        </p>
      </div>

      {collections.length === 0 ? (
        <EmptyState
          title="No mistakes yet"
          description="Questions you answer incorrectly in submitted tests will appear here automatically."
        />
      ) : (
        collections.map((item) => (
          <MistakeCard
            key={item.id}
            item={item}
            bookmarkId={bookmarkByQuestion.get(item.question_id) ?? null}
            onNoteSaved={() => undefined}
            onRemoved={() => undefined}
          />
        ))
      )}

      <Pagination
        page={page}
        totalPages={Math.max(1, Math.ceil(total / PAGE_SIZE))}
        onPageChange={setPage}
      />
      <Card>
        
          <CardTitle>Your bookmarks</CardTitle>
          <p className="mt-2 text-sm text-slate-600">
            You have {bookmarksQuery.data?.total ?? 0} bookmarked question
            {(bookmarksQuery.data?.total ?? 0) === 1 ? "" : "s"}. Bookmarks are
            managed from the question review on any result page.
          </p>
        
      </Card>
    </div>
  );
}

// OfficerPath AI — result detail page (Phase 2, M8, GAP-7).
//
// Every number on this page comes from the stored test_results row
// (GET /api/v1/tests/{id}/result): score, counts, breakdowns and
// the per-question review. The frontend never computes marks or
// trends. Review shows only what the engine stored — snapshot
// text/options + the selected answer + evidence labels. No
// explanations are invented: there is no explanation field
// anywhere, because the engine never stored one. Unknown
// snapshots (correct_index = -1) are shown as unknown, never as
// correct or incorrect.

"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { SectionHeading } from "@/components/ui/section-heading";
import { Spinner } from "@/components/ui/spinner";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "@/components/ui/table";
import {
  ApiError,
  createCollection,
  deleteCollection,
  getTestResultDetail,
  getSessionToken,
  retryTest,
  type BreakdownItem,
  type ReviewItem,
} from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return s === 0 ? `${m} min` : `${m} min ${s}s`;
}

function statusTone(
  status: ReviewItem["status"],
): "success" | "danger" | "neutral" | "info" {
  switch (status) {
    case "correct":
      return "success";
    case "incorrect":
      return "danger";
    case "unknown":
      return "info";
    default:
      return "neutral";
  }
}

function statusLabel(status: ReviewItem["status"]): string {
  switch (status) {
    case "correct":
      return "Correct";
    case "incorrect":
      return "Incorrect";
    case "unknown":
      return "Unknown answer";
    default:
      return "Unattempted";
  }
}

function optionLetter(index: number): string {
  return String.fromCharCode(65 + index);
}

function BreakdownTable({
  title,
  items,
}: {
  title: string;
  items: BreakdownItem[] | null;
}) {
  if (!items || items.length === 0) {
    return (
      <p className="text-sm text-slate-600">
        No {title.toLowerCase()} breakdown — none of this test&apos;s
        questions carry a {title.toLowerCase() === "subject breakdown" ? "subject" : "topic"} assignment.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHead>
          <TableRow>
            <TableHeaderCell>{title === "Subject breakdown" ? "Subject" : "Topic"}</TableHeaderCell>
            <TableHeaderCell>Scored</TableHeaderCell>
            <TableHeaderCell>Correct</TableHeaderCell>
            <TableHeaderCell>Incorrect</TableHeaderCell>
            <TableHeaderCell>Unattempted</TableHeaderCell>
            <TableHeaderCell>Marks</TableHeaderCell>
            <TableHeaderCell>Accuracy</TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {items.map((b) => (
            <TableRow key={b.key}>
              <TableCell>{b.name}</TableCell>
              <TableCell>{b.scored}</TableCell>
              <TableCell>{b.correct}</TableCell>
              <TableCell>{b.incorrect}</TableCell>
              <TableCell>{b.unattempted}</TableCell>
              <TableCell>
                {b.marks} / {b.max_marks}
              </TableCell>
              <TableCell>{b.accuracy === null ? "—" : `${b.accuracy}%`}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export function ResultClient({ id }: { id: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [retryError, setRetryError] = useState("");
  const [bookmarkError, setBookmarkError] = useState("");
  const [busyBookmark, setBusyBookmark] = useState<string | null>(null);

  const detailQuery = useQuery({
    queryKey: ["test-result-detail", id],
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new Error("You need to sign in to view this result.");
      return getTestResultDetail(token, id);
    },
  });

  const retryMutation = useMutation({
    mutationFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new Error("You need to sign in to retry this test.");
      return retryTest(token, id);
    },
    onSuccess: (retried) => {
      void queryClient.invalidateQueries({ queryKey: ["tests"] });
      router.push(`/dashboard/tests/${retried.test_id}`);
    },
    onError: (err) => {
      setRetryError(err instanceof ApiError ? err.message : "Could not retry this test.");
    },
  });

  async function toggleBookmark(item: ReviewItem) {
    if (!item.question_id) return;
    setBookmarkError("");
    setBusyBookmark(item.snapshot_id);
    try {
      const token = await getSessionToken();
      if (!token) throw new Error("You need to sign in to bookmark a question.");
      if (item.is_bookmarked && item.bookmark_id) {
        await deleteCollection(token, item.bookmark_id);
      } else {
        await createCollection(token, {
          question_id: item.question_id,
          collection_type: "bookmark",
        });
      }
      await queryClient.invalidateQueries({ queryKey: ["test-result-detail", id] });
    } catch (err) {
      setBookmarkError(
        err instanceof ApiError ? err.message : "Could not update the bookmark.",
      );
    } finally {
      setBusyBookmark(null);
    }
  }

  if (detailQuery.isPending) {
    return (
      <div className="flex items-center gap-2 py-16 text-slate-600">
        <Spinner /> Loading your result…
      </div>
    );
  }

  if (detailQuery.isError) {
    const err = detailQuery.error;
    if (err instanceof ApiError && err.status === 404) {
      return (
        <EmptyState
          title="No result yet"
          description="This test has no submitted result — the result appears here after you submit the test."
        />
      );
    }
    return (
      <ErrorState
        title="Could not load the result"
        description={err instanceof Error ? err.message : "Something went wrong."}
        onRetry={() => void detailQuery.refetch()}
      />
    );
  }

  const result = detailQuery.data;

  return (
    <div className="space-y-6">
      <div>
        <SectionHeading
          title={result.title}
          description={`Submitted ${formatDateTime(result.submitted_at)} · ${result.marking_config.name} marking`}
        />
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <Card>
            
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Score</p>
              <p className="mt-1 text-2xl font-bold text-slate-900">
                {result.total_marks} <span className="text-base font-normal text-slate-500">/ {result.max_marks}</span>
              </p>
            
          </Card>
          <Card>
            
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Percentage</p>
              <p className="mt-1 text-2xl font-bold text-slate-900">{result.percentage}%</p>
            
          </Card>
          <Card>
            
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Correct</p>
              <p className="mt-1 text-2xl font-bold text-success-700">{result.correct}</p>
            
          </Card>
          <Card>
            
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Incorrect</p>
              <p className="mt-1 text-2xl font-bold text-danger-700">{result.incorrect}</p>
            
          </Card>
          <Card>
            
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Unattempted</p>
              <p className="mt-1 text-2xl font-bold text-slate-900">{result.unattempted}</p>
            
          </Card>
          <Card>
            
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Unknown</p>
              <p className="mt-1 text-2xl font-bold text-info-700">{result.unknown_count}</p>
            
          </Card>
        </div>
        <p className="mt-3 text-sm text-slate-600">
          Time taken: {formatDuration(result.time_taken_seconds)} ·{" "}
          {result.total_questions} questions · Negative marking{" "}
          {result.marking_config.incorrect_marks} per wrong answer
        </p>
        <p className="mt-1 text-sm text-slate-600">
          These numbers are the stored result — they never change, even if
          the question bank is corrected later.
        </p>
      </div>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-slate-900">Subject breakdown</h2>
        <BreakdownTable title="Subject breakdown" items={result.subject_breakdown} />
        <p className="text-sm text-slate-600">
          Questions with no subject assignment are grouped under
          “Uncategorised” — no subject is ever guessed.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-slate-900">Topic breakdown</h2>
        <BreakdownTable title="Topic breakdown" items={result.topic_breakdown} />
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-slate-900">Weak and strong areas</h2>
        {result.weak_areas.length === 0 && result.strong_areas.length === 0 ? (
          <p className="text-sm text-slate-600">
            No weak or strong area to show yet — a subject needs at least 3
            scored questions in this test before it can be ranked.
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            <Card>
              
                <CardTitle>Weakest</CardTitle>
                {result.weak_areas.length === 0 ? (
                  <p className="mt-2 text-sm text-slate-600">No subject qualifies yet.</p>
                ) : (
                  <ul className="mt-2 space-y-1 text-sm text-slate-700">
                    {result.weak_areas.map((w) => (
                      <li key={w.subject_name}>
                        {w.subject_name} — {w.accuracy}% accuracy ({w.scored} scored)
                      </li>
                    ))}
                  </ul>
                )}
              
            </Card>
            <Card>
              
                <CardTitle>Strongest</CardTitle>
                {result.strong_areas.length === 0 ? (
                  <p className="mt-2 text-sm text-slate-600">No subject qualifies yet.</p>
                ) : (
                  <ul className="mt-2 space-y-1 text-sm text-slate-700">
                    {result.strong_areas.map((w) => (
                      <li key={w.subject_name}>
                        {w.subject_name} — {w.accuracy}% accuracy ({w.scored} scored)
                      </li>
                    ))}
                  </ul>
                )}
              
            </Card>
          </div>
        )}
        <p className="text-sm text-slate-600">
          Ranked by accuracy among subjects with at least 3 scored questions
          in this test.
        </p>
      </section>

      <section className="space-y-4">
        <h2 className="text-lg font-semibold text-slate-900">Question review</h2>
        <p className="text-sm text-slate-600">
          Only what the engine stored: the frozen question, your answer, the
          stored answer, and the evidence source. No explanations are shown
          because none were stored.
        </p>
        {bookmarkError ? (
          <Alert tone="danger" title="Bookmark failed">
            {bookmarkError}
          </Alert>
        ) : null}
        {result.review.map((item) => (
          <Card key={item.snapshot_id}>
            
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold text-slate-900">Q{item.position}</span>
                <Badge tone={statusTone(item.status)}>{statusLabel(item.status)}</Badge>
                {item.marked_for_review ? <Badge tone="accent">Marked for review</Badge> : null}
                {item.is_mistake ? <Badge tone="danger">Mistake</Badge> : null}
              </div>
              <p className="mt-2 whitespace-pre-wrap text-slate-800">{item.question_text}</p>
              {item.options.length > 0 ? (
                <ul className="mt-3 space-y-1">
                  {item.options.map((opt, idx) => {
                    const isCorrect = idx === item.correct_index;
                    const isSelected = idx === item.selected_index;
                    return (
                      <li
                        key={opt.label}
                        className={
                          isCorrect
                            ? "rounded-md bg-success-50 px-3 py-1.5 text-sm text-success-900 ring-1 ring-success-200"
                            : isSelected
                              ? "rounded-md bg-danger-50 px-3 py-1.5 text-sm text-danger-900 ring-1 ring-danger-200"
                              : "rounded-md bg-slate-50 px-3 py-1.5 text-sm text-slate-700"
                        }
                      >
                        <span className="font-semibold">{optionLetter(idx)}. </span>
                        {opt.text}
                        {isCorrect ? " — stored answer" : ""}
                        {isSelected && !isCorrect ? " — your answer" : ""}
                        {isSelected && isCorrect ? " — your answer" : ""}
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <p className="mt-3 text-sm text-slate-600">
                  This question has no options (Q&amp;A pair).
                </p>
              )}
              {item.status === "unknown" ? (
                <p className="mt-3 text-sm text-info-800">
                  Answer unknown — the engine never found a verified answer
                  for this question, so it was not scored.
                </p>
              ) : null}
              {item.status === "unattempted" ? (
                <p className="mt-3 text-sm text-slate-600">
                  You did not answer this question.
                </p>
              ) : null}
              <p className="mt-3 text-xs text-slate-500">
                Evidence: {item.answer_source ?? "not recorded"}
                {item.source_document_id
                  ? ` · from document ${item.source_document_id.slice(0, 8)}…`
                  : ""}
                {item.source_page !== null ? ` · page ${item.source_page}` : ""}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={!item.question_id || busyBookmark === item.snapshot_id}
                  onClick={() => void toggleBookmark(item)}
                >
                  {busyBookmark === item.snapshot_id
                    ? "Saving…"
                    : item.is_bookmarked
                      ? "Remove bookmark"
                      : "Bookmark"}
                </Button>
              </div>
            
          </Card>
        ))}
      </section>

      <div className="flex flex-wrap gap-2">
        <Button
          loading={retryMutation.isPending}
          onClick={() => {
            setRetryError("");
            retryMutation.mutate();
          }}
        >
          Retry this test
        </Button>
        <Link href="/dashboard/results">
          <Button variant="secondary">All results</Button>
        </Link>
        <Link href="/dashboard/mistakes">
          <Button variant="secondary">Mistake notebook</Button>
        </Link>
      </div>
      <p className="text-sm text-slate-600">
        Retrying creates a new attempt of the same frozen questions — your
        original answers and score stay stored on this result.
      </p>
      {retryError ? (
        <Alert tone="danger" title="Could not retry the test">
          {retryError}
        </Alert>
      ) : null}
    </div>
  );
}

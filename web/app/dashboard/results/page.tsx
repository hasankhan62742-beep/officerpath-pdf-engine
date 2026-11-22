// OfficerPath AI — test history (Phase 2, M8, GAP-7).
//
// Real list from GET /api/v1/results (newest first, owner-only).
// Compare-over-time is shown ONLY when at least 2 results exist,
// as a simple chronological marks/% list from stored results.
// With a single result there is no trend — the page says so
// instead of faking one.

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
import { Pagination } from "@/components/ui/pagination";
import { SectionHeading } from "@/components/ui/section-heading";
import { Spinner } from "@/components/ui/spinner";
import {
  ApiError,
  getSessionToken,
  listResults,
  retryTest,
  type ExamResultDetail,
} from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

const PAGE_SIZE = 20;

function ResultRow({
  result,
  onRetry,
  retrying,
}: {
  result: ExamResultDetail;
  onRetry: (id: string) => void;
  retrying: string | null;
}) {
  return (
    <Card>
      
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <CardTitle>{result.title}</CardTitle>
            <p className="mt-1 text-sm text-slate-600">
              {formatDateTime(result.submitted_at)} · {result.total_questions}{" "}
              questions · {result.marking_config.name}
            </p>
          </div>
          <Badge tone="success">
            {result.total_marks} / {result.max_marks} ({result.percentage}%)
          </Badge>
        </div>
        <p className="mt-2 text-sm text-slate-700">
          {result.correct} correct · {result.incorrect} incorrect ·{" "}
          {result.unattempted} unattempted · {result.unknown_count} unknown
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Link href={`/dashboard/tests/${result.test_id}/result`}>
            <Button variant="secondary" size="sm">
              View result
            </Button>
          </Link>
          <Button
            variant="secondary"
            size="sm"
            loading={retrying === result.test_id}
            onClick={() => onRetry(result.test_id)}
          >
            Retry this test
          </Button>
        </div>
      
    </Card>
  );
}

export default function ResultsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [retryError, setRetryError] = useState("");
  const [retrying, setRetrying] = useState<string | null>(null);

  const listQuery = useQuery({
    queryKey: ["results", page],
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new Error("You need to sign in to view your results.");
      return listResults(token, { limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE });
    },
  });

  const retryMutation = useMutation({
    mutationFn: async (testId: string) => {
      const token = await getSessionToken();
      if (!token) throw new Error("You need to sign in to retry a test.");
      setRetrying(testId);
      return retryTest(token, testId);
    },
    onSuccess: (retried) => {
      void queryClient.invalidateQueries({ queryKey: ["results"] });
      void queryClient.invalidateQueries({ queryKey: ["tests"] });
      router.push(`/dashboard/tests/${retried.test_id}`);
    },
    onError: (err) => {
      setRetryError(err instanceof ApiError ? err.message : "Could not retry this test.");
      setRetrying(null);
    },
  });

  if (listQuery.isPending) {
    return (
      <div className="flex items-center gap-2 py-16 text-slate-600">
        <Spinner /> Loading your results…
      </div>
    );
  }

  if (listQuery.isError) {
    return (
      <ErrorState
        title="Could not load your results"
        description={
          listQuery.error instanceof Error
            ? listQuery.error.message
            : "Something went wrong."
        }
        onRetry={() => void listQuery.refetch()}
      />
    );
  }

  const { results, total } = listQuery.data;
  const chronological = [...results].reverse();

  return (
    <div className="space-y-6">
      <SectionHeading
        title="Results"
        description="Every submitted test, newest first. Scores come from the stored result — they never change, even if the question bank is corrected later."
      />

      {retryError ? (
        <Alert tone="danger" title="Could not retry the test">
          {retryError}
        </Alert>
      ) : null}

      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-slate-900">Progress over time</h2>
        {results.length < 2 ? (
          <p className="text-sm text-slate-600">
            {results.length === 0
              ? "No attempts yet — submit a test to see your progress here."
              : "Only one attempt so far, so there is no trend to show yet. After a second attempt, your marks over time will appear here."}
          </p>
        ) : (
          <Card>
            
              <ul className="space-y-1 text-sm text-slate-700">
                {chronological.map((r, idx) => (
                  <li key={r.result_id}>
                    Attempt {idx + 1} — {formatDateTime(r.submitted_at)}: {r.title},{" "}
                    {r.total_marks} / {r.max_marks} ({r.percentage}%)
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-xs text-slate-500">
                Chronological list of stored results, oldest first. No trend
                is fitted or predicted — these are your real marks.
              </p>
            
          </Card>
        )}
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-slate-900">All results</h2>
        {results.length === 0 ? (
          <EmptyState
            title="No results yet"
            description="Submit a test to see your score, breakdown and review here."
          />
        ) : (
          results.map((r) => (
            <ResultRow
              key={r.result_id}
              result={r}
              retrying={retrying}
              onRetry={(testId) => {
                setRetryError("");
                retryMutation.mutate(testId);
              }}
            />
          ))
        )}
        <Pagination
          page={page}
          totalPages={Math.max(1, Math.ceil(total / PAGE_SIZE))}
          onPageChange={setPage}
        />
      </section>
    </div>
  );
}

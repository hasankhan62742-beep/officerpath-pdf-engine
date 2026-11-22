"use client";

// OfficerPath AI — extraction results for one document (Phase 2, M5).
//
// Real data from GET /api/v1/documents/{id}/questions and
// GET /api/v1/documents/{id}/report. Counts are the engine's
// counts; a low recovery is shown plainly, never dressed up.
// Q&A pairs are a count only (the Phase 1 store keeps their
// count, not rows) — the UI says so instead of inventing rows.

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Alert } from "@/components/ui/alert";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { Pagination } from "@/components/ui/pagination";
import { Spinner } from "@/components/ui/spinner";
import { QuestionResultCard } from "@/components/dashboard/question-result";
import {
  getDocumentReport,
  getSessionToken,
  listDocumentQuestions,
} from "@/lib/api";

const PAGE_SIZE = 10;

export function DocumentResults({ documentId }: { documentId: string }) {
  const [page, setPage] = useState(1);

  const questionsQuery = useQuery({
    queryKey: ["document-questions", documentId, page],
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      return listDocumentQuestions(token, documentId, {
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
      });
    },
  });

  const reportQuery = useQuery({
    queryKey: ["document-report", documentId],
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      return getDocumentReport(token, documentId);
    },
  });

  if (questionsQuery.isPending) {
    return (
      <div className="flex items-center gap-2 py-8 text-slate-600">
        <Spinner /> Loading the extracted questions…
      </div>
    );
  }

  if (questionsQuery.isError || !questionsQuery.data) {
    return (
      <ErrorState
        title="Could not load the results"
        description={
          (questionsQuery.error as Error | null)?.message ??
          "The engine did not answer. Check that it is running and try again."
        }
        onRetry={() => questionsQuery.refetch()}
      />
    );
  }

  const { counts, qa_pairs, questions, total } = questionsQuery.data;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const report = reportQuery.data;

  if (total === 0 && qa_pairs === 0) {
    return (
      <EmptyState
        title="No questions extracted"
        description="The engine found no questions in this document. Check the report below for what it saw, or try a clearer scan."
      />
    );
  }

  return (
    <div className="space-y-6">
      <dl className="grid grid-cols-2 gap-4 text-center sm:grid-cols-5">
        <div className="rounded-xl bg-slate-50 px-2 py-3">
          <dt className="text-xs font-medium text-slate-500">Questions</dt>
          <dd className="text-2xl font-bold text-slate-900">{counts.questions ?? 0}</dd>
        </div>
        <div className="rounded-xl bg-slate-50 px-2 py-3">
          <dt className="text-xs font-medium text-slate-500">Answered</dt>
          <dd className="text-2xl font-bold text-slate-900">{counts.answered ?? 0}</dd>
        </div>
        <div className="rounded-xl bg-slate-50 px-2 py-3">
          <dt className="text-xs font-medium text-slate-500">Unknown</dt>
          <dd className="text-2xl font-bold text-slate-900">{counts.unknown ?? 0}</dd>
        </div>
        <div className="rounded-xl bg-slate-50 px-2 py-3">
          <dt className="text-xs font-medium text-slate-500">Needs review</dt>
          <dd className="text-2xl font-bold text-slate-900">{counts.pending ?? 0}</dd>
        </div>
        <div className="rounded-xl bg-slate-50 px-2 py-3">
          <dt className="text-xs font-medium text-slate-500">Inferred</dt>
          <dd className="text-2xl font-bold text-slate-900">{counts.inferred ?? 0}</dd>
        </div>
      </dl>

      {qa_pairs > 0 ? (
        <Alert tone="info" title={`Q&A pairs: ${qa_pairs}`}>
          This document also contains {qa_pairs} question-and-answer pair
          {qa_pairs === 1 ? "" : "s"} (answers without options). They are
          counted in the report but not listed as questions — the engine
          stores their count only, and they are never forced into four
          options.
        </Alert>
      ) : null}

      {report?.requires_review ? (
        <Alert tone="warning" title="This document needs review">
          {counts.unknown ?? 0} question{(counts.unknown ?? 0) === 1 ? " has" : "s have"}{" "}
          no determined answer
          {counts.pending ? `, including ${counts.pending} still pending` : ""}.
          {(report.review_reasons ?? []).length > 0
            ? ` Engine notes: ${(report.review_reasons ?? []).slice(0, 3).join("; ")}.`
            : ""}
        </Alert>
      ) : null}

      <div className="space-y-4">
        {questions.map((item) => (
          <QuestionResultCard key={item.question_id} item={item} />
        ))}
      </div>

      <p className="text-sm text-slate-600">
        Showing {(page - 1) * PAGE_SIZE + 1}–
        {Math.min(page * PAGE_SIZE, total)} of {total} questions.
      </p>
      <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />

      {report ? (
        <Card className="p-5">
          <CardTitle>Extraction report</CardTitle>
          <CardDescription>
            The engine&apos;s own report for this document — rule set{" "}
            {report.rule_set_version}.
          </CardDescription>
          <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
            <div>
              <dt className="font-medium text-slate-500">Questions extracted</dt>
              <dd className="text-slate-900">{report.questions_extracted}</dd>
            </div>
            <div>
              <dt className="font-medium text-slate-500">Missing options</dt>
              <dd className="text-slate-900">{report.questions_missing_options}</dd>
            </div>
            <div>
              <dt className="font-medium text-slate-500">Uncertain answers</dt>
              <dd className="text-slate-900">{report.uncertain_answers}</dd>
            </div>
            <div>
              <dt className="font-medium text-slate-500">Conflicting answers</dt>
              <dd className="text-slate-900">{report.conflicting_answers}</dd>
            </div>
            <div>
              <dt className="font-medium text-slate-500">Unmatched key entries</dt>
              <dd className="text-slate-900">{report.unmatched_key_entries}</dd>
            </div>
            <div>
              <dt className="font-medium text-slate-500">Duplicates found</dt>
              <dd className="text-slate-900">{report.duplicates_found}</dd>
            </div>
          </dl>
        </Card>
      ) : null}
    </div>
  );
}

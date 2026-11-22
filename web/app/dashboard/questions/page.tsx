"use client";

// OfficerPath AI — Question bank (Phase 2, M5).
//
// Every row is a real extracted question from the engine
// database. Search and filters run against the API, never
// against invented data. A question with no subject shows as
// "Uncategorised" — subjects are assigned by hand, never
// guessed by the engine.

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Pagination } from "@/components/ui/pagination";
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
import { QuestionBadges } from "@/components/dashboard/question-result";
import {
  BANK_STATUSES,
  getSessionToken,
  listDocuments,
  listQuestions,
  listSubjects,
  type BankStatus,
} from "@/lib/api";

const PAGE_SIZE = 20;

type ConfidenceBand = "all" | "high" | "medium" | "low";

const BANDS: Record<ConfidenceBand, { min?: number; max?: number }> = {
  all: {},
  high: { min: 0.9 },
  medium: { min: 0.5, max: 0.9 },
  low: { max: 0.5 },
};

export default function QuestionsPage() {
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [documentId, setDocumentId] = useState("all");
  const [status, setStatus] = useState<"all" | BankStatus>("all");
  const [subjectId, setSubjectId] = useState("all");
  const [band, setBand] = useState<ConfidenceBand>("all");

  const listQuery = useQuery({
    queryKey: ["questions", page, search, documentId, status, subjectId, band],
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      return listQuestions(token, {
        q: search || undefined,
        document_id: documentId === "all" ? undefined : documentId,
        status: status === "all" ? undefined : status,
        subject_id: subjectId === "all" ? undefined : subjectId,
        confidence_min: BANDS[band].min,
        confidence_max: BANDS[band].max,
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
      });
    },
  });

  const docsQuery = useQuery({
    queryKey: ["documents-for-filter"],
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      return listDocuments(token, { limit: 100, offset: 0 });
    },
  });

  const subjectsQuery = useQuery({
    queryKey: ["subjects"],
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      return listSubjects(token);
    },
  });

  const totalPages = listQuery.data
    ? Math.max(1, Math.ceil(listQuery.data.total / PAGE_SIZE))
    : 1;

  function resetPage() {
    setPage(1);
  }

  return (
    <div className="space-y-6">
      <SectionHeading
        title="Question bank"
        description="Every question the engine extracted from your documents, with its answer state. Unknown stays unknown — nothing here is guessed."
        level="h1"
        align="left"
      />

      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          setSearch(searchInput.trim());
          resetPage();
        }}
      >
        <div className="min-w-56 flex-1">
          <Input
            label="Search questions"
            id="bank-search"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search by question text…"
          />
        </div>
        <Button type="submit" variant="secondary">
          Search
        </Button>
        <label className="text-sm font-medium text-slate-700" htmlFor="doc-filter">
          Document
        </label>
        <select
          id="doc-filter"
          className="min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm"
          value={documentId}
          onChange={(e) => {
            setDocumentId(e.target.value);
            resetPage();
          }}
        >
          <option value="all">All documents</option>
          {(docsQuery.data?.documents ?? []).map((doc) => (
            <option key={doc.id} value={doc.id}>
              {doc.title}
            </option>
          ))}
        </select>
        <label className="text-sm font-medium text-slate-700" htmlFor="status-filter">
          Answer
        </label>
        <select
          id="status-filter"
          className="min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as "all" | BankStatus);
            resetPage();
          }}
        >
          <option value="all">All answers</option>
          {BANK_STATUSES.map((s) => (
            <option key={s} value={s}>
              {s.charAt(0).toUpperCase() + s.slice(1)}
            </option>
          ))}
        </select>
        <label className="text-sm font-medium text-slate-700" htmlFor="subject-filter">
          Subject
        </label>
        <select
          id="subject-filter"
          className="min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm"
          value={subjectId}
          onChange={(e) => {
            setSubjectId(e.target.value);
            resetPage();
          }}
        >
          <option value="all">All subjects</option>
          {(subjectsQuery.data?.subjects ?? []).map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
        <label className="text-sm font-medium text-slate-700" htmlFor="band-filter">
          Confidence
        </label>
        <select
          id="band-filter"
          className="min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm"
          value={band}
          onChange={(e) => {
            setBand(e.target.value as ConfidenceBand);
            resetPage();
          }}
        >
          <option value="all">Any confidence</option>
          <option value="high">High (≥ 90%)</option>
          <option value="medium">Medium (50–90%)</option>
          <option value="low">Low (&lt; 50%)</option>
        </select>
      </form>
      <p className="text-xs text-slate-500">
        Confidence filters apply only to answered questions — unknown
        answers have no confidence to filter on.
      </p>

      {listQuery.isPending ? (
        <div className="flex items-center gap-2 py-16 text-slate-600">
          <Spinner /> Loading your questions…
        </div>
      ) : listQuery.isError || !listQuery.data ? (
        <ErrorState
          title="Could not load your questions"
          description={
            (listQuery.error as Error | null)?.message ??
            "The engine did not answer. Check that it is running and try again."
          }
          onRetry={() => listQuery.refetch()}
        />
      ) : listQuery.data.total === 0 ? (
        <EmptyState
          title="No questions found"
          description={
            search || documentId !== "all" || status !== "all" || subjectId !== "all" || band !== "all"
              ? "Nothing matches these filters. Clear a filter or try different words."
              : "Upload a paper first — extracted questions appear here once a document finishes processing."
          }
          actionLabel={
            search || documentId !== "all" || status !== "all" || subjectId !== "all" || band !== "all"
              ? undefined
              : "Upload your first document"
          }
          actionHref={
            search || documentId !== "all" || status !== "all" || subjectId !== "all" || band !== "all"
              ? undefined
              : "/dashboard/upload"
          }
        />
      ) : (
        <>
          <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white">
            <Table>
              <TableHead>
                <TableRow>
                  <TableHeaderCell>Question</TableHeaderCell>
                  <TableHeaderCell>Document</TableHeaderCell>
                  <TableHeaderCell>Answer</TableHeaderCell>
                  <TableHeaderCell>Confidence</TableHeaderCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {listQuery.data.questions.map((q) => (
                  <TableRow key={q.question_id}>
                    <TableCell>
                      <Link
                        href={`/dashboard/questions/${q.question_id}`}
                        className="font-medium text-brand-700 hover:underline"
                      >
                        {q.number ? `Q${q.number} — ` : ""}
                        {q.text.length > 120 ? `${q.text.slice(0, 120)}…` : q.text}
                      </Link>
                      <div className="mt-1">
                        <QuestionBadges item={q} />
                      </div>
                    </TableCell>
                    <TableCell>
                      <Link
                        href={`/dashboard/documents/${q.document_id}`}
                        className="text-brand-700 hover:underline"
                      >
                        {q.document_title}
                      </Link>
                    </TableCell>
                    <TableCell>
                      {q.correct_index >= 0 ? (
                        <span className="font-semibold text-slate-900">
                          {q.correct_letter}
                        </span>
                      ) : (
                        <span className="text-slate-500">Unknown</span>
                      )}
                    </TableCell>
                    <TableCell>
                      {q.confidence !== null
                        ? `${Math.round(q.confidence * 100)}%`
                        : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <p className="text-sm text-slate-600">
            Showing {(page - 1) * PAGE_SIZE + 1}–
            {Math.min(page * PAGE_SIZE, listQuery.data.total)} of{" "}
            {listQuery.data.total} questions.
          </p>
          <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
        </>
      )}
    </div>
  );
}

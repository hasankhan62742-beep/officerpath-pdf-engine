// OfficerPath AI — admin question review access (Phase 2, M9,
// GAP-10). Real bank rows from GET /api/v1/admin/questions with
// search + status filters; each row links to the student question
// detail page for the full evidence trail.

"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { ErrorState, EmptyState } from "@/components/ui/empty-state";
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
import { ApiError, getSessionToken, listAdminQuestions } from "@/lib/api";

const PAGE_SIZE = 20;

export default function AdminQuestionsPage() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [submittedSearch, setSubmittedSearch] = useState("");
  const [validationStatus, setValidationStatus] = useState("");

  const query = useQuery({
    queryKey: ["admin-questions", page, submittedSearch, validationStatus],
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new ApiError(401, "unauthorized", "Sign in to view the admin area.");
      return listAdminQuestions(token, {
        search: submittedSearch || undefined,
        validation_status: validationStatus || undefined,
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
      });
    },
  });

  if (query.isPending) return <Spinner />;
  if (query.isError) {
    return (
      <ErrorState
        title="Questions could not be loaded"
        description={query.error instanceof Error ? query.error.message : "Try again."}
        onRetry={() => void query.refetch()}
      />
    );
  }

  const data = query.data;
  const totalPages = Math.max(1, Math.ceil(data.total / PAGE_SIZE));

  return (
    <div>
      <SectionHeading
        eyebrow="Admin"
        title="Question bank"
        description={`${data.total} extracted question${data.total === 1 ? "" : "s"} in the bank. Open any row for its full evidence trail.`}
      />
      <form
        className="mb-6 flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setSubmittedSearch(search.trim());
          setPage(1);
        }}
      >
        <Input
          label="Search questions"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search the question text…"
          className="max-w-sm"
        />
        <Button type="submit" size="sm">
          Search
        </Button>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={() => {
            setSearch("");
            setSubmittedSearch("");
            setValidationStatus("");
            setPage(1);
          }}
        >
          Clear
        </Button>
      </form>
      <div className="mb-6 flex flex-wrap gap-2">
        {["", "answered", "unknown", "pending"].map((s) => (
          <Button
            key={s || "all"}
            variant={validationStatus === s ? "primary" : "secondary"}
            size="sm"
            onClick={() => { setValidationStatus(s); setPage(1); }}
          >
            {s === "" ? "All statuses" : s}
          </Button>
        ))}
      </div>
      {data.items.length === 0 ? (
        <EmptyState title="No questions found" description="Try a different search or status filter." />
      ) : (
        <Table>
          <TableHead>
            <TableRow>
              <TableHeaderCell>Question</TableHeaderCell>
              <TableHeaderCell>Options</TableHeaderCell>
              <TableHeaderCell>Answer</TableHeaderCell>
              <TableHeaderCell>Status</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data.items.map((q) => (
              <TableRow key={q.id}>
                <TableCell>
                  <Link
                    href={`/dashboard/questions/${q.id}`}
                    className="font-medium text-brand-700 underline"
                  >
                    {q.text.length > 90 ? `${q.text.slice(0, 90)}…` : q.text}
                  </Link>
                  {q.question_number && (
                    <span className="block text-xs text-slate-500">Q{q.question_number}</span>
                  )}
                </TableCell>
                <TableCell>{q.options_count}</TableCell>
                <TableCell>
                  {q.correct_index >= 0 ? String.fromCharCode(65 + q.correct_index) : "Unknown"}
                </TableCell>
                <TableCell>{q.validation_status}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      <div className="mt-6">
        <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
      </div>
    </div>
  );
}

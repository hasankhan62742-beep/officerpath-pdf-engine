// OfficerPath AI — admin community review (M16).
//
// The approval queue: every student-submitted question waits
// here (pending first) with its paper, source and contributor
// name. The paper is shown prominently — it is what lets the
// admin spot a repetition at review time. Approving mints the
// bank rows at once, so the question joins that subject's pool;
// rejecting records the reason, which the contributor sees on
// their own submissions list.

"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Pagination } from "@/components/ui/pagination";
import { SectionHeading } from "@/components/ui/section-heading";
import { Spinner } from "@/components/ui/spinner";
import {
  ApiError,
  getSessionToken,
  listAdminCommunityQuestions,
  reviewCommunityQuestion,
} from "@/lib/api";
import { formatMathText } from "@/lib/mathText";

const PAGE_SIZE = 20;
const OPTION_LETTERS = ["A", "B", "C", "D"];

function statusTone(status: string): "info" | "success" | "danger" | "neutral" {
  if (status === "pending") return "info";
  if (status === "approved") return "success";
  if (status === "rejected") return "danger";
  return "neutral";
}

export default function AdminCommunityPage() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState("");
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionNote, setActionNote] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ["admin-community-questions", page, statusFilter],
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new ApiError(401, "unauthorized", "Sign in to view the admin area.");
      return listAdminCommunityQuestions(token, {
        status: statusFilter || undefined,
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
      });
    },
  });

  const reviewMutation = useMutation({
    mutationFn: async (args: { id: string; approved: boolean; note: string }) => {
      const token = await getSessionToken();
      if (!token) throw new ApiError(401, "unauthorized", "Sign in to view the admin area.");
      return reviewCommunityQuestion(token, args.id, {
        approved: args.approved,
        note: args.note.trim() || null,
      });
    },
    onSuccess: (result) => {
      setActionError(null);
      setActionNote(
        result.status === "approved"
          ? "Approved — the question is now in the bank."
          : "Rejected — the contributor can see your note.",
      );
      setNotes((prev) => {
        const next = { ...prev };
        delete next[result.id];
        return next;
      });
      void queryClient.invalidateQueries({ queryKey: ["admin-community-questions"] });
    },
    onError: (err) => {
      setActionNote(null);
      setActionError(err instanceof Error ? err.message : "The review could not be saved.");
    },
  });

  if (query.isPending) return <Spinner />;
  if (query.isError) {
    return (
      <ErrorState
        title="Community questions could not be loaded"
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
        title="Community questions"
        description={`${data.total} student-submitted question${data.total === 1 ? "" : "s"}. Approve to add a question to the bank at once; reject with a note the contributor can see.`}
      />

      <div className="mb-6 flex flex-wrap items-end gap-2">
        <div>
          <label
            className="mb-1.5 block text-sm font-medium text-slate-900"
            htmlFor="status-filter"
          >
            Status
          </label>
          <select
            id="status-filter"
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(1);
            }}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
          >
            <option value="">All (pending first)</option>
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
          </select>
        </div>
      </div>

      {actionError ? (
        <p role="alert" className="mb-4 text-sm font-medium text-danger-700">
          {actionError}
        </p>
      ) : null}
      {actionNote ? (
        <p role="status" className="mb-4 text-sm font-medium text-success-800">
          {actionNote}
        </p>
      ) : null}

      {data.total === 0 ? (
        <EmptyState
          title="No submissions yet"
          description="Student-submitted questions will wait here for review."
        />
      ) : (
        <div>
          <ul className="space-y-4">
            {data.items.map((item) => (
              <li
                key={item.id}
                className="rounded-2xl border border-slate-200 bg-white p-4"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={statusTone(item.status)}>{item.status}</Badge>
                  <span className="text-sm text-slate-500">
                    {item.subject.subject_name ?? "No subject"}
                    {item.subject.topic_name ? ` — ${item.subject.topic_name}` : ""}
                  </span>
                  <span className="text-sm text-slate-500">
                    Submitted by {item.contributor_name}
                  </span>
                </div>
                {item.paper ? (
                  <p className="mt-2 text-sm font-semibold text-slate-900">
                    Paper: {item.paper}
                  </p>
                ) : (
                  <p className="mt-2 text-sm text-slate-500">Paper: not given</p>
                )}
                {item.source ? (
                  <p className="text-sm text-slate-500">Source: {item.source}</p>
                ) : null}
                <p className="mt-2 text-slate-900">{formatMathText(item.question)}</p>
                <ol className="mt-2 space-y-1 text-sm text-slate-700">
                  {item.options.map((option, i) => (
                    <li
                      key={i}
                      className={i === item.correct_index ? "font-semibold text-green-900" : ""}
                    >
                      {OPTION_LETTERS[i]}. {formatMathText(option)}
                      {i === item.correct_index ? " — correct answer" : ""}
                    </li>
                  ))}
                </ol>
                {item.explanation ? (
                  <p className="mt-2 whitespace-pre-wrap text-sm text-slate-700">
                    Explanation: {formatMathText(item.explanation)}
                  </p>
                ) : null}
                {item.review_note ? (
                  <p className="mt-2 text-sm text-slate-600">
                    Review note: {item.review_note}
                  </p>
                ) : null}
                {item.status === "pending" ? (
                  <div className="mt-3 space-y-2">
                    <Input
                      label="Note for the contributor (optional)"
                      name={`note-${item.id}`}
                      value={notes[item.id] ?? ""}
                      onChange={(e) =>
                        setNotes((prev) => ({ ...prev, [item.id]: e.target.value }))
                      }
                      placeholder="e.g. Answer is wrong — the correct option is C."
                    />
                    <div className="flex flex-wrap gap-2">
                      <Button
                        variant="success"
                        size="sm"
                        loading={reviewMutation.isPending}
                        onClick={() =>
                          reviewMutation.mutate({
                            id: item.id,
                            approved: true,
                            note: notes[item.id] ?? "",
                          })
                        }
                      >
                        Approve — add to bank
                      </Button>
                      <Button
                        variant="danger"
                        size="sm"
                        loading={reviewMutation.isPending}
                        onClick={() =>
                          reviewMutation.mutate({
                            id: item.id,
                            approved: false,
                            note: notes[item.id] ?? "",
                          })
                        }
                      >
                        Reject
                      </Button>
                    </div>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
          <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
        </div>
      )}
    </div>
  );
}

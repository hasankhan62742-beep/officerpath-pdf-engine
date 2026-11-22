"use client";

// OfficerPath AI — My Documents (Phase 2, M4).
//
// Real list from GET /api/v1/documents (paginated, owner-only).
// Retry / Cancel / Delete are real engine calls; the list
// refetches after each one. Nothing here is a placeholder.

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { Modal } from "@/components/ui/modal";
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
import { JobStatusBadge } from "@/components/dashboard/job-status-badge";
import {
  ApiError,
  JOB_STATUSES,
  cancelJob,
  deleteDocument,
  getSessionToken,
  listDocuments,
  retryJob,
  type DashboardDocument,
  type JobStatus,
} from "@/lib/api";
import { formatBytes, formatDateTime } from "@/lib/utils";

const PAGE_SIZE = 20;

function RowActions({ doc }: { doc: DashboardDocument }) {
  const queryClient = useQueryClient();
  const [actionError, setActionError] = useState<string | null>(null);
  const [acting, setActing] = useState<"cancel" | "retry" | "delete" | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const job = doc.job;
  const cancellable = job?.status === "queued" || job?.status === "processing";
  const retryable = job?.status === "failed" || job?.status === "cancelled";

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: ["documents"] });
    await queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
  }

  async function act(kind: "cancel" | "retry" | "delete") {
    setActionError(null);
    setActing(kind);
    try {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      if (!job && kind !== "delete") return;
      if (kind === "cancel" && job) await cancelJob(token, job.id);
      if (kind === "retry" && job) await retryJob(token, job.id);
      if (kind === "delete") await deleteDocument(token, doc.id);
      await refresh();
    } catch (err) {
      setActionError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "That action failed. Please try again.",
      );
    } finally {
      setActing(null);
      setConfirmDelete(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-1">
      <Button variant="ghost" size="sm" href={`/dashboard/documents/${doc.id}`}>
        View
      </Button>
      {retryable ? (
        <Button
          variant="ghost"
          size="sm"
          disabled={acting !== null}
          onClick={() => act("retry")}
        >
          {acting === "retry" ? "Retrying…" : "Retry"}
        </Button>
      ) : null}
      {cancellable ? (
        <Button
          variant="ghost"
          size="sm"
          disabled={acting !== null}
          onClick={() => act("cancel")}
        >
          {acting === "cancel" ? "Cancelling…" : "Cancel"}
        </Button>
      ) : null}
      <Button
        variant="ghost"
        size="sm"
        disabled={acting !== null}
        onClick={() => setConfirmDelete(true)}
      >
        Delete
      </Button>
      {actionError ? (
        <span role="alert" className="w-full text-xs text-danger-700">
          {actionError}
        </span>
      ) : null}
      <Modal
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        title={`Delete “${doc.title}”?`}
      >
        <p>
          The document is removed from your list. Its processing job is
          cancelled if it is still running. The original file is deleted
          from this server&apos;s storage.
        </p>
        <div className="mt-5 flex gap-2">
          <Button
            variant="danger"
            disabled={acting !== null}
            loading={acting === "delete"}
            onClick={() => act("delete")}
          >
            Delete document
          </Button>
          <Button variant="secondary" onClick={() => setConfirmDelete(false)}>
            Keep it
          </Button>
        </div>
      </Modal>
    </div>
  );
}

export default function DocumentsPage() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<"all" | JobStatus>("all");

  const listQuery = useQuery({
    queryKey: ["documents", page, status],
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      return listDocuments(token, {
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
        status: status === "all" ? undefined : status,
      });
    },
  });

  const totalPages = listQuery.data
    ? Math.max(1, Math.ceil(listQuery.data.total / PAGE_SIZE))
    : 1;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <SectionHeading
          title="My Documents"
          description="Every paper and photo you uploaded, with its processing status."
          level="h1"
          align="left"
        />
        <Button href="/dashboard/upload">Upload a document</Button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor="status-filter" className="text-sm font-medium text-slate-700">
          Status
        </label>
        <select
          id="status-filter"
          className="min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as "all" | JobStatus);
            setPage(1);
          }}
        >
          <option value="all">All statuses</option>
          {JOB_STATUSES.map((s) => (
            <option key={s} value={s}>
              {s.charAt(0).toUpperCase() + s.slice(1)}
            </option>
          ))}
        </select>
      </div>

      {listQuery.isPending ? (
        <div className="flex items-center gap-2 py-16 text-slate-600">
          <Spinner /> Loading your documents…
        </div>
      ) : listQuery.isError || !listQuery.data ? (
        <ErrorState
          title="Could not load your documents"
          description={
            (listQuery.error as Error | null)?.message ??
            "The engine did not answer. Check that it is running and try again."
          }
          onRetry={() => listQuery.refetch()}
        />
      ) : listQuery.data.total === 0 ? (
        <EmptyState
          title="No documents yet"
          description={
            status === "all"
              ? "Upload your first paper — a PPSC past paper PDF or a photo of a question table."
              : `No documents with status “${status}”. Try another status.`
          }
          actionLabel={status === "all" ? "Upload your first document" : undefined}
          actionHref={status === "all" ? "/dashboard/upload" : undefined}
        />
      ) : (
        <>
          <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white">
            <Table>
              <TableHead>
                <TableRow>
                  <TableHeaderCell>Document</TableHeaderCell>
                  <TableHeaderCell>Type</TableHeaderCell>
                  <TableHeaderCell>Size</TableHeaderCell>
                  <TableHeaderCell>Questions</TableHeaderCell>
                  <TableHeaderCell>Status</TableHeaderCell>
                  <TableHeaderCell>Actions</TableHeaderCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {listQuery.data.documents.map((doc) => (
                  <TableRow key={doc.id}>
                    <TableCell>
                      <Link
                        href={`/dashboard/documents/${doc.id}`}
                        className="font-medium text-brand-700 hover:underline"
                      >
                        {doc.title}
                      </Link>
                      <p className="text-xs text-slate-500">
                        {formatDateTime(doc.created_at)}
                      </p>
                    </TableCell>
                    <TableCell>{doc.file_type.toUpperCase()}</TableCell>
                    <TableCell>{formatBytes(doc.file_size_bytes)}</TableCell>
                    <TableCell>
                      {doc.job?.status === "done" && doc.questions !== null
                        ? `${doc.answered ?? 0} / ${doc.questions}`
                        : "—"}
                    </TableCell>
                    <TableCell>
                      {doc.job ? <JobStatusBadge status={doc.job.status} /> : "—"}
                    </TableCell>
                    <TableCell>
                      <RowActions doc={doc} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <p className="text-sm text-slate-600">
            Showing {(page - 1) * PAGE_SIZE + 1}–
            {Math.min(page * PAGE_SIZE, listQuery.data.total)} of{" "}
            {listQuery.data.total} documents.
          </p>
          <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
        </>
      )}
    </div>
  );
}

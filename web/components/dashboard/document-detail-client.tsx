"use client";

// OfficerPath AI — document detail (Phase 2, M4).
//
// Real detail from GET /api/v1/documents/{id}: the document, its
// job, and the job's stage history. Polls while the job is active
// (5 s, backoff to 15 s after 2 min) and stops on terminal states.
// Retry / Cancel / Delete are real engine calls. The questions
// themselves arrive in Milestone 5 — this page shows the counts
// only, never invented questions.

import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/empty-state";
import { Modal } from "@/components/ui/modal";
import { SectionHeading } from "@/components/ui/section-heading";
import { Spinner } from "@/components/ui/spinner";
import { JobStatusBadge, isJobActive } from "@/components/dashboard/job-status-badge";
import {
  ApiError,
  cancelJob,
  deleteDocument,
  getDocument,
  getSessionToken,
  retryJob,
} from "@/lib/api";
import { formatBytes, formatDateTime } from "@/lib/utils";

export function DocumentDetailClient({ id }: { id: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const pollStartedAt = useRef<number | null>(null);

  const detailQuery = useQuery({
    queryKey: ["document", id],
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      return getDocument(token, id);
    },
    refetchInterval: (query) => {
      const status = query.state.data?.job?.status;
      if (!isJobActive(status)) {
        pollStartedAt.current = null;
        return false;
      }
      if (pollStartedAt.current === null) pollStartedAt.current = Date.now();
      return Date.now() - pollStartedAt.current > 120_000 ? 15_000 : 5_000;
    },
  });

  const [actionError, setActionError] = useState<string | null>(null);
  const [acting, setActing] = useState<"cancel" | "retry" | "delete" | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  async function refreshAll() {
    await queryClient.invalidateQueries({ queryKey: ["document", id] });
    await queryClient.invalidateQueries({ queryKey: ["documents"] });
    await queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
  }

  async function act(kind: "cancel" | "retry" | "delete") {
    setActionError(null);
    setActing(kind);
    try {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      if (kind === "cancel" && detailQuery.data?.job) {
        await cancelJob(token, detailQuery.data.job.id);
      } else if (kind === "retry" && detailQuery.data?.job) {
        await retryJob(token, detailQuery.data.job.id);
      } else if (kind === "delete") {
        await deleteDocument(token, id);
        router.push("/dashboard/documents");
        return;
      }
      await refreshAll();
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

  if (detailQuery.isPending) {
    return (
      <div className="flex items-center gap-2 py-16 text-slate-600">
        <Spinner /> Loading the document…
      </div>
    );
  }

  if (detailQuery.isError || !detailQuery.data) {
    const status = (detailQuery.error as ApiError | null)?.status;
    return (
      <ErrorState
        title={status === 404 ? "Document not found" : "Could not load the document"}
        description={
          status === 404
            ? "It may have been deleted, or the link is wrong."
            : ((detailQuery.error as Error | null)?.message ??
              "The engine did not answer. Check that it is running and try again.")
        }
        onRetry={() => detailQuery.refetch()}
      />
    );
  }

  const { document, job, stages } = detailQuery.data;
  const summary = (job?.result_summary ?? {}) as Record<string, unknown>;
  const questions = typeof summary.questions === "number" ? summary.questions : null;
  const answered = typeof summary.answered === "number" ? summary.answered : null;
  const pending = typeof summary.pending === "number" ? summary.pending : null;
  const cancellable = job?.status === "queued" || job?.status === "processing";
  const retryable = job?.status === "failed" || job?.status === "cancelled";

  return (
    <div className="space-y-8">
      <div>
        <Link
          href="/dashboard/documents"
          className="text-sm font-medium text-brand-700 hover:underline"
        >
          ← All documents
        </Link>
        <div className="mt-2">
          <SectionHeading
            title={document.title}
            description={`${document.file_type.toUpperCase()} · ${formatBytes(document.file_size_bytes)} · uploaded ${formatDateTime(document.created_at)}`}
            level="h1"
            align="left"
          />
        </div>
      </div>

      {actionError ? (
        <Alert tone="danger" title="That action did not work">
          {actionError}
        </Alert>
      ) : null}

      <Card className="p-5">
        <CardTitle>Processing status</CardTitle>
        <CardDescription>
          {job
            ? "Live from the engine — this page updates while the job runs."
            : "No processing job exists for this document."}
        </CardDescription>
        <div className="mt-4 space-y-3">
          {job ? (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <JobStatusBadge status={job.status} />
                {isJobActive(job.status) ? (
                  <span className="inline-flex items-center gap-2 text-sm text-slate-600">
                    <Spinner /> Processing — this page updates automatically.
                  </span>
                ) : null}
                {job.completed_at ? (
                  <span className="text-sm text-slate-600">
                    Finished {formatDateTime(job.completed_at)}.
                  </span>
                ) : null}
              </div>
              {job.error ? (
                <Alert tone="danger" title="Processing failed">
                  {job.error}
                </Alert>
              ) : null}
              {job.status === "done" ? (
                <dl className="grid grid-cols-3 gap-4 text-center">
                  <div className="rounded-xl bg-slate-50 px-2 py-3">
                    <dt className="text-xs font-medium text-slate-500">Questions</dt>
                    <dd className="text-2xl font-bold text-slate-900">{questions ?? "—"}</dd>
                  </div>
                  <div className="rounded-xl bg-slate-50 px-2 py-3">
                    <dt className="text-xs font-medium text-slate-500">Answered</dt>
                    <dd className="text-2xl font-bold text-slate-900">{answered ?? "—"}</dd>
                  </div>
                  <div className="rounded-xl bg-slate-50 px-2 py-3">
                    <dt className="text-xs font-medium text-slate-500">Needs review</dt>
                    <dd className="text-2xl font-bold text-slate-900">{pending ?? "—"}</dd>
                  </div>
                </dl>
              ) : null}
              {stages.length > 0 ? (
                <div>
                  <h3 className="text-sm font-semibold text-slate-900">Stages</h3>
                  <ul className="mt-2 space-y-1 text-sm text-slate-600">
                    {stages.map((stage) => (
                      <li key={`${stage.stage}-${stage.created_at}`} className="flex gap-2">
                        <span className="font-medium text-slate-800">{stage.stage}</span>
                        <span>— {stage.status}</span>
                        {typeof stage.detail?.seconds === "number" ? (
                          <span>({stage.detail.seconds}s)</span>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              <p className="text-sm text-slate-600">
                Questions and answers for this document arrive in Milestone 5
                — the question bank view.
              </p>
            </>
          ) : null}
          <div className="flex flex-wrap gap-2">
            {cancellable ? (
              <Button
                variant="secondary"
                disabled={acting !== null}
                onClick={() => act("cancel")}
              >
                {acting === "cancel" ? "Cancelling…" : "Cancel job"}
              </Button>
            ) : null}
            {retryable ? (
              <Button
                variant="secondary"
                disabled={acting !== null}
                onClick={() => act("retry")}
              >
                {acting === "retry" ? "Retrying…" : "Retry job"}
              </Button>
            ) : null}
            <Button
              variant="danger"
              disabled={acting !== null}
              onClick={() => setConfirmDelete(true)}
            >
              Delete document
            </Button>
          </div>
        </div>
      </Card>

      <Card className="p-5">
        <CardTitle>Details</CardTitle>
        <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
          <div>
            <dt className="font-medium text-slate-500">File type</dt>
            <dd className="text-slate-900">{document.file_type.toUpperCase()}</dd>
          </div>
          <div>
            <dt className="font-medium text-slate-500">File size</dt>
            <dd className="text-slate-900">{formatBytes(document.file_size_bytes)}</dd>
          </div>
          <div>
            <dt className="font-medium text-slate-500">Pages</dt>
            <dd className="text-slate-900">{document.page_count ?? "—"}</dd>
          </div>
          <div>
            <dt className="font-medium text-slate-500">Uploaded</dt>
            <dd className="text-slate-900">{formatDateTime(document.created_at)}</dd>
          </div>
        </dl>
      </Card>

      <Modal
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        title={`Delete “${document.title}”?`}
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

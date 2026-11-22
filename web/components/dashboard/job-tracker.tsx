"use client";

import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { JobStatusBadge, isJobActive } from "@/components/dashboard/job-status-badge";
import {
  ApiError,
  cancelJob,
  getJob,
  getSessionToken,
  retryJob,
} from "@/lib/api";

/**
 * Live job tracker: polls GET /api/v1/jobs/{id} while the job is
 * active (5 s, backoff to 15 s after 2 min) and stops on a
 * terminal state. Shows the engine's status, the engine's error
 * when failed, and the real Retry / Cancel actions. Never invents
 * a status.
 */
export function JobTracker({ jobId, documentId }: { jobId: string; documentId?: string }) {
  const queryClient = useQueryClient();
  const pollStartedAt = useRef<number | null>(null);

  const jobQuery = useQuery({
    queryKey: ["job", jobId],
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      return getJob(token, jobId);
    },
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (!isJobActive(status)) {
        pollStartedAt.current = null;
        return false;
      }
      if (pollStartedAt.current === null) pollStartedAt.current = Date.now();
      return Date.now() - pollStartedAt.current > 120_000 ? 15_000 : 5_000;
    },
  });
  const job = jobQuery.data;

  const [actionError, setActionError] = useState<string | null>(null);
  const [acting, setActing] = useState<"cancel" | "retry" | null>(null);

  async function act(kind: "cancel" | "retry") {
    setActionError(null);
    setActing(kind);
    try {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      if (kind === "cancel") await cancelJob(token, jobId);
      else await retryJob(token, jobId);
      await queryClient.invalidateQueries({ queryKey: ["job", jobId] });
      await queryClient.invalidateQueries({ queryKey: ["documents"] });
      await queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
      if (documentId) {
        await queryClient.invalidateQueries({ queryKey: ["document", documentId] });
      }
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
    }
  }

  if (jobQuery.isPending) {
    return (
      <div className="flex items-center gap-2 text-sm text-slate-600">
        <Spinner /> Checking job status…
      </div>
    );
  }

  if (jobQuery.isError || !job) {
    return (
      <Alert tone="danger" title="Could not load the job status">
        {(jobQuery.error as Error | null)?.message ??
          "The engine did not answer. Try again."}
      </Alert>
    );
  }

  const active = isJobActive(job.status);
  const retryable = job.status === "failed" || job.status === "cancelled";
  const cancellable = job.status === "queued" || job.status === "processing";

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <JobStatusBadge status={job.status} />
        {active ? (
          <span className="inline-flex items-center gap-2 text-sm text-slate-600">
            <Spinner /> Processing — this page updates automatically.
          </span>
        ) : null}
        {job.status === "done" && job.completed_at ? (
          <span className="text-sm text-slate-600">
            Finished {new Date(job.completed_at).toLocaleString()}.
          </span>
        ) : null}
      </div>
      {job.error ? (
        <Alert tone="danger" title="Processing failed">
          {job.error}
        </Alert>
      ) : null}
      {actionError ? (
        <Alert tone="danger" title="That action did not work">
          {actionError}
        </Alert>
      ) : null}
      <div className="flex flex-wrap gap-2">
        {cancellable ? (
          <Button
            variant="secondary"
            size="sm"
            disabled={acting !== null}
            onClick={() => act("cancel")}
          >
            {acting === "cancel" ? "Cancelling…" : "Cancel job"}
          </Button>
        ) : null}
        {retryable ? (
          <Button
            variant="secondary"
            size="sm"
            disabled={acting !== null}
            onClick={() => act("retry")}
          >
            {acting === "retry" ? "Retrying…" : "Retry job"}
          </Button>
        ) : null}
        {documentId ? (
          <Button variant="ghost" size="sm" href={`/dashboard/documents/${documentId}`}>
            View document
          </Button>
        ) : null}
      </div>
      {job.status === "done" ? (
        <p className="text-sm text-slate-600">
          Questions and answers for this document arrive in Milestone 5 — the
          question bank view.{" "}
          <Link href="/dashboard/documents" className="font-medium text-brand-700 underline">
            Back to documents
          </Link>
        </p>
      ) : null}
    </div>
  );
}

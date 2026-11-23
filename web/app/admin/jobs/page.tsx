// OfficerPath AI — admin jobs list + error surface (Phase 2,
// M9, GAP-10). Real rows from GET /api/v1/admin/jobs: every job
// with its status, error text, and how many processing_errors
// rows belong to it. The full error list lives at /admin/errors.

"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ErrorState, EmptyState } from "@/components/ui/empty-state";
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
import { ApiError, getSessionToken, listAdminJobs } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

const PAGE_SIZE = 20;
const STATUS_FILTERS = ["", "queued", "processing", "done", "failed", "cancelled"];

export default function AdminJobsPage() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const query = useQuery({
    queryKey: ["admin-jobs", page, status],
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new ApiError(401, "unauthorized", "Sign in to view the admin area.");
      return listAdminJobs(token, {
        status: status || undefined,
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
      });
    },
  });

  if (query.isPending) return <Spinner />;
  if (query.isError) {
    return (
      <ErrorState
        title="Jobs could not be loaded"
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
        title="Jobs"
        description={`${data.total} processing job${data.total === 1 ? "" : "s"}${status ? ` with status “${status}”` : ""}. Failed jobs and their error rows are listed here and in full under Errors.`}
      />
      <div className="mb-6 flex flex-wrap gap-2">
        {STATUS_FILTERS.map((s) => (
          <Button
            key={s || "all"}
            variant={status === s ? "primary" : "secondary"}
            size="sm"
            onClick={() => { setStatus(s); setPage(1); }}
          >
            {s === "" ? "All" : s}
          </Button>
        ))}
        <Link href="/admin/errors" className="ml-auto text-sm font-medium text-brand-700 underline">
          View all errors →
        </Link>
      </div>
      {data.items.length === 0 ? (
        <EmptyState title="No jobs found" description="Processing jobs appear here once a document is uploaded." />
      ) : (
        <Table>
          <TableHead>
            <TableRow>
              <TableHeaderCell>Document</TableHeaderCell>
              <TableHeaderCell>Status</TableHeaderCell>
              <TableHeaderCell>Errors</TableHeaderCell>
              <TableHeaderCell>Error</TableHeaderCell>
              <TableHeaderCell>Completed</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data.items.map((job) => (
              <TableRow key={job.id}>
                <TableCell>
                  <span className="font-medium text-slate-900">{job.document_title ?? job.document_id}</span>
                  {job.retry_count > 0 && (
                    <span className="block text-xs text-slate-500">Retries: {job.retry_count}</span>
                  )}
                </TableCell>
                <TableCell>
                  <Badge>{job.status}</Badge>
                </TableCell>
                <TableCell>{job.error_rows}</TableCell>
                <TableCell>
                  {job.error ? <span className="text-xs text-slate-600">{job.error}</span> : "—"}
                </TableCell>
                <TableCell>{job.completed_at ? formatDateTime(job.completed_at) : "—"}</TableCell>
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

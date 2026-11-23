// OfficerPath AI — admin error monitor (Phase 2, M9, GAP-10).
// Real rows from GET /api/v1/admin/errors: every recorded
// processing failure (processing_errors), newest first. Rows are
// written by the pipeline/worker, never by hand; this view only
// reads them.

"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
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
import { ApiError, getSessionToken, listAdminErrors } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

const PAGE_SIZE = 20;

export default function AdminErrorsPage() {
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: ["admin-errors", page],
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new ApiError(401, "unauthorized", "Sign in to view the admin area.");
      return listAdminErrors(token, { limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE });
    },
  });

  if (query.isPending) return <Spinner />;
  if (query.isError) {
    return (
      <ErrorState
        title="Errors could not be loaded"
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
        title="Processing errors"
        description={`${data.total} recorded error${data.total === 1 ? "" : "s"}. A failed page never fails the whole document silently — every failure is a row here.`}
      />
      {data.items.length === 0 ? (
        <EmptyState title="No errors recorded" description="Processing failures will appear here with their stage, code and message." />
      ) : (
        <Table>
          <TableHead>
            <TableRow>
              <TableHeaderCell>Document</TableHeaderCell>
              <TableHeaderCell>Stage</TableHeaderCell>
              <TableHeaderCell>Code</TableHeaderCell>
              <TableHeaderCell>Message</TableHeaderCell>
              <TableHeaderCell>When</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data.items.map((err) => (
              <TableRow key={err.id}>
                <TableCell>
                  <span className="font-medium text-slate-900">{err.document_title ?? err.document_id}</span>
                  {err.page_number !== null && err.page_number !== undefined && (
                    <span className="block text-xs text-slate-500">Page {err.page_number}</span>
                  )}
                </TableCell>
                <TableCell>{err.stage ?? "—"}</TableCell>
                <TableCell>{err.error_code}</TableCell>
                <TableCell>
                  <span className="text-xs text-slate-600">{err.message}</span>
                </TableCell>
                <TableCell>{err.created_at ? formatDateTime(err.created_at) : "—"}</TableCell>
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

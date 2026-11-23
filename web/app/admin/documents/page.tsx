// OfficerPath AI — admin documents list (Phase 2, M9, GAP-10).
// Real rows from GET /api/v1/admin/documents, with each
// document's latest job status.

"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
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
import { ApiError, getSessionToken, listAdminDocuments } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

const PAGE_SIZE = 20;

export default function AdminDocumentsPage() {
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: ["admin-documents", page],
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new ApiError(401, "unauthorized", "Sign in to view the admin area.");
      return listAdminDocuments(token, { limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE });
    },
  });

  if (query.isPending) return <Spinner />;
  if (query.isError) {
    return (
      <ErrorState
        title="Documents could not be loaded"
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
        title="Documents"
        description={`${data.total} document${data.total === 1 ? "" : "s"} uploaded by students.`}
      />
      {data.items.length === 0 ? (
        <EmptyState title="No documents yet" description="Uploaded documents appear here with their processing status." />
      ) : (
        <Table>
          <TableHead>
            <TableRow>
              <TableHeaderCell>Title</TableHeaderCell>
              <TableHeaderCell>Type</TableHeaderCell>
              <TableHeaderCell>Pages</TableHeaderCell>
              <TableHeaderCell>Job</TableHeaderCell>
              <TableHeaderCell>Uploaded</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data.items.map((doc) => (
              <TableRow key={doc.id}>
                <TableCell>
                  <span className="font-medium text-slate-900">{doc.title}</span>
                  {doc.deleted_at && <Badge>Deleted</Badge>}
                </TableCell>
                <TableCell>{doc.file_type}</TableCell>
                <TableCell>{doc.page_count ?? "—"}</TableCell>
                <TableCell>{doc.latest_job_status ?? "—"}</TableCell>
                <TableCell>{doc.created_at ? formatDateTime(doc.created_at) : "—"}</TableCell>
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

// OfficerPath AI — admin users list (Phase 2, M9, GAP-10).
//
// Real rows from GET /api/v1/admin/users: student profiles with
// per-user document/test counts. The engine stores NO student
// email, so none is shown here — the list never invents one
// (see the API report note).

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
import { ApiError, getSessionToken, listAdminUsers } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

const PAGE_SIZE = 20;

export default function AdminUsersPage() {
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: ["admin-users", page],
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new ApiError(401, "unauthorized", "Sign in to view the admin area.");
      return listAdminUsers(token, { limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE });
    },
  });

  if (query.isPending) return <Spinner />;
  if (query.isError) {
    return (
      <ErrorState
        title="Users could not be loaded"
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
        title="Students"
        description={`${data.total} student profile${data.total === 1 ? "" : "s"} in the engine database.`}
      />
      {data.items.length === 0 ? (
        <EmptyState title="No students yet" description="Student profiles appear here once someone registers and completes their profile." />
      ) : (
        <Table>
          <TableHead>
            <TableRow>
              <TableHeaderCell>Name</TableHeaderCell>
              <TableHeaderCell>Exam</TableHeaderCell>
              <TableHeaderCell>Documents</TableHeaderCell>
              <TableHeaderCell>Tests</TableHeaderCell>
              <TableHeaderCell>Joined</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data.items.map((user) => (
              <TableRow key={user.user_id}>
                <TableCell>
                  <span className="font-medium text-slate-900">{user.full_name}</span>
                  {user.phone && <span className="block text-xs text-slate-500">{user.phone}</span>}
                </TableCell>
                <TableCell>{user.preferred_exam ?? "—"}</TableCell>
                <TableCell>{user.documents}</TableCell>
                <TableCell>{user.tests}</TableCell>
                <TableCell>{user.created_at ? formatDateTime(user.created_at) : "—"}</TableCell>
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

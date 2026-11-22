"use client";

// OfficerPath AI — My Tests (Phase 2, M6).
//
// Real list from GET /api/v1/tests (paginated, owner-only).
// Delete is a real engine call and is only allowed before any
// attempt exists (the API enforces it with a 409). Taking a
// test is M7 — this page never pretends to start an exam.

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
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
import {
  ApiError,
  deleteTest,
  getSessionToken,
  listTests,
  markingLabel,
  type TestSummary,
} from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

const PAGE_SIZE = 20;

function statusTone(status: string): "success" | "info" | "accent" | "neutral" {
  switch (status) {
    case "created":
      return "info";
    case "in_progress":
      return "accent";
    case "submitted":
      return "success";
    default:
      return "neutral";
  }
}

export default function TestsPage() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [deleteTarget, setDeleteTarget] = useState<TestSummary | null>(null);
  const [deleteError, setDeleteError] = useState("");
  const [deleting, setDeleting] = useState(false);

  const listQuery = useQuery({
    queryKey: ["tests", page],
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      return listTests(token, { limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE });
    },
  });

  const totalPages = listQuery.data
    ? Math.max(1, Math.ceil(listQuery.data.total / PAGE_SIZE))
    : 1;

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    setDeleteError("");
    try {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      await deleteTest(token, deleteTarget.test_id);
      setDeleteTarget(null);
      await queryClient.invalidateQueries({ queryKey: ["tests"] });
    } catch (err) {
      setDeleteError(
        err instanceof ApiError
          ? err.message
          : "Could not delete this test. Please try again.",
      );
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="space-y-6">
      <SectionHeading
        title="My tests"
        description="Tests you built from your question bank. Each test keeps its own frozen copy of the questions — editing the bank never changes a test."
        level="h1"
        align="left"
      />

      <div>
        <Link href="/dashboard/tests/new">
          <Button>Build a new test</Button>
        </Link>
      </div>

      {listQuery.isPending ? (
        <div className="flex items-center gap-2 py-16 text-slate-600">
          <Spinner /> Loading your tests…
        </div>
      ) : listQuery.isError ? (
        <ErrorState
          title="Could not load your tests"
          description="The engine did not answer. Check your connection and try again."
          onRetry={() => listQuery.refetch()}
        />
      ) : listQuery.data.tests.length === 0 ? (
        <EmptyState
          title="No tests yet"
          description="Build your first test from the questions the engine extracted from your documents."
          actionLabel="Build a new test"
          actionHref="/dashboard/tests/new"
        />
      ) : (
        <>
          <Table>
            <TableHead>
              <TableRow>
                <TableHeaderCell>Test</TableHeaderCell>
                <TableHeaderCell>Questions</TableHeaderCell>
                <TableHeaderCell>Marking</TableHeaderCell>
                <TableHeaderCell>Status</TableHeaderCell>
                <TableHeaderCell>Created</TableHeaderCell>
                <TableHeaderCell>Actions</TableHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {listQuery.data.tests.map((test) => (
                <TableRow key={test.test_id}>
                  <TableCell>
                    <Link
                      href={`/dashboard/tests/${test.test_id}`}
                      className="font-medium text-brand-700 hover:underline"
                    >
                      {test.title}
                    </Link>
                  </TableCell>
                  <TableCell>{test.question_count}</TableCell>
                  <TableCell>
                    {test.marking_config.name} ({markingLabel(test.marking_config)})
                  </TableCell>
                  <TableCell>
                    <Badge tone={statusTone(test.status)}>{test.status}</Badge>
                  </TableCell>
                  <TableCell>{formatDateTime(test.created_at)}</TableCell>
                  <TableCell>
                    <div className="flex gap-2">
                      <Link href={`/dashboard/tests/${test.test_id}`}>
                        <Button variant="secondary">View</Button>
                      </Link>
                      <Button
                        variant="secondary"
                        disabled={test.status !== "created"}
                        title={
                          test.status !== "created"
                            ? "A test with an attempt cannot be deleted."
                            : undefined
                        }
                        onClick={() => {
                          setDeleteError("");
                          setDeleteTarget(test);
                        }}
                      >
                        Delete
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <Pagination
            page={page}
            totalPages={totalPages}
            onPageChange={setPage}
          />
        </>
      )}

      <Modal
        open={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        title="Delete this test?"
      >
        <p className="text-sm text-slate-700">
          {deleteTarget
            ? `“${deleteTarget.title}” and its ${deleteTarget.question_count} frozen questions will be deleted. This cannot be undone.`
            : ""}
        </p>
        {deleteError ? (
          <p className="mt-3 text-sm text-red-700">{deleteError}</p>
        ) : null}
        <div className="mt-5 flex gap-2">
          <Button variant="danger" disabled={deleting} onClick={confirmDelete}>
            {deleting ? "Deleting…" : "Delete test"}
          </Button>
          <Button variant="secondary" onClick={() => setDeleteTarget(null)}>
            Keep it
          </Button>
        </div>
      </Modal>
    </div>
  );
}

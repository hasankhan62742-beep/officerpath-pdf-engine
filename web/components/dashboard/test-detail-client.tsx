"use client";

// OfficerPath AI — test view / preview (Phase 2, M6; Start wired in M7).
//
// Read-only preview of a test's frozen snapshots, rendered with
// the shared truth-rule component (QuestionResultCard): an
// unknown answer renders as "Answer: unknown." and never as a
// correct option. The Start button activates the test on the
// server and routes to the exam page (M7).

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { Modal } from "@/components/ui/modal";
import { SectionHeading } from "@/components/ui/section-heading";
import { Spinner } from "@/components/ui/spinner";
import { QuestionResultCard } from "@/components/dashboard/question-result";
import {
  ApiError,
  deleteTest,
  getSessionToken,
  getTest,
  markingLabel,
  retryTest,
  startTest,
  type QuestionItem,
  type TestSnapshot,
} from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

function snapshotToQuestionItem(snap: TestSnapshot): QuestionItem {
  // The key is withheld (null) until the test is submitted:
  // never render a correct option, and never label the
  // question "unknown" when the key is merely hidden.
  const keyWithheld = snap.correct_index === null;
  return {
    question_id: snap.question_id ?? snap.snapshot_id,
    document_id: snap.source_document_id ?? "",
    document_title: "",
    number: String(snap.position),
    text: snap.question_text,
    options: snap.options.map((o) => o.text),
    kind: snap.options.length === 0 ? "qa_pair" : "mcq",
    correct_index: snap.correct_index,
    correct_letter:
      snap.correct_index !== null && snap.correct_index >= 0
        ? String.fromCharCode(65 + snap.correct_index)
        : "",
    answer_source: snap.answer_source ?? "",
    explanation: snap.explanation ?? null,
    confidence: null,
    verified: false,
    inferred: false,
    corrected: false,
    status: snap.is_unknown ? "unknown" : keyWithheld ? "withheld" : "answered",
    answer_status: keyWithheld ? "withheld" : snap.is_unknown ? "unknown" : "detected",
    page: snap.source_page,
    subjects: [],
    created_at: null,
  };
}

export function TestDetailClient({ id }: { id: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState("");
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState("");

  const testQuery = useQuery({
    queryKey: ["test", id],
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      return getTest(token, id);
    },
  });

  async function handleStart() {
    if (testQuery.data?.status === "in_progress") {
      router.push(`/dashboard/tests/${id}/take`);
      return;
    }
    setStarting(true);
    setStartError("");
    try {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      await startTest(token, id);
      router.push(`/dashboard/tests/${id}/take`);
    } catch (err) {
      setStartError(
        err instanceof ApiError
          ? err.message
          : "Could not start this test. Please try again.",
      );
    } finally {
      setStarting(false);
    }
  }

  async function handleRetry() {
    setRetrying(true);
    setRetryError("");
    try {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      const retried = await retryTest(token, id);
      await queryClient.invalidateQueries({ queryKey: ["tests"] });
      router.push(`/dashboard/tests/${retried.test_id}`);
    } catch (err) {
      setRetryError(
        err instanceof ApiError
          ? err.message
          : "Could not retry this test. Please try again.",
      );
    } finally {
      setRetrying(false);
    }
  }

  async function confirmDelete() {
    setDeleting(true);
    setDeleteError("");
    try {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      await deleteTest(token, id);
      await queryClient.invalidateQueries({ queryKey: ["tests"] });
      router.push("/dashboard/tests");
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

  if (testQuery.isPending) {
    return (
      <div className="flex items-center gap-2 py-16 text-slate-600">
        <Spinner /> Loading the test…
      </div>
    );
  }

  if (testQuery.isError || !testQuery.data) {
    return (
      <ErrorState
        title="Could not load this test"
        description="The engine did not answer, or this test does not exist."
        onRetry={() => testQuery.refetch()}
      />
    );
  }

  const test = testQuery.data;
  const unknownCount = test.snapshots.filter((s) => s.is_unknown).length;

  return (
    <div className="space-y-6">
      <SectionHeading
        title={test.title}
        description={test.description ?? "A test built from your question bank."}
        level="h1"
        align="left"
      />

      <div className="flex flex-wrap items-center gap-2 text-sm text-slate-700">
        <Badge tone="info">{test.status}</Badge>
        <span>
          {test.question_count} question{test.question_count === 1 ? "" : "s"}
        </span>
        <span>·</span>
        <span>
          Marking: {test.marking_config.name} ({markingLabel(test.marking_config)})
        </span>
        <span>·</span>
        <span>Created {formatDateTime(test.created_at)}</span>
      </div>

      <Alert tone="info" title="Preview — start the test to answer">
        These are the frozen questions this test will ask. Nothing here is an exam yet:
        your answers are not recorded and no score is calculated until you start the test.
        The answer key is hidden until you submit the test.
      </Alert>

      {startError ? (
        <Alert tone="danger" title="Could not start the test">
          {startError}
        </Alert>
      ) : null}

      {retryError ? (
        <Alert tone="danger" title="Could not retry the test">
          {retryError}
        </Alert>
      ) : null}

      {test.excluded_unknown > 0 || test.excluded_no_options > 0 ? (
        <p className="text-sm text-slate-600">
          When this test was built, {test.excluded_unknown} question
          {test.excluded_unknown === 1 ? "" : "s"} with unknown answers and{" "}
          {test.excluded_no_options} Q&amp;A pair
          {test.excluded_no_options === 1 ? "" : "s"} without options were left out of
          the selection pool.
          {unknownCount > 0
            ? ` ${unknownCount} unknown question${unknownCount === 1 ? " was" : "s were"} explicitly included and stay flagged as unknown below.`
            : ""}
        </p>
      ) : null}

      <div className="flex flex-wrap gap-2">
        {test.status === "submitted" ? (
          <>
            <Link href={`/dashboard/tests/${id}/result`}>
              <Button>View result</Button>
            </Link>
            <Button loading={retrying} onClick={handleRetry}>
              Retry this test
            </Button>
          </>
        ) : test.status === "expired" || test.status === "abandoned" ? (
          <Button disabled title="This test has ended.">
            This test has ended
          </Button>
        ) : (
          <Button loading={starting} onClick={handleStart}>
            {test.status === "in_progress" ? "Resume test" : "Start test"}
          </Button>
        )}
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
            setDeleteOpen(true);
          }}
        >
          Delete test
        </Button>
        <Link href="/dashboard/tests">
          <Button variant="secondary">Back to my tests</Button>
        </Link>
      </div>

      {test.snapshots.length === 0 ? (
        <EmptyState
          title="This test has no questions"
          description="The test was created without any frozen questions."
        />
      ) : (
        <div className="space-y-4">
          {test.snapshots.map((snap) => (
            <QuestionResultCard
              key={snap.snapshot_id}
              item={snapshotToQuestionItem(snap)}
              detailsHref={
                snap.question_id
                  ? `/dashboard/questions/${snap.question_id}`
                  : null
              }
            />
          ))}
        </div>
      )}

      <Modal open={deleteOpen} onClose={() => setDeleteOpen(false)} title="Delete this test?">
        <p className="text-sm text-slate-700">
          “{test.title}” and its {test.question_count} frozen questions will be deleted.
          This cannot be undone.
        </p>
        {deleteError ? (
          <p className="mt-3 text-sm text-red-700">{deleteError}</p>
        ) : null}
        <div className="mt-5 flex gap-2">
          <Button variant="danger" disabled={deleting} onClick={confirmDelete}>
            {deleting ? "Deleting…" : "Delete test"}
          </Button>
          <Button variant="secondary" onClick={() => setDeleteOpen(false)}>
            Keep it
          </Button>
        </div>
      </Modal>
    </div>
  );
}

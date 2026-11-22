"use client";

// OfficerPath AI — examination interface (Phase 2, M7, GAP-6).
//
// The timer is SERVER truth: the remaining time shown here comes
// only from the exam-session endpoint (server_started_at + the
// time limit) and is re-synced by polling every 10 seconds. The
// page never ticks from the browser clock and never trusts it —
// changing the browser clock cannot move the countdown. Answers
// save to the server immediately (debounced 400ms per question)
// and are mirrored to a local draft, so a refresh mid-test loses
// nothing: the page restores snapshots + saved answers +
// remaining time from the server on load.

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { Modal } from "@/components/ui/modal";
import { SectionHeading } from "@/components/ui/section-heading";
import { Spinner } from "@/components/ui/spinner";
import {
  ApiError,
  getExamSession,
  getSessionToken,
  getTestResult,
  saveAnswers,
  startTest,
  submitTest,
  type ExamResult,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type AnswerState = { selected_index: number | null; marked_for_review: boolean };
type DraftEntry = AnswerState & { at: number };
type SaveState = "idle" | "saving" | "saved" | "error";

const SAVE_DEBOUNCE_MS = 400;
const SAVE_RETRY_MS = 3000;
const MAX_SAVE_ATTEMPTS = 5;
const TIMER_POLL_MS = 10_000;

function draftKey(id: string) {
  return `officerpath-exam-draft-${id}`;
}

function readDraft(id: string): Record<string, DraftEntry> {
  try {
    const raw = localStorage.getItem(draftKey(id));
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, DraftEntry>;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function writeDraft(id: string, answers: Record<string, AnswerState>) {
  try {
    const stamped: Record<string, DraftEntry> = {};
    for (const [snapshotId, answer] of Object.entries(answers)) {
      stamped[snapshotId] = { ...answer, at: Date.now() };
    }
    localStorage.setItem(draftKey(id), JSON.stringify(stamped));
  } catch {
    // A draft that cannot be stored is not fatal — the server
    // save is the source of truth; the draft is only a cushion.
  }
}

function clearDraft(id: string) {
  try {
    localStorage.removeItem(draftKey(id));
  } catch {
    // ignore
  }
}

function formatRemaining(seconds: number | null): string {
  if (seconds === null) return "No time limit";
  const total = Math.max(0, seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return s === 0 ? `${m} min` : `${m} min ${s}s`;
}

export function ExamClient({ id }: { id: string }) {
  const queryClient = useQueryClient();
  const [current, setCurrent] = useState(0);
  const [answers, setAnswers] = useState<Record<string, AnswerState> | null>(null);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [saveMessage, setSaveMessage] = useState("");
  const [submitOpen, setSubmitOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [expiredNotice, setExpiredNotice] = useState(false);
  const [result, setResult] = useState<ExamResult | null>(null);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState("");

  const answersRef = useRef<Record<string, AnswerState> | null>(null);
  const lastSavedRef = useRef<Record<string, AnswerState>>({});
  const saveTimersRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const retryTimersRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const initializedRef = useRef(false);
  const autoSubmitRef = useRef(false);

  const examQuery = useQuery({
    queryKey: ["exam", id],
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      return getExamSession(token, id);
    },
    refetchInterval: (query) =>
      query.state.data?.status === "in_progress" ? TIMER_POLL_MS : false,
  });

  const exam = examQuery.data ?? null;
  const snapshots = useMemo(() => exam?.snapshots ?? [], [exam]);
  const currentSnap = snapshots[current] ?? null;

  const resultQuery = useQuery({
    queryKey: ["exam-result", id],
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      return getTestResult(token, id);
    },
    enabled: exam?.status === "submitted" && result === null,
    retry: false,
  });

  // The submitted result is shown from either the local submit
  // response or the stored-result query — no effect needed to
  // copy one into the other (the render derives it directly).
  const shownResult = result ?? resultQuery.data ?? null;

  useEffect(() => {
    answersRef.current = answers;
  }, [answers]);

  useEffect(() => {
    if (answers !== null) writeDraft(id, answers);
  }, [answers, id]);

  // Keep the save queue tidy when the component unmounts.
  useEffect(
    () => () => {
      for (const t of Object.values(saveTimersRef.current)) clearTimeout(t);
      for (const t of Object.values(retryTimersRef.current)) clearTimeout(t);
    },
    [],
  );

  async function doSave(snapshotId: string, attempt = 1): Promise<void> {
    const currentAnswers = answersRef.current;
    if (!currentAnswers) return;
    const answer = currentAnswers[snapshotId];
    if (!answer) return;
    setSaveState("saving");
    setSaveMessage("Saving…");
    try {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      const res = await saveAnswers(token, id, [
        {
          snapshot_id: snapshotId,
          selected_index: answer.selected_index,
          marked_for_review: answer.marked_for_review,
        },
      ]);
      lastSavedRef.current = { ...lastSavedRef.current, [snapshotId]: { ...answer } };
      setSaveState("saved");
      setSaveMessage("All answers saved.");
      if (res.status === "expired") {
        setExpiredNotice(true);
      }
    } catch (err) {
      if (err instanceof ApiError && err.code === "time_expired") {
        setExpiredNotice(true);
        setSaveState("error");
        setSaveMessage("Time expired — your saved answers will be submitted.");
        return;
      }
      if (attempt < MAX_SAVE_ATTEMPTS) {
        setSaveState("error");
        setSaveMessage("Couldn’t save — retrying…");
        retryTimersRef.current[snapshotId] = setTimeout(
          () => void doSave(snapshotId, attempt + 1),
          SAVE_RETRY_MS * attempt,
        );
      } else {
        setSaveState("error");
        setSaveMessage(
          "Couldn’t save — check your connection, then use “Retry saving” below.",
        );
      }
    }
  }

  function queueSave(snapshotId: string) {
    const existing = saveTimersRef.current[snapshotId];
    if (existing) clearTimeout(existing);
    saveTimersRef.current[snapshotId] = setTimeout(() => void doSave(snapshotId, 1), SAVE_DEBOUNCE_MS);
  }

  function retryAllUnsaved() {
    const currentAnswers = answersRef.current;
    if (!currentAnswers) return;
    setSaveState("saving");
    setSaveMessage("Retrying…");
    for (const [snapshotId, answer] of Object.entries(currentAnswers)) {
      const saved = lastSavedRef.current[snapshotId];
      if (
        !saved ||
        saved.selected_index !== answer.selected_index ||
        saved.marked_for_review !== answer.marked_for_review
      ) {
        void doSave(snapshotId, 1);
      }
    }
  }

  // First load: initialise answers from the server, then merge
  // any local draft entries the server does not have yet (a save
  // that was in flight when the page was refreshed). The server
  // wins where it already has a newer answer.
  useEffect(() => {
    if (initializedRef.current || !exam) return;
    initializedRef.current = true;
    const fromServer: Record<string, AnswerState> = {};
    for (const r of exam.responses) {
      fromServer[r.snapshot_id] = {
        selected_index: r.selected_index,
        marked_for_review: r.marked_for_review,
      };
      lastSavedRef.current[r.snapshot_id] = {
        selected_index: r.selected_index,
        marked_for_review: r.marked_for_review,
      };
    }
    const draft = readDraft(id);
    const merged = { ...fromServer };
    const toResend: string[] = [];
    for (const [snapshotId, entry] of Object.entries(draft)) {
      const server = exam.responses.find((r) => r.snapshot_id === snapshotId);
      const serverAt = server?.updated_at ? Date.parse(server.updated_at) : 0;
      if (!server || entry.at > serverAt) {
        merged[snapshotId] = {
          selected_index: entry.selected_index,
          marked_for_review: entry.marked_for_review,
        };
        toResend.push(snapshotId);
      }
    }
    setAnswers(merged);
    if (exam.status === "in_progress") {
      for (const snapshotId of toResend) queueSave(snapshotId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [exam]);

  // Time expired on the server: lock the exam and submit what
  // was saved (once).
  useEffect(() => {
    if (exam?.status === "expired" && result === null && !autoSubmitRef.current) {
      autoSubmitRef.current = true;
      setExpiredNotice(true);
      void doSubmit();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [exam?.status]);

  function updateAnswer(snapshotId: string, patch: Partial<AnswerState>) {
    setAnswers((prev) => {
      if (!prev) return prev;
      const current = prev[snapshotId] ?? { selected_index: null, marked_for_review: false };
      return { ...prev, [snapshotId]: { ...current, ...patch } };
    });
    queueSave(snapshotId);
  }

  async function doSubmit() {
    setSubmitting(true);
    setSubmitError("");
    try {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      const res = await submitTest(token, id);
      setResult(res);
      clearDraft(id);
      await queryClient.invalidateQueries({ queryKey: ["tests"] });
      await queryClient.invalidateQueries({ queryKey: ["exam", id] });
    } catch (err) {
      setSubmitError(
        err instanceof ApiError ? err.message : "Could not submit this test. Please try again.",
      );
    } finally {
      setSubmitting(false);
      setSubmitOpen(false);
    }
  }

  async function handleStart() {
    setStarting(true);
    setStartError("");
    try {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      await startTest(token, id);
      await examQuery.refetch();
    } catch (err) {
      setStartError(
        err instanceof ApiError ? err.message : "Could not start this test. Please try again.",
      );
    } finally {
      setStarting(false);
    }
  }

  const counts = useMemo(() => {
    let answered = 0;
    let marked = 0;
    let unknown = 0;
    for (const snap of snapshots) {
      if (snap.correct_index < 0) unknown += 1;
      const answer = answers?.[snap.snapshot_id];
      if (answer?.selected_index !== null && answer?.selected_index !== undefined) answered += 1;
      if (answer?.marked_for_review) marked += 1;
    }
    return { answered, marked, unknown, unanswered: snapshots.length - answered };
  }, [snapshots, answers]);

  if (examQuery.isPending) {
    return (
      <div className="flex items-center gap-2 py-16 text-slate-600">
        <Spinner /> Loading the exam…
      </div>
    );
  }

  if (examQuery.isError || !exam) {
    return (
      <ErrorState
        title="Could not load this exam"
        description="The engine did not answer, or this test does not exist."
        onRetry={() => examQuery.refetch()}
      />
    );
  }

  // Submitted: show the server-returned marks summary (counts +
  // total marks only — analytics and history are M8).
  if (exam.status === "submitted" || shownResult) {
    const shown = shownResult;
    if (!shown) {
      return (
        <div className="flex items-center gap-2 py-16 text-slate-600">
          <Spinner /> Loading your result…
        </div>
      );
    }
    return (
      <div className="space-y-6">
        <SectionHeading title={shown.title} description="Your test is submitted." level="h1" align="left" />
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <p className="text-sm text-slate-600">Total marks</p>
          <p className="mt-1 text-4xl font-bold text-slate-900">
            {shown.total_marks} <span className="text-xl font-semibold text-slate-500">/ {shown.max_marks}</span>
          </p>
          <p className="mt-1 text-sm text-slate-600">{shown.percentage}% · Time taken {formatDuration(shown.time_taken_seconds)}</p>
          <div className="mt-4 flex flex-wrap gap-2 text-sm">
            <Badge tone="success">Correct: {shown.correct}</Badge>
            <Badge tone="danger">Incorrect: {shown.incorrect}</Badge>
            <Badge tone="info">Unattempted: {shown.unattempted}</Badge>
            {shown.unknown_count > 0 ? (
              <Badge tone="neutral">
                {shown.unknown_count} question{shown.unknown_count === 1 ? "" : "s"} had no known answer and {shown.unknown_count === 1 ? "was" : "were"} not scored
              </Badge>
            ) : null}
          </div>
          <p className="mt-4 text-sm text-slate-600">
            {shown.total_questions} questions · Marking: {shown.marking_config.name} (
            {shown.marking_config.correct_marks > 0 ? "+" : ""}
            {shown.marking_config.correct_marks} / {shown.marking_config.incorrect_marks} /{" "}
            {shown.marking_config.unattempted_marks})
          </p>
          <p className="mt-2 text-sm text-slate-500">
            Detailed review, per-subject breakdown and history arrive in Milestone 8.
          </p>
        </div>
        <Link href="/dashboard/tests">
          <Button variant="secondary">Back to my tests</Button>
        </Link>
      </div>
    );
  }

  // Not started yet (opened the exam URL directly): start here.
  if (exam.status === "created") {
    return (
      <div className="space-y-6">
        <SectionHeading title={exam.title} description="This test has not started yet." level="h1" align="left" />
        {startError ? (
          <Alert tone="danger" title="Could not start the test">
            {startError}
          </Alert>
        ) : null}
        <p className="text-sm text-slate-600">
          {exam.snapshots.length} questions · Marking: {exam.marking_config.name} ·{" "}
          {exam.time_limit_seconds !== null
            ? `Time limit: ${formatDuration(exam.time_limit_seconds)} (counted from the server, not your device clock).`
            : "No time limit."}
        </p>
        <Button loading={starting} onClick={handleStart}>
          Start test
        </Button>
      </div>
    );
  }

  // Expired without a result yet: offer the submit of saved answers.
  if (exam.status === "expired" && !result) {
    return (
      <div className="space-y-6">
        <SectionHeading title={exam.title} description="The time for this test has expired." level="h1" align="left" />
        <Alert tone="warning" title="Time expired">
          No more answers can be saved. Your saved answers are kept — submit them to get your marks.
        </Alert>
        {submitError ? (
          <Alert tone="danger" title="Could not submit">
            {submitError}
          </Alert>
        ) : null}
        <div className="flex flex-wrap gap-2">
          <Button loading={submitting} onClick={() => void doSubmit()}>
            Submit saved answers
          </Button>
          <Link href="/dashboard/tests">
            <Button variant="secondary">Back to my tests</Button>
          </Link>
        </div>
      </div>
    );
  }

  if (snapshots.length === 0) {
    return (
      <EmptyState
        title="This test has no questions"
        description="The test was created without any frozen questions."
      />
    );
  }

  const answer = currentSnap ? (answers?.[currentSnap.snapshot_id] ?? { selected_index: null, marked_for_review: false }) : null;
  const isUnknown = currentSnap ? currentSnap.correct_index < 0 : false;
  const hasNoOptions = currentSnap ? currentSnap.options.length === 0 : false;
  const locked = exam.status !== "in_progress";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <SectionHeading title={exam.title} description="Answer each question. Your answers save as you go." level="h1" align="left" />
        <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-right shadow-sm">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Time remaining</p>
          <p className="text-2xl font-bold tabular-nums text-slate-900" data-testid="remaining-time">
            {formatRemaining(exam.remaining_seconds)}
          </p>
          <p className="text-xs text-slate-500">from the server · syncs every 10s</p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-sm text-slate-700">
        <span data-testid="progress">
          Answered {counts.answered} of {snapshots.length}
        </span>
        <span>·</span>
        <span>Unanswered {counts.unanswered}</span>
        <span>·</span>
        <span>Marked for review {counts.marked}</span>
        {counts.unknown > 0 ? (
          <>
            <span>·</span>
            <span>{counts.unknown} not scored (answer unknown)</span>
          </>
        ) : null}
      </div>

      <p className="text-sm" data-testid="save-state" aria-live="polite">
        {saveState === "saving" && <span className="text-slate-600">{saveMessage}</span>}
        {saveState === "saved" && <span className="text-green-700">{saveMessage}</span>}
        {saveState === "error" && (
          <span className="text-red-700">
            {saveMessage}{" "}
            <button type="button" className="font-semibold underline" onClick={retryAllUnsaved}>
              Retry saving
            </button>
          </span>
        )}
        {saveState === "idle" && <span className="text-slate-500">Answers save automatically.</span>}
      </p>

      {expiredNotice ? (
        <Alert tone="warning" title="Time expired">
          The server says the time is up. Submitting your saved answers…
        </Alert>
      ) : null}
      {submitError ? (
        <Alert tone="danger" title="Could not submit">
          {submitError}
        </Alert>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-[1fr_280px]">
        <div className="space-y-4">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone="info">
                Question {current + 1} of {snapshots.length}
              </Badge>
              {isUnknown ? <Badge tone="neutral">Answer unknown — not scored</Badge> : null}
              {answer?.marked_for_review ? <Badge tone="accent">Marked for review</Badge> : null}
            </div>
            <p className="mt-3 text-base font-medium leading-relaxed text-slate-900">
              {currentSnap?.question_text}
            </p>

            {hasNoOptions ? (
              <p className="mt-4 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-600">
                This question has no options — it is shown as a question &amp; answer pair and is
                not scored.
              </p>
            ) : (
              <div className="mt-4 space-y-2" role="radiogroup" aria-label={`Options for question ${current + 1}`}>
                {currentSnap?.options.map((option, index) => {
                  const selected = answer?.selected_index === index;
                  return (
                    <button
                      key={option.label}
                      type="button"
                      role="radio"
                      aria-checked={selected}
                      disabled={locked || isUnknown}
                      title={isUnknown ? "This question has no known answer, so it is not scored." : undefined}
                      onClick={() => updateAnswer(currentSnap.snapshot_id, { selected_index: index })}
                      className={cn(
                        "flex w-full items-start gap-3 rounded-xl border px-4 py-3 text-left text-sm transition-colors",
                        "disabled:cursor-not-allowed",
                        selected
                          ? "border-brand-600 bg-brand-50 ring-1 ring-brand-600"
                          : "border-slate-300 bg-white hover:border-slate-400",
                        isUnknown && "opacity-60",
                      )}
                    >
                      <span
                        className={cn(
                          "mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-xs font-bold",
                          selected ? "border-brand-600 bg-brand-600 text-white" : "border-slate-400 text-slate-700",
                        )}
                      >
                        {option.label}
                      </span>
                      <span className="leading-relaxed text-slate-900">{option.text}</span>
                    </button>
                  );
                })}
              </div>
            )}
            {isUnknown && !hasNoOptions ? (
              <p className="mt-3 text-sm text-slate-600">
                This question has no known answer. You can still mark it for review, but it will
                never count for or against your marks.
              </p>
            ) : null}
          </div>

          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              disabled={current === 0}
              onClick={() => setCurrent((c) => Math.max(0, c - 1))}
            >
              Previous
            </Button>
            <Button
              variant="secondary"
              disabled={current >= snapshots.length - 1}
              onClick={() => setCurrent((c) => Math.min(snapshots.length - 1, c + 1))}
            >
              Next
            </Button>
            <Button
              variant="secondary"
              disabled={locked || !currentSnap}
              onClick={() =>
                currentSnap &&
                updateAnswer(currentSnap.snapshot_id, {
                  marked_for_review: !(answer?.marked_for_review ?? false),
                })
              }
            >
              {answer?.marked_for_review ? "Unmark review" : "Mark for review"}
            </Button>
            <Button
              variant="ghost"
              disabled={locked || !currentSnap || answer?.selected_index === null}
              onClick={() => currentSnap && updateAnswer(currentSnap.snapshot_id, { selected_index: null })}
            >
              Clear response
            </Button>
            <Button variant="success" disabled={locked} onClick={() => setSubmitOpen(true)}>
              Submit test
            </Button>
          </div>
        </div>

        <aside className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm" aria-label="Question palette">
          <p className="text-sm font-semibold text-slate-900">Questions</p>
          <p className="mt-1 text-xs text-slate-500">
            Green = answered · amber ring = marked for review · grey = answer unknown
          </p>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {snapshots.map((snap, index) => {
              const snapAnswer = answers?.[snap.snapshot_id];
              const isAnswered = snapAnswer?.selected_index !== null && snapAnswer?.selected_index !== undefined;
              const isMarked = snapAnswer?.marked_for_review === true;
              const isCurrent = index === current;
              const snapUnknown = snap.correct_index < 0;
              return (
                <button
                  key={snap.snapshot_id}
                  type="button"
                  onClick={() => setCurrent(index)}
                  aria-label={`Question ${index + 1}${isAnswered ? ", answered" : ", unanswered"}${isMarked ? ", marked for review" : ""}${snapUnknown ? ", answer unknown" : ""}`}
                  aria-current={isCurrent}
                  className={cn(
                    "flex h-10 w-10 items-center justify-center rounded-lg border text-sm font-semibold transition-colors",
                    isAnswered
                      ? "border-green-700 bg-green-600 text-white"
                      : "border-slate-300 bg-white text-slate-800 hover:border-slate-400",
                    snapUnknown && !isAnswered && "bg-slate-100 text-slate-500",
                    isMarked && "ring-2 ring-amber-500 ring-offset-1",
                    isCurrent && "ring-2 ring-brand-600 ring-offset-1",
                  )}
                >
                  {index + 1}
                </button>
              );
            })}
          </div>
        </aside>
      </div>

      <Modal open={submitOpen} onClose={() => setSubmitOpen(false)} title="Submit this test?">
        <p>
          You have answered <strong>{counts.answered}</strong> of {snapshots.length} questions.{" "}
          <strong>{counts.unanswered}</strong> unanswered and <strong>{counts.marked}</strong>{" "}
          marked for review.
          {counts.unknown > 0
            ? ` ${counts.unknown} question${counts.unknown === 1 ? " has" : "s have"} no known answer and will not be scored.`
            : ""}
        </p>
        <p className="mt-2">
          Once submitted, your answers cannot be changed. Marks are calculated on the server.
        </p>
        {submitError ? <p className="mt-3 text-sm text-red-700">{submitError}</p> : null}
        <div className="mt-5 flex gap-2">
          <Button variant="success" loading={submitting} onClick={() => void doSubmit()}>
            {submitting ? "Submitting…" : "Submit test"}
          </Button>
          <Button variant="secondary" onClick={() => setSubmitOpen(false)}>
            Keep answering
          </Button>
        </div>
      </Modal>

      <Link href="/dashboard/tests">
        <Button variant="ghost">Back to my tests</Button>
      </Link>
    </div>
  );
}

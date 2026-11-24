"use client";

// OfficerPath AI — question detail (Phase 2, M5).
//
// One extracted question with its full evidence trail, its
// correction history, manual subject assignment, and the
// correction form. A correction is a NEW audit entry — the
// original extraction is never overwritten, and the history
// below is the real audit trail from the engine.

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { SectionHeading } from "@/components/ui/section-heading";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import {
  AnswerLine,
  QuestionBadges,
  QuestionOptions,
} from "@/components/dashboard/question-result";
import {
  ApiError,
  assignSubject,
  getQuestion,
  getSessionToken,
  listSubjects,
  submitCorrection,
  unassignSubject,
} from "@/lib/api";
import { formatMathText } from "@/lib/mathText";
import { formatDateTime } from "@/lib/utils";

const ANSWER_LETTERS = ["A", "B", "C", "D"];

export function QuestionDetailClient({ id }: { id: string }) {
  const queryClient = useQueryClient();
  const [field, setField] = useState<string>("answer");
  const [answerLetter, setAnswerLetter] = useState("A");
  const [textValue, setTextValue] = useState("");
  const [reason, setReason] = useState("");
  const [correcting, setCorrecting] = useState(false);
  const [correctionError, setCorrectionError] = useState<string | null>(null);
  const [correctionDone, setCorrectionDone] = useState<string | null>(null);
  const [subjectPick, setSubjectPick] = useState("");
  const [assigning, setAssigning] = useState(false);
  const [subjectError, setSubjectError] = useState<string | null>(null);

  const detailQuery = useQuery({
    queryKey: ["question", id],
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      return getQuestion(token, id);
    },
  });

  const subjectsQuery = useQuery({
    queryKey: ["subjects"],
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      return listSubjects(token);
    },
  });

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: ["question", id] });
    await queryClient.invalidateQueries({ queryKey: ["questions"] });
    await queryClient.invalidateQueries({
      queryKey: ["document-questions"],
    });
  }

  async function submit() {
    setCorrectionError(null);
    setCorrectionDone(null);
    const detail = detailQuery.data;
    if (!detail) return;
    const newValue = field === "answer" ? answerLetter : textValue.trim();
    if (!newValue) {
      setCorrectionError("Write the corrected value first.");
      return;
    }
    setCorrecting(true);
    try {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      const result = await submitCorrection(
        token,
        detail.document_id,
        detail.question_id,
        field,
        newValue,
        reason.trim(),
      );
      setCorrectionDone(
        `Saved: ${result.field} changed from “${result.old_value ?? "—"}” to “${result.new_value}”. The original extraction is untouched — this is a new audit entry.`,
      );
      setTextValue("");
      setReason("");
      await refresh();
    } catch (err) {
      setCorrectionError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "That correction did not save. Please try again.",
      );
    } finally {
      setCorrecting(false);
    }
  }

  async function assign() {
    setSubjectError(null);
    if (!subjectPick || !detailQuery.data) return;
    setAssigning(true);
    try {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      const result = await assignSubject(token, detailQuery.data.question_id, subjectPick);
      if (result.already_assigned) setSubjectError("That subject is already assigned.");
      setSubjectPick("");
      await refresh();
    } catch (err) {
      setSubjectError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "That assignment did not save. Please try again.",
      );
    } finally {
      setAssigning(false);
    }
  }

  async function unassign(subjectId: string) {
    if (!detailQuery.data) return;
    try {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      await unassignSubject(token, detailQuery.data.question_id, subjectId);
      await refresh();
    } catch {
      setSubjectError("That subject could not be removed. Please try again.");
    }
  }

  if (detailQuery.isPending) {
    return (
      <div className="flex items-center gap-2 py-16 text-slate-600">
        <Spinner /> Loading the question…
      </div>
    );
  }

  if (detailQuery.isError || !detailQuery.data) {
    const status = (detailQuery.error as ApiError | null)?.status;
    return (
      <ErrorState
        title={status === 404 ? "Question not found" : "Could not load the question"}
        description={
          status === 404
            ? "It may belong to another document, or the link is wrong."
            : ((detailQuery.error as Error | null)?.message ??
              "The engine did not answer. Check that it is running and try again.")
        }
        onRetry={() => detailQuery.refetch()}
      />
    );
  }

  const item = detailQuery.data;
  const optionFields = item.options.map((_, i) => `option_text:${i}`);

  return (
    <div className="space-y-8">
      <div>
        <Link
          href="/dashboard/questions"
          className="text-sm font-medium text-brand-700 hover:underline"
        >
          ← Question bank
        </Link>
        <div className="mt-2">
          <SectionHeading
            title={item.number ? `Question ${item.number}` : "Question"}
            description={`From ${item.document_title}${item.page ? ` · page ${item.page}` : ""}`}
            level="h1"
            align="left"
          />
        </div>
      </div>

      <Card className="p-5">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <QuestionBadges item={item} />
          <Link
            href={`/dashboard/documents/${item.document_id}`}
            className="text-sm font-medium text-brand-700 hover:underline"
          >
            View document →
          </Link>
        </div>
        <p className="mt-3 text-base leading-relaxed text-slate-900" dir="auto">
          {formatMathText(item.text)}
        </p>
        <QuestionOptions item={item} />
        <AnswerLine item={item} />
      </Card>

      <Card className="p-5">
        <CardTitle>Evidence trail</CardTitle>
        <CardDescription>
          Why the engine chose this answer — each detector that voted,
          in the order recorded. An unknown answer has no evidence
          because no detector claimed it.
        </CardDescription>
        {item.evidence.length === 0 ? (
          <p className="mt-3 text-sm text-slate-600">
            No evidence recorded for this question.
          </p>
        ) : (
          <ul className="mt-3 space-y-2">
            {item.evidence.map((ev, i) => (
              <li
                key={`${ev.detector}-${i}`}
                className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800"
              >
                <span className="font-semibold">{ev.detector}</span>
                {ev.value_normalized ? ` → ${ev.value_normalized}` : ""}
                {ev.detector_confidence !== null
                  ? ` · confidence ${Math.round(ev.detector_confidence * 100)}%`
                  : ""}
                {ev.page_number !== null ? ` · page ${ev.page_number}` : ""}
                {ev.artifact_ref ? (
                  <span className="block text-xs text-slate-500">
                    {ev.artifact_ref}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card className="p-5">
        <CardTitle>Correct this question</CardTitle>
        <CardDescription>
          Fix an answer, an option, or the question text. The original
          extraction is never overwritten — your correction is recorded
          as a new version with the old and new values below.
        </CardDescription>
        {correctionError ? (
          <Alert tone="danger" title="That correction did not save" className="mt-3">
            {correctionError}
          </Alert>
        ) : null}
        {correctionDone ? (
          <Alert tone="info" title="Correction saved" className="mt-3">
            {correctionDone}
          </Alert>
        ) : null}
        <div className="mt-4 space-y-4">
          <div>
            <label
              htmlFor="correction-field"
              className="text-sm font-medium text-slate-700"
            >
              What to correct
            </label>
            <select
              id="correction-field"
              className="mt-1 min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm"
              value={field}
              onChange={(e) => setField(e.target.value)}
            >
              <option value="answer">Answer (letter)</option>
              <option value="question_text">Question text</option>
              {optionFields.map((f, i) => (
                <option key={f} value={f}>
                  Option {String.fromCharCode(65 + i)} text
                </option>
              ))}
            </select>
          </div>
          {field === "answer" ? (
            <div>
              <label
                htmlFor="correction-answer"
                className="text-sm font-medium text-slate-700"
              >
                Correct answer
              </label>
              <select
                id="correction-answer"
                className="mt-1 min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm"
                value={answerLetter}
                onChange={(e) => setAnswerLetter(e.target.value)}
              >
                {ANSWER_LETTERS.slice(0, Math.max(item.options.length, 1)).map(
                  (letter) => (
                    <option key={letter} value={letter}>
                      {letter}
                      {item.options[letter.charCodeAt(0) - 65]
                        ? ` — ${formatMathText(item.options[letter.charCodeAt(0) - 65])}`
                        : ""}
                    </option>
                  ),
                )}
              </select>
            </div>
          ) : (
            <Textarea
              label="Corrected text"
              id="correction-text"
              value={textValue}
              onChange={(e) => setTextValue(e.target.value)}
              placeholder="Write the corrected text exactly as it should read…"
            />
          )}
          <Input
            label="Reason (optional)"
            id="correction-reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. checked against the answer key"
          />
          <Button disabled={correcting} loading={correcting} onClick={submit}>
            Save correction
          </Button>
        </div>
      </Card>

      <Card className="p-5">
        <CardTitle>Correction history</CardTitle>
        <CardDescription>
          Every manual correction for this question, newest first.
        </CardDescription>
        {item.corrections.length === 0 ? (
          <p className="mt-3 text-sm text-slate-600">
            No corrections yet — the extraction stands as the engine
            returned it.
          </p>
        ) : (
          <ul className="mt-3 space-y-2">
            {item.corrections.map((c) => (
              <li
                key={c.id}
                className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800"
              >
                <span className="font-semibold">{c.field_name}</span>
                {": “"}
                {c.old_value ?? "—"}
                {"” → “"}
                {c.new_value ?? "—"}
                {"”"}
                {c.reason ? <span className="text-slate-600"> ({c.reason})</span> : null}
                <span className="block text-xs text-slate-500">
                  {c.created_at ? formatDateTime(c.created_at) : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card className="p-5">
        <CardTitle>Subject</CardTitle>
        <CardDescription>
          Subjects are assigned by hand — the engine does not guess
          them. A question with no subject is simply uncategorised.
        </CardDescription>
        {subjectError ? (
          <Alert tone="danger" title="That did not save" className="mt-3">
            {subjectError}
          </Alert>
        ) : null}
        <div className="mt-3 flex flex-wrap gap-2">
          {item.subjects.length === 0 ? (
            <span className="text-sm text-slate-600">Uncategorised</span>
          ) : (
            item.subjects.map((s) => (
              <span
                key={s.subject_id}
                className="inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-800 ring-1 ring-inset ring-slate-200"
              >
                {s.subject_name}
                <button
                  type="button"
                  aria-label={`Remove ${s.subject_name}`}
                  className="font-bold text-slate-500 hover:text-danger-700"
                  onClick={() => unassign(s.subject_id)}
                >
                  ×
                </button>
              </span>
            ))
          )}
        </div>
        <div className="mt-4 flex flex-wrap items-end gap-2">
          <div className="min-w-56">
            <label
              htmlFor="subject-pick"
              className="text-sm font-medium text-slate-700"
            >
              Assign a subject
            </label>
            <select
              id="subject-pick"
              className="mt-1 min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm"
              value={subjectPick}
              onChange={(e) => setSubjectPick(e.target.value)}
            >
              <option value="">Choose a subject…</option>
              {(subjectsQuery.data?.subjects ?? []).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
          <Button
            variant="secondary"
            disabled={assigning || !subjectPick}
            loading={assigning}
            onClick={assign}
          >
            Assign subject
          </Button>
        </div>
      </Card>
    </div>
  );
}

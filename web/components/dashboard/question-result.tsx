"use client";

// OfficerPath AI — shared question rendering (Phase 2, M5).
//
// The truth rules live here, once, so no view can drift:
// - correct_index -1 renders as UNKNOWN: no option is ever
//   highlighted as correct, and the answer line says so plainly.
// - An inferred answer always carries a visible "Inferred" flag
//   and is never shown as verified.
// - A question with no options (Q&A pair) is shown as Q&A —
//   options are never invented or padded to four.

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { answerSourceLabel, type QuestionItem } from "@/lib/api";
import { formatMathText } from "@/lib/mathText";

const OPTION_LETTERS = ["A", "B", "C", "D", "E", "F", "G", "H"];

function answerStatusBadge(item: QuestionItem) {
  switch (item.answer_status) {
    case "verified":
      return <Badge tone="success">Verified answer</Badge>;
    case "detected":
      return <Badge tone="info">Detected answer</Badge>;
    case "needs_review":
      return <Badge tone="accent">Needs review</Badge>;
    case "conflicting":
      return <Badge tone="danger">Conflicting</Badge>;
    case "withheld":
      return <Badge tone="neutral">Answer hidden</Badge>;
    default:
      return <Badge tone="neutral">Unknown answer</Badge>;
  }
}

export function QuestionBadges({ item }: { item: QuestionItem }) {
  return (
    <span className="flex flex-wrap items-center gap-1.5">
      {answerStatusBadge(item)}
      {item.inferred ? <Badge tone="accent">Inferred</Badge> : null}
      {item.corrected ? <Badge tone="brand">Corrected</Badge> : null}
      {item.subjects.map((s) => (
        <Badge key={s.subject_id} tone="neutral">
          {s.subject_name}
        </Badge>
      ))}
    </span>
  );
}

export function QuestionOptions({ item }: { item: QuestionItem }) {
  if (item.options.length === 0) {
    return (
      <p className="text-sm text-slate-600">
        Q&amp;A pair — this question has no options by design. The
        answer is free text, not one of four choices.
      </p>
    );
  }
  const known = item.correct_index !== null && item.correct_index >= 0;
  return (
    <ul className="mt-3 space-y-2">
      {item.options.map((option, index) => {
        const isCorrect = known && index === item.correct_index;
        return (
          <li
            key={index}
            className={
              isCorrect
                ? "rounded-lg border border-success-300 bg-success-50 px-3 py-2 text-sm text-slate-900"
                : "rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800"
            }
          >
            <span className="mr-2 font-semibold">
              {OPTION_LETTERS[index] ?? `(${index + 1})`}.
            </span>
            {formatMathText(option)}
            {isCorrect ? (
              <span className="ml-2 font-semibold text-success-800">— correct</span>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

export function AnswerLine({ item }: { item: QuestionItem }) {
  if (item.correct_index === null) {
    return (
      <p className="mt-3 text-sm text-slate-600">
        <strong>Answer hidden.</strong> The answer key is revealed
        after the test is submitted — it is never shown while a
        test is still open.
      </p>
    );
  }
  if (item.correct_index < 0) {
    return (
      <p className="mt-3 text-sm text-slate-600">
        <strong>Answer: unknown.</strong> The engine could not
        determine the answer for this question — no option is marked
        correct.
        {item.status === "pending"
          ? " It is still waiting for review."
          : null}
      </p>
    );
  }
  return (
    <p className="mt-3 text-sm text-slate-700">
      <strong>
        Answer: {item.correct_letter}
        {item.options[item.correct_index]
          ? ` — ${formatMathText(item.options[item.correct_index])}`
          : ""}
      </strong>
      {" · "}
      {answerSourceLabel(item.answer_source)}
      {item.confidence !== null
        ? ` · confidence ${Math.round(item.confidence * 100)}%`
        : ""}
      {item.inferred
        ? " · Inferred — the lowest-confidence source; treat this answer as unverified."
        : ""}
    </p>
  );
}

/** One extracted question, rendered with the truth rules.
 *
 * ``detailsHref`` overrides the "Evidence, corrections &
 * details" link (default: the bank question page). Pass null
 * to hide the link — e.g. for a test snapshot whose source
 * question was deleted, where the bank page no longer exists.
 */
export function QuestionResultCard({
  item,
  showDocument = false,
  detailsHref,
}: {
  item: QuestionItem;
  showDocument?: boolean;
  detailsHref?: string | null;
}) {
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="text-base font-semibold text-slate-900">
          {item.number ? `Q${item.number}` : "Question"}
          {item.page ? (
            <span className="ml-2 text-sm font-normal text-slate-500">
              page {item.page}
            </span>
          ) : null}
        </h3>
        <QuestionBadges item={item} />
      </div>
      {showDocument ? (
        <p className="mt-1 text-xs text-slate-500">
          From{" "}
          <Link
            href={`/dashboard/documents/${item.document_id}`}
            className="font-medium text-brand-700 hover:underline"
          >
            {item.document_title}
          </Link>
        </p>
      ) : null}
      <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-slate-900" dir="auto">
        {formatMathText(item.text)}
      </p>
      <QuestionOptions item={item} />
      <AnswerLine item={item} />
      {detailsHref === null ? null : (
        <p className="mt-3">
          <Link
            href={detailsHref ?? `/dashboard/questions/${item.question_id}`}
            className="text-sm font-medium text-brand-700 hover:underline"
          >
            Evidence, corrections &amp; details →
          </Link>
        </p>
      )}
    </article>
  );
}

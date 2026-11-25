// OfficerPath AI — shared reading-mode card (M12).
//
// One question in reading mode: all four options with the
// correct one pre-ticked, and the stored explanation
// underneath. Nothing is invented — a missing explanation
// says so, and an unknown answer stays unknown.
//
// A question with no options is a Q+A card, not an MCQ: the
// answer text lives in ``explanation`` (the Most Important
// Questions — Computer one-liners), so the box is labelled
// "Answer" for those and "Explanation" for MCQs. Options are
// never invented or padded to four.

import type { QuestionItem } from "@/lib/api";
import { formatMathText } from "@/lib/mathText";
import { cn } from "@/lib/utils";

export function ReadingCard({ q, position }: { q: QuestionItem; position: number }) {
  const isQaPair = q.options.length === 0;
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-4">
      <p className="text-base font-semibold text-slate-900 sm:text-lg">
        Question {position}
        {q.number ? <span className="font-normal text-slate-500"> (Q{q.number})</span> : null}
        {isQaPair ? (
          <span className="ml-2 rounded-full bg-brand-50 px-2 py-0.5 text-xs font-semibold text-brand-700">
            Q&amp;A
          </span>
        ) : null}
      </p>
      <p className="mt-2 text-base leading-relaxed text-slate-900 sm:text-lg" dir="auto">
        {formatMathText(q.text)}
      </p>
      {isQaPair ? (
        <p className="mt-3 text-sm text-slate-500">
          This question has no options — it is a question-and-answer pair.
        </p>
      ) : (
        <ol className="mt-3 space-y-2">
          {q.options.map((option, i) => {
            const isCorrect = q.correct_index === i;
            return (
              <li
                key={i}
                className={cn(
                  "flex items-start gap-2 rounded-lg border px-3 py-2 text-sm sm:text-base",
                  isCorrect
                    ? "border-green-600 bg-green-50 font-semibold text-green-900"
                    : "border-slate-200 text-slate-700",
                )}
              >
                <span className="font-semibold">{String.fromCharCode(65 + i)}.</span>
                <span>{formatMathText(option)}</span>
                {isCorrect ? (
                  <span className="ml-auto shrink-0 text-xs font-semibold">Correct answer</span>
                ) : null}
              </li>
            );
          })}
        </ol>
      )}
      {q.correct_index !== null && q.correct_index < 0 ? (
        <p className="mt-3 text-sm text-slate-500">
          Answer unknown — the engine could not resolve this one, so nothing is marked.
        </p>
      ) : null}
      {q.explanation ? (
        <div className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-700 sm:text-base">
          <p className="font-semibold text-slate-900">{isQaPair ? "Answer" : "Explanation"}</p>
          <p className="mt-1 whitespace-pre-wrap">{formatMathText(q.explanation)}</p>
        </div>
      ) : (
        <p className="mt-3 text-sm text-slate-500">
          {isQaPair
            ? "No answer was stored for this question."
            : "No explanation was stored for this question."}
        </p>
      )}
      {q.submitted_by || q.paper ? (
        <p className="mt-3 text-xs text-slate-500">
          {q.submitted_by ? `Submitted by ${q.submitted_by}` : ""}
          {q.submitted_by && q.paper ? " · " : ""}
          {q.paper ? `Paper: ${q.paper}` : ""}
        </p>
      ) : null}
    </article>
  );
}

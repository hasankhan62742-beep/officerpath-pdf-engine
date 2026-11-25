// OfficerPath AI — "Add Questions" (M16).
//
// A student writes a question + four options + the correct
// answer + an explanation + subject + source + the paper it
// appeared in. The submission waits (pending) until an admin
// approves it; only approved questions join the bank. The list
// below the form shows the student's own submissions with
// their review status, so a rejection (with the admin's note)
// is visible here, not silently lost.

"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Pagination } from "@/components/ui/pagination";
import { SectionHeading } from "@/components/ui/section-heading";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import {
  ApiError,
  getSessionToken,
  listMyCommunityQuestions,
  listSubjects,
  submitCommunityQuestion,
} from "@/lib/api";
import { formatMathText } from "@/lib/mathText";

const PAGE_SIZE = 20;
const OPTION_LETTERS = ["A", "B", "C", "D"];

function statusTone(status: string): "info" | "success" | "danger" | "neutral" {
  if (status === "pending") return "info";
  if (status === "approved") return "success";
  if (status === "rejected") return "danger";
  return "neutral";
}

export default function AddQuestionsPage() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [question, setQuestion] = useState("");
  const [options, setOptions] = useState<string[]>(["", "", "", ""]);
  const [correctIndex, setCorrectIndex] = useState(1);
  const [explanation, setExplanation] = useState("");
  const [subjectId, setSubjectId] = useState("");
  const [topicId, setTopicId] = useState("");
  const [source, setSource] = useState("");
  const [paper, setPaper] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [submittedNote, setSubmittedNote] = useState<string | null>(null);

  const subjectsQuery = useQuery({
    queryKey: ["subjects"],
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new ApiError(401, "unauthorized", "Sign in to add a question.");
      return listSubjects(token);
    },
  });

  const mineQuery = useQuery({
    queryKey: ["my-community-questions", page],
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new ApiError(401, "unauthorized", "Sign in to view your submissions.");
      return listMyCommunityQuestions(token, {
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
      });
    },
  });

  const submitMutation = useMutation({
    mutationFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new ApiError(401, "unauthorized", "Sign in to add a question.");
      return submitCommunityQuestion(token, {
        question: question.trim(),
        options: options.map((o) => o.trim()),
        correct_index: correctIndex,
        explanation: explanation.trim() || null,
        subject_id: subjectId,
        topic_id: topicId || null,
        source: source.trim() || null,
        paper: paper.trim() || null,
      });
    },
    onSuccess: (result) => {
      setSubmittedNote(
        `Question submitted for review — it will join the bank once an admin approves it. Submitted by ${result.contributor_name}.`,
      );
      setFormError(null);
      setQuestion("");
      setOptions(["", "", "", ""]);
      setCorrectIndex(1);
      setExplanation("");
      setTopicId("");
      setSource("");
      setPaper("");
      setPage(1);
      void queryClient.invalidateQueries({ queryKey: ["my-community-questions"] });
    },
    onError: (err) => {
      setSubmittedNote(null);
      setFormError(err instanceof Error ? err.message : "Could not submit this question.");
    },
  });

  const subjects = subjectsQuery.data?.subjects ?? [];
  const selectedSubject = subjects.find((s) => s.id === subjectId);

  const formValid =
    question.trim().length > 0 &&
    options.every((o) => o.trim().length > 0) &&
    subjectId.length > 0;

  return (
    <div>
      <SectionHeading
        eyebrow="Community"
        title="Add Questions"
        description="Write a question for the bank. It goes to an admin for review first — approved questions join that subject's bank automatically, with your name shown underneath."
      />

      {subjectsQuery.isPending ? (
        <p className="flex items-center gap-2 text-sm text-slate-600">
          <Spinner /> Loading subjects…
        </p>
      ) : subjectsQuery.isError ? (
        <ErrorState
          title="Subjects could not be loaded"
          description={
            subjectsQuery.error instanceof Error
              ? subjectsQuery.error.message
              : "Try again."
          }
          onRetry={() => void subjectsQuery.refetch()}
        />
      ) : (
        <form
          className="max-w-2xl space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (!formValid || submitMutation.isPending) return;
            submitMutation.mutate();
          }}
        >
          <Textarea
            label="Question"
            name="question"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Write the question exactly as it appeared…"
            required
          />
          <div>
            <p className="mb-1.5 block text-sm font-medium text-slate-900">
              Options — tick the correct one
            </p>
            <div className="space-y-2">
              {options.map((option, i) => (
                <div key={i} className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="correct-option"
                    aria-label={`Option ${OPTION_LETTERS[i]} is correct`}
                    checked={correctIndex === i}
                    onChange={() => setCorrectIndex(i)}
                    className="h-4 w-4 shrink-0"
                  />
                  <span className="w-4 shrink-0 text-sm font-semibold text-slate-700">
                    {OPTION_LETTERS[i]}.
                  </span>
                  <Input
                    label={`Option ${OPTION_LETTERS[i]}`}
                    name={`option-${i}`}
                    value={option}
                    onChange={(e) => {
                      const next = [...options];
                      next[i] = e.target.value;
                      setOptions(next);
                    }}
                    placeholder={`Option ${OPTION_LETTERS[i]}`}
                    required
                  />
                </div>
              ))}
            </div>
          </div>
          <Textarea
            label="Explanation (optional)"
            name="explanation"
            value={explanation}
            onChange={(e) => setExplanation(e.target.value)}
            placeholder="Why is this the correct answer?"
          />
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label
                className="mb-1.5 block text-sm font-medium text-slate-900"
                htmlFor="subject"
              >
                Subject
              </label>
              <select
                id="subject"
                value={subjectId}
                onChange={(e) => {
                  setSubjectId(e.target.value);
                  setTopicId("");
                }}
                required
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
              >
                <option value="">Choose a subject…</option>
                {subjects.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label
                className="mb-1.5 block text-sm font-medium text-slate-900"
                htmlFor="topic"
              >
                Section (optional)
              </label>
              <select
                id="topic"
                value={topicId}
                onChange={(e) => setTopicId(e.target.value)}
                disabled={!selectedSubject}
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm disabled:bg-slate-50"
              >
                <option value="">No specific section</option>
                {(selectedSubject?.topics ?? []).map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <Input
            label="Which paper did this question appear in?"
            name="paper"
            value={paper}
            onChange={(e) => setPaper(e.target.value)}
            placeholder="e.g. PPSC Tehsildar BS-16 2021"
            hint="Paper name + year, as exact as you know it. It is shown with the question and helps the admin spot repeats."
          />
          <Input
            label="Source (optional)"
            name="source"
            value={source}
            onChange={(e) => setSource(e.target.value)}
            placeholder="e.g. PPSC past paper, a book name, or a link"
            hint="Where did you take this question from?"
          />
          {formError ? (
            <p role="alert" className="text-sm font-medium text-danger-700">
              {formError}
            </p>
          ) : null}
          {submittedNote ? (
            <p role="status" className="text-sm font-medium text-success-800">
              {submittedNote}
            </p>
          ) : null}
          <Button type="submit" disabled={!formValid || submitMutation.isPending}>
            {submitMutation.isPending ? "Submitting…" : "Submit for review"}
          </Button>
          <p className="text-sm text-slate-500">
            Up to 20 questions a day. Your name is shown with the question
            once it is approved — your email address is never shown.
          </p>
        </form>
      )}

      <div className="mt-10">
        <SectionHeading
          eyebrow="My submissions"
          title="Your questions"
          description="What you submitted, and what the admin decided."
        />
        {mineQuery.isPending ? (
          <Spinner />
        ) : mineQuery.isError ? (
          <ErrorState
            title="Your submissions could not be loaded"
            description={
              mineQuery.error instanceof Error ? mineQuery.error.message : "Try again."
            }
            onRetry={() => void mineQuery.refetch()}
          />
        ) : mineQuery.data.total === 0 ? (
          <EmptyState
            title="No questions submitted yet"
            description="Your submissions will appear here once you add your first question."
          />
        ) : (
          <div>
            <ul className="space-y-3">
              {mineQuery.data.items.map((item) => (
                <li
                  key={item.id}
                  className="rounded-2xl border border-slate-200 bg-white p-4"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={statusTone(item.status)}>{item.status}</Badge>
                    <span className="text-sm text-slate-500">
                      {item.subject.subject_name ?? "No subject"}
                      {item.subject.topic_name ? ` — ${item.subject.topic_name}` : ""}
                    </span>
                    {item.paper ? (
                      <span className="text-sm text-slate-500">Paper: {item.paper}</span>
                    ) : null}
                  </div>
                  <p className="mt-2 text-slate-900">{formatMathText(item.question)}</p>
                  <ol className="mt-2 space-y-1 text-sm text-slate-700">
                    {item.options.map((option, i) => (
                      <li key={i} className={i === item.correct_index ? "font-semibold text-green-900" : ""}>
                        {OPTION_LETTERS[i]}. {formatMathText(option)}
                        {i === item.correct_index ? " — correct answer" : ""}
                      </li>
                    ))}
                  </ol>
                  {item.review_note ? (
                    <p className="mt-2 text-sm text-slate-600">
                      Admin note: {item.review_note}
                    </p>
                  ) : null}
                </li>
              ))}
            </ul>
            <Pagination
              page={page}
              totalPages={Math.max(1, Math.ceil(mineQuery.data.total / PAGE_SIZE))}
              onPageChange={setPage}
            />
          </div>
        )}
      </div>
    </div>
  );
}

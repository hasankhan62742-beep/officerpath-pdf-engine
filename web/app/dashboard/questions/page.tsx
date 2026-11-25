"use client";

// OfficerPath AI — Question bank (Phase 2, M5).
//
// Every row is a real extracted question from the engine
// database. Search and filters run against the API, never
// against invented data. A question with no subject shows as
// "Uncategorised" — subjects are assigned by hand, never
// guessed by the engine.

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
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
import { QuestionBadges } from "@/components/dashboard/question-result";
import {
  BANK_STATUSES,
  getSessionToken,
  getTestAvailability,
  groupTopicsBySection,
  listDocuments,
  listQuestions,
  listSectionQuestions,
  listSubjects,
  type BankStatus,
  type QuestionItem,
} from "@/lib/api";
import { formatMathText } from "@/lib/mathText";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 20;
const READ_PAGE_SIZE = 10;

/** Truncate AFTER plain-text conversion, so a LaTeX-heavy
 * question is cut on its readable form, not its raw form. */
function truncateMathText(text: string, max: number): string {
  const plain = formatMathText(text);
  return plain.length > max ? `${plain.slice(0, max)}…` : plain;
}

type ConfidenceBand = "all" | "high" | "medium" | "low";

const BANDS: Record<ConfidenceBand, { min?: number; max?: number }> = {
  all: {},
  high: { min: 0.9 },
  medium: { min: 0.5, max: 0.9 },
  low: { max: 0.5 },
};

export default function QuestionsPage() {
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [documentId, setDocumentId] = useState("all");
  const [status, setStatus] = useState<"all" | BankStatus>("all");
  const [subjectId, setSubjectId] = useState("all");
  const [band, setBand] = useState<ConfidenceBand>("all");

  // M12 — reading mode: subject → section tabs → questions in
  // bank order, correct option pre-ticked, stored explanation
  // underneath. Same bank the tests draw from.
  const [view, setView] = useState<"table" | "read">("table");
  const [readSubjectId, setReadSubjectId] = useState("");
  const [readSection, setReadSection] = useState("");
  const [readPage, setReadPage] = useState(1);
  const [readRangeStart, setReadRangeStart] = useState("");
  const [readRangeEnd, setReadRangeEnd] = useState("");

  const listQuery = useQuery({
    queryKey: ["questions", page, search, documentId, status, subjectId, band],
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      return listQuestions(token, {
        q: search || undefined,
        document_id: documentId === "all" ? undefined : documentId,
        status: status === "all" ? undefined : status,
        subject_id: subjectId === "all" ? undefined : subjectId,
        confidence_min: BANDS[band].min,
        confidence_max: BANDS[band].max,
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
      });
    },
  });

  const docsQuery = useQuery({
    queryKey: ["documents-for-filter"],
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      return listDocuments(token, { limit: 100, offset: 0 });
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

  const totalPages = listQuery.data
    ? Math.max(1, Math.ceil(listQuery.data.total / PAGE_SIZE))
    : 1;

  function resetPage() {
    setPage(1);
  }

  // ---- M12 reading mode ----
  const readSubject = useMemo(
    () =>
      subjectsQuery.data?.subjects.find((s) => s.id === readSubjectId) ??
      subjectsQuery.data?.subjects.find((s) => s.topics.length > 0),
    [subjectsQuery.data, readSubjectId],
  );
  const readGroups = useMemo(
    () => (readSubject ? groupTopicsBySection(readSubject.topics) : []),
    [readSubject],
  );
  const readGroup = useMemo(
    () =>
      readGroups.find((g) => g.name === readSection) ?? readGroups[0],
    [readGroups, readSection],
  );
  const readAllTopicIds = useMemo(
    () => readGroups.flatMap((g) => g.topicIds),
    [readGroups],
  );
  const readCountsQuery = useQuery({
    queryKey: ["read-section-counts", readSubject?.id],
    enabled: view === "read" && readAllTopicIds.length > 0,
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      return getTestAvailability(token, {
        source_type: "topics",
        topic_ids: readAllTopicIds,
      });
    },
  });
  const readGroupTotal = useMemo(() => {
    if (!readGroup) return -1;
    let total = 0;
    let known = false;
    for (const topicId of readGroup.topicIds) {
      const row = readCountsQuery.data?.by_topic?.find((t) => t.topic_id === topicId);
      if (row) {
        total += row.available;
        known = true;
      }
    }
    return known ? total : -1;
  }, [readGroup, readCountsQuery.data]);
  const readGroupCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const group of readGroups) {
      let total = 0;
      let known = false;
      for (const topicId of group.topicIds) {
        const row = readCountsQuery.data?.by_topic?.find((t) => t.topic_id === topicId);
        if (row) {
          total += row.available;
          known = true;
        }
      }
      counts.set(group.name, known ? total : -1);
    }
    return counts;
  }, [readGroups, readCountsQuery.data]);
  const readRangeStartNum = readRangeStart.trim() === "" ? null : Number(readRangeStart);
  const readRangeEndNum = readRangeEnd.trim() === "" ? null : Number(readRangeEnd);
  const readRangeSet = readRangeStartNum !== null || readRangeEndNum !== null;
  const readRangeValid =
    !readRangeSet ||
    (readGroup !== undefined &&
      readRangeStartNum !== null &&
      readRangeEndNum !== null &&
      Number.isInteger(readRangeStartNum) &&
      Number.isInteger(readRangeEndNum) &&
      readRangeStartNum >= 1 &&
      readRangeEndNum >= readRangeStartNum &&
      readGroupTotal >= 0 &&
      readRangeEndNum <= readGroupTotal);
  const readRangeError = readRangeSet
    ? readRangeStartNum === null || readRangeEndNum === null
      ? "Enter both ends of the range."
      : !Number.isInteger(readRangeStartNum) || !Number.isInteger(readRangeEndNum)
        ? "The range must be whole question numbers."
        : readRangeStartNum < 1 || readRangeEndNum < readRangeStartNum
          ? "The range must start at 1 or later, and end at or after where it starts."
          : readGroupTotal < 0
            ? "Still loading how many questions this section holds…"
            : readRangeEndNum > readGroupTotal
              ? `This section holds ${readGroupTotal} question${readGroupTotal === 1 ? "" : "s"} — the range cannot go past ${readGroupTotal}.`
              : ""
    : "";
  const readTotal =
    readRangeSet && readRangeValid && readRangeStartNum !== null && readRangeEndNum !== null
      ? readRangeEndNum - readRangeStartNum + 1
      : readGroupTotal;
  const readTotalPages =
    readTotal > 0 ? Math.max(1, Math.ceil(readTotal / READ_PAGE_SIZE)) : 1;
  const readOffset =
    (readRangeSet && readRangeValid && readRangeStartNum !== null
      ? readRangeStartNum - 1
      : 0) +
    (readPage - 1) * READ_PAGE_SIZE;
  const readLimit =
    readTotal > 0
      ? Math.min(READ_PAGE_SIZE, readTotal - (readPage - 1) * READ_PAGE_SIZE)
      : READ_PAGE_SIZE;
  const readQuery = useQuery({
    queryKey: [
      "read-questions",
      readGroup?.topicIds,
      readOffset,
      readLimit,
      view,
    ],
    enabled:
      view === "read" &&
      readGroup !== undefined &&
      readTotal > 0 &&
      readRangeValid &&
      readLimit > 0,
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      return listSectionQuestions(token, readGroup?.topicIds ?? [], {
        limit: readLimit,
        offset: readOffset,
      });
    },
  });

  return (
    <div className="space-y-6">
      <SectionHeading
        title="Question bank"
        description="Every question the engine extracted from your documents, with its answer state. Unknown stays unknown — nothing here is guessed."
        level="h1"
        align="left"
      />

      <div className="flex gap-2" role="tablist" aria-label="Question bank view">
        <Button
          variant={view === "table" ? "primary" : "secondary"}
          onClick={() => setView("table")}
          aria-pressed={view === "table"}
        >
          Table
        </Button>
        <Button
          variant={view === "read" ? "primary" : "secondary"}
          onClick={() => setView("read")}
          aria-pressed={view === "read"}
        >
          Read
        </Button>
      </div>

      {view === "table" ? (
        <>
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          setSearch(searchInput.trim());
          resetPage();
        }}
      >
        <div className="min-w-56 flex-1">
          <Input
            label="Search questions"
            id="bank-search"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search by question text…"
          />
        </div>
        <Button type="submit" variant="secondary">
          Search
        </Button>
        <label className="text-sm font-medium text-slate-700" htmlFor="doc-filter">
          Document
        </label>
        <select
          id="doc-filter"
          className="min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm"
          value={documentId}
          onChange={(e) => {
            setDocumentId(e.target.value);
            resetPage();
          }}
        >
          <option value="all">All documents</option>
          {(docsQuery.data?.documents ?? []).map((doc) => (
            <option key={doc.id} value={doc.id}>
              {doc.title}
            </option>
          ))}
        </select>
        <label className="text-sm font-medium text-slate-700" htmlFor="status-filter">
          Answer
        </label>
        <select
          id="status-filter"
          className="min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as "all" | BankStatus);
            resetPage();
          }}
        >
          <option value="all">All answers</option>
          {BANK_STATUSES.map((s) => (
            <option key={s} value={s}>
              {s.charAt(0).toUpperCase() + s.slice(1)}
            </option>
          ))}
        </select>
        <label className="text-sm font-medium text-slate-700" htmlFor="subject-filter">
          Subject
        </label>
        <select
          id="subject-filter"
          className="min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm"
          value={subjectId}
          onChange={(e) => {
            setSubjectId(e.target.value);
            resetPage();
          }}
        >
          <option value="all">All subjects</option>
          {(subjectsQuery.data?.subjects ?? []).map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
        <label className="text-sm font-medium text-slate-700" htmlFor="band-filter">
          Confidence
        </label>
        <select
          id="band-filter"
          className="min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm"
          value={band}
          onChange={(e) => {
            setBand(e.target.value as ConfidenceBand);
            resetPage();
          }}
        >
          <option value="all">Any confidence</option>
          <option value="high">High (≥ 90%)</option>
          <option value="medium">Medium (50–90%)</option>
          <option value="low">Low (&lt; 50%)</option>
        </select>
      </form>
      <p className="text-xs text-slate-500">
        Confidence filters apply only to answered questions — unknown
        answers have no confidence to filter on.
      </p>

      {listQuery.isPending ? (
        <div className="flex items-center gap-2 py-16 text-slate-600">
          <Spinner /> Loading your questions…
        </div>
      ) : listQuery.isError || !listQuery.data ? (
        <ErrorState
          title="Could not load your questions"
          description={
            (listQuery.error as Error | null)?.message ??
            "The engine did not answer. Check that it is running and try again."
          }
          onRetry={() => listQuery.refetch()}
        />
      ) : listQuery.data.total === 0 ? (
        <EmptyState
          title="No questions found"
          description={
            search || documentId !== "all" || status !== "all" || subjectId !== "all" || band !== "all"
              ? "Nothing matches these filters. Clear a filter or try different words."
              : "Upload a paper first — extracted questions appear here once a document finishes processing."
          }
          actionLabel={
            search || documentId !== "all" || status !== "all" || subjectId !== "all" || band !== "all"
              ? undefined
              : "Upload your first document"
          }
          actionHref={
            search || documentId !== "all" || status !== "all" || subjectId !== "all" || band !== "all"
              ? undefined
              : "/dashboard/upload"
          }
        />
      ) : (
        <>
          <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white">
            <Table>
              <TableHead>
                <TableRow>
                  <TableHeaderCell>Question</TableHeaderCell>
                  <TableHeaderCell>Document</TableHeaderCell>
                  <TableHeaderCell>Answer</TableHeaderCell>
                  <TableHeaderCell>Confidence</TableHeaderCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {listQuery.data.questions.map((q) => (
                  <TableRow key={q.question_id}>
                    <TableCell>
                      <Link
                        href={`/dashboard/questions/${q.question_id}`}
                        className="font-medium text-brand-700 hover:underline"
                      >
                        {q.number ? `Q${q.number} — ` : ""}
                        {truncateMathText(q.text, 120)}
                      </Link>
                      {q.submitted_by || q.paper ? (
                        <p className="mt-1 text-xs text-slate-500">
                          {q.submitted_by ? `Submitted by ${q.submitted_by}` : ""}
                          {q.submitted_by && q.paper ? " · " : ""}
                          {q.paper ? `Paper: ${q.paper}` : ""}
                        </p>
                      ) : null}
                      <div className="mt-1">
                        <QuestionBadges item={q} />
                      </div>
                    </TableCell>
                    <TableCell>
                      <Link
                        href={`/dashboard/documents/${q.document_id}`}
                        className="text-brand-700 hover:underline"
                      >
                        {q.document_title}
                      </Link>
                    </TableCell>
                    <TableCell>
                      {q.correct_index !== null && q.correct_index >= 0 ? (
                        <span className="font-semibold text-slate-900">
                          {q.correct_letter}
                        </span>
                      ) : (
                        <span className="text-slate-500">Unknown</span>
                      )}
                    </TableCell>
                    <TableCell>
                      {q.confidence !== null
                        ? `${Math.round(q.confidence * 100)}%`
                        : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <p className="text-sm text-slate-600">
            Showing {(page - 1) * PAGE_SIZE + 1}–
            {Math.min(page * PAGE_SIZE, listQuery.data.total)} of{" "}
            {listQuery.data.total} questions.
          </p>
          <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
        </>
      )}
        </>
      ) : null}

      {view === "read" ? (
        <div className="space-y-4">
          {subjectsQuery.isPending ? (
            <p className="flex items-center gap-2 text-sm text-slate-600">
              <Spinner /> Loading subjects…
            </p>
          ) : subjectsQuery.isError || !subjectsQuery.data ? (
            <ErrorState
              title="Could not load subjects"
              description="The engine did not answer."
              onRetry={() => subjectsQuery.refetch()}
            />
          ) : readGroups.length === 0 ? (
            <EmptyState
              title="No sections yet"
              description="No subject has sections to read. Upload a paper or a question bank first."
            />
          ) : (
            <>
              <div>
                <p className="text-sm font-medium text-slate-900">Subject</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {subjectsQuery.data.subjects
                    .filter((subject) => subject.topics.length > 0)
                    .map((subject) => (
                      <button
                        key={subject.id}
                        type="button"
                        onClick={() => {
                          // A new subject resets the section + range
                          // picks (each subject has its own sections).
                          setReadSubjectId(subject.id);
                          setReadSection("");
                          setReadRangeStart("");
                          setReadRangeEnd("");
                          setReadPage(1);
                        }}
                        aria-pressed={readSubject?.id === subject.id}
                        className={cn(
                          "rounded-full border px-4 py-2 text-sm",
                          readSubject?.id === subject.id
                            ? "border-brand-600 bg-brand-600 font-semibold text-white"
                            : "border-slate-300 text-slate-700 hover:bg-slate-50",
                        )}
                      >
                        {subject.name}
                      </button>
                    ))}
                </div>
              </div>
              <div>
                <p className="text-sm font-medium text-slate-900">
                  Sections of {readSubject?.name} — pick one to read
                </p>
                {readCountsQuery.isPending ? (
                  <p className="mt-2 flex items-center gap-2 text-sm text-slate-600">
                    <Spinner /> Counting questions per section…
                  </p>
                ) : (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {readGroups.map((group) => {
                      const count = readGroupCounts.get(group.name);
                      const selected = readGroup?.name === group.name;
                      return (
                        <button
                          key={group.name}
                          type="button"
                          onClick={() => {
                            // A new section resets the range (each
                            // section has its own question count).
                            setReadSection(group.name);
                            setReadRangeStart("");
                            setReadRangeEnd("");
                            setReadPage(1);
                          }}
                          aria-pressed={selected}
                          className={cn(
                            "rounded-full border px-4 py-2 text-sm",
                            selected
                              ? "border-brand-600 bg-brand-600 font-semibold text-white"
                              : "border-slate-300 text-slate-700 hover:bg-slate-50",
                          )}
                        >
                          {group.name}
                          {count !== undefined && count >= 0 ? (
                            <span className={cn("ml-2 text-xs", selected ? "text-white" : "text-slate-500")}>
                              {count}
                            </span>
                          ) : null}
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
              {readGroup ? (
                <div className="max-w-xl space-y-2">
                  <p className="text-sm font-medium text-slate-900">
                    Read only part of this section? (optional)
                  </p>
                  <p className="text-sm text-slate-600">
                    {readGroup.name} holds{" "}
                    {readGroupTotal >= 0
                      ? `${readGroupTotal} question${readGroupTotal === 1 ? "" : "s"}`
                      : "…"}{" "}
                    — enter a range to read only the part you want, e.g. 1 to 500.
                    Leave both empty to read the whole section.
                  </p>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Input
                      label="From question"
                      type="number"
                      min={1}
                      max={readGroupTotal >= 0 ? readGroupTotal : undefined}
                      value={readRangeStart}
                      onChange={(e) => {
                        setReadRangeStart(e.target.value);
                        setReadPage(1);
                      }}
                      placeholder="1"
                    />
                    <Input
                      label="To question"
                      type="number"
                      min={1}
                      max={readGroupTotal >= 0 ? readGroupTotal : undefined}
                      value={readRangeEnd}
                      onChange={(e) => {
                        setReadRangeEnd(e.target.value);
                        setReadPage(1);
                      }}
                      placeholder={readGroupTotal >= 0 ? String(readGroupTotal) : ""}
                    />
                  </div>
                  {readRangeError ? (
                    <Alert tone="warning" title="Check the range">
                      {readRangeError}
                    </Alert>
                  ) : null}
                </div>
              ) : null}
              {readQuery.isPending ? (
                <p className="flex items-center gap-2 py-16 text-slate-600">
                  <Spinner /> Loading questions…
                </p>
              ) : readQuery.isError || !readQuery.data ? (
                <ErrorState
                  title="Could not load these questions"
                  description={
                    (readQuery.error as Error | null)?.message ??
                    "The engine did not answer. Check that it is running and try again."
                  }
                  onRetry={() => readQuery.refetch()}
                />
              ) : readQuery.data.total === 0 ? (
                <EmptyState
                  title="No questions in this section"
                  description="This section has no readable questions yet."
                />
              ) : (
                <>
                  <p className="text-sm text-slate-600">
                    Showing {readOffset + 1}–
                    {Math.min(readOffset + readQuery.data.questions.length, readOffset + readTotal)} of{" "}
                    {readTotal} questions
                    {readGroup ? ` in ${readGroup.name}` : ""}.
                  </p>
                  <div className="space-y-4">
                    {readQuery.data.questions.map((q, i) => (
                      <ReadingCard key={q.question_id} q={q} position={readOffset + i + 1} />
                    ))}
                  </div>
                  <Pagination page={readPage} totalPages={readTotalPages} onPageChange={setReadPage} />
                </>
              )}
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}

/**
 * One question in reading mode (M12): all four options, the
 * correct one pre-ticked, and the stored explanation
 * underneath. Nothing is invented — a missing explanation
 * says so, and an unknown answer stays unknown.
 */
function ReadingCard({ q, position }: { q: QuestionItem; position: number }) {
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-4">
      <p className="text-sm font-semibold text-slate-900">
        Question {position}
        {q.number ? <span className="font-normal text-slate-500"> (Q{q.number})</span> : null}
      </p>
      <p className="mt-2 text-slate-900">{formatMathText(q.text)}</p>
      {q.options.length > 0 ? (
        <ol className="mt-3 space-y-2">
          {q.options.map((option, i) => {
            const isCorrect = q.correct_index === i;
            return (
              <li
                key={i}
                className={cn(
                  "flex items-start gap-2 rounded-lg border px-3 py-2 text-sm",
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
      ) : (
        <p className="mt-3 text-sm text-slate-500">
          This question has no options — it is a question-and-answer pair.
        </p>
      )}
      {q.correct_index !== null && q.correct_index < 0 ? (
        <p className="mt-3 text-sm text-slate-500">
          Answer unknown — the engine could not resolve this one, so nothing is marked.
        </p>
      ) : null}
      {q.explanation ? (
        <div className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-700">
          <p className="font-semibold text-slate-900">Explanation</p>
          <p className="mt-1 whitespace-pre-wrap">{formatMathText(q.explanation)}</p>
        </div>
      ) : (
        <p className="mt-3 text-sm text-slate-500">
          No explanation was stored for this question.
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

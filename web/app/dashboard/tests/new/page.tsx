"use client";

// OfficerPath AI — Test builder (Phase 2, M6).
//
// Builds a test from the question bank: the API picks the
// questions (randomly, with a saved seed), freezes them into
// snapshots, and stores the marking config with the test. The
// availability preview is the engine's own count — never a
// guess — and requesting more than available is refused with
// the real number, never a short test. Taking the test is M7;
// this page only builds it.

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { SectionHeading } from "@/components/ui/section-heading";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import {
  ApiError,
  QUICK_COUNTS,
  createTest,
  getSessionToken,
  getTestAvailability,
  groupTopicsBySection,
  listDocuments,
  listMarkingConfigs,
  listQuestions,
  listSubjects,
  markingLabel,
  type MarkingConfig,
  type QuestionItem,
  type TestSourceType,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type SourceMode = "all" | "documents" | "subjects" | "topics" | "explicit";

const SOURCE_LABELS: Record<SourceMode, string> = {
  all: "All my questions",
  documents: "From specific documents",
  subjects: "From specific subjects",
  topics: "From specific sections",
  explicit: "Pick questions myself",
};

export default function NewTestPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [sourceMode, setSourceMode] = useState<SourceMode>("all");
  const [documentIds, setDocumentIds] = useState<string[]>([]);
  const [subjectIds, setSubjectIds] = useState<string[]>([]);
  // M12 — sections mode: one subject, then its sections
  // (subtopic groups such as "Synonyms") as selectable tabs.
  const [topicsSubjectId, setTopicsSubjectId] = useState("");
  const [selectedSections, setSelectedSections] = useState<string[]>([]);
  // M12 — question range, only when exactly one section is
  // selected. Empty means "the whole section".
  const [rangeStart, setRangeStart] = useState("");
  const [rangeEnd, setRangeEnd] = useState("");
  const [picks, setPicks] = useState<QuestionItem[]>([]);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [count, setCount] = useState(25);
  const [markingChoice, setMarkingChoice] = useState<string>("default");
  const [customName, setCustomName] = useState("Custom marking");
  const [customCorrect, setCustomCorrect] = useState("1");
  const [customIncorrect, setCustomIncorrect] = useState("-0.25");
  const [customUnattempted, setCustomUnattempted] = useState("0");
  const [allowRepetition, setAllowRepetition] = useState(false);
  const [includeUnknown, setIncludeUnknown] = useState(false);
  const [timeLimitMinutes, setTimeLimitMinutes] = useState("");
  const [submitError, setSubmitError] = useState("");
  const [creating, setCreating] = useState(false);

  const isExplicit = sourceMode === "explicit";
  const effectiveCount = isExplicit ? picks.length : count;

  const docsQuery = useQuery({
    queryKey: ["documents-for-builder"],
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      // Shared bank documents are listed too (M11), flagged by
      // is_shared, so a student can pick them as a test source.
      return listDocuments(token, { limit: 100, offset: 0, include_shared: true });
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

  const configsQuery = useQuery({
    queryKey: ["marking-configs"],
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      return listMarkingConfigs(token);
    },
  });

  const defaultConfig: MarkingConfig | undefined = useMemo(
    () => configsQuery.data?.find((c) => c.is_default) ?? configsQuery.data?.[0],
    [configsQuery.data],
  );

  // M12 — sections mode: the chosen subject's sections, with
  // per-section question counts. The subject defaults to the
  // first one that has sections.
  const topicsSubject = useMemo(
    () =>
      subjectsQuery.data?.subjects.find((s) => s.id === topicsSubjectId) ??
      subjectsQuery.data?.subjects.find((s) => s.topics.length > 0),
    [subjectsQuery.data, topicsSubjectId],
  );
  const topicGroups = useMemo(
    () => (topicsSubject ? groupTopicsBySection(topicsSubject.topics) : []),
    [topicsSubject],
  );
  const selectedTopicIds = useMemo(
    () =>
      topicGroups
        .filter((group) => selectedSections.includes(group.name))
        .flatMap((group) => group.topicIds),
    [topicGroups, selectedSections],
  );
  const allTopicIdsOfSubject = useMemo(
    () => topicGroups.flatMap((group) => group.topicIds),
    [topicGroups],
  );
  const sectionCountsQuery = useQuery({
    queryKey: ["section-counts", topicsSubject?.id, includeUnknown],
    enabled: sourceMode === "topics" && allTopicIdsOfSubject.length > 0,
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      return getTestAvailability(token, {
        source_type: "topics",
        topic_ids: allTopicIdsOfSubject,
        include_unknown: includeUnknown,
      });
    },
  });
  const sectionCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const group of topicGroups) {
      let total = 0;
      let known = false;
      for (const topicId of group.topicIds) {
        const row = sectionCountsQuery.data?.by_topic?.find((t) => t.topic_id === topicId);
        if (row) {
          total += row.available;
          known = true;
        }
      }
      counts.set(group.name, known ? total : -1);
    }
    return counts;
  }, [topicGroups, sectionCountsQuery.data]);
  const singleSection =
    selectedSections.length === 1
      ? topicGroups.find((group) => group.name === selectedSections[0])
      : undefined;
  const singleSectionTotal =
    singleSection === undefined ? undefined : sectionCounts.get(singleSection.name);
  const rangeStartNum = rangeStart.trim() === "" ? null : Number(rangeStart);
  const rangeEndNum = rangeEnd.trim() === "" ? null : Number(rangeEnd);
  const rangeSet = rangeStartNum !== null || rangeEndNum !== null;
  const rangeValid =
    !rangeSet ||
    (singleSection !== undefined &&
      rangeStartNum !== null &&
      rangeEndNum !== null &&
      Number.isInteger(rangeStartNum) &&
      Number.isInteger(rangeEndNum) &&
      rangeStartNum >= 1 &&
      rangeEndNum >= rangeStartNum &&
      singleSectionTotal !== undefined &&
      singleSectionTotal >= 0 &&
      rangeEndNum <= singleSectionTotal);
  const rangeError = rangeSet
    ? singleSection === undefined
      ? "A range needs exactly one section selected."
      : singleSectionTotal === undefined || singleSectionTotal < 0
        ? "Still loading how many questions this section holds…"
        : rangeStartNum === null || rangeEndNum === null
          ? "Enter both ends of the range."
          : !Number.isInteger(rangeStartNum) || !Number.isInteger(rangeEndNum)
            ? "The range must be whole question numbers."
            : rangeStartNum < 1 || rangeEndNum < rangeStartNum
              ? "The range must start at 1 or later, and end at or after where it starts."
              : rangeEndNum > singleSectionTotal
                ? `This section holds ${singleSectionTotal} question${singleSectionTotal === 1 ? "" : "s"} — the range cannot go past ${singleSectionTotal}.`
                : ""
    : "";
  const rangeForRequest =
    rangeSet && rangeValid && rangeStartNum !== null && rangeEndNum !== null
      ? { start: rangeStartNum, end: rangeEndNum }
      : null;

  const availabilityReady =
    !isExplicit &&
    (sourceMode === "all" ||
      (sourceMode === "documents" && documentIds.length > 0) ||
      (sourceMode === "subjects" && subjectIds.length > 0) ||
      (sourceMode === "topics" && selectedTopicIds.length > 0));

  const availabilityQuery = useQuery({
    queryKey: [
      "test-availability",
      sourceMode,
      documentIds,
      subjectIds,
      selectedTopicIds,
      rangeForRequest,
      includeUnknown,
    ],
    enabled: availabilityReady,
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      return getTestAvailability(token, {
        source_type: sourceMode as TestSourceType,
        document_ids: documentIds.length ? documentIds : undefined,
        subject_ids: subjectIds.length ? subjectIds : undefined,
        topic_ids: selectedTopicIds.length ? selectedTopicIds : undefined,
        include_unknown: includeUnknown,
        question_range_start: rangeForRequest?.start,
        question_range_end: rangeForRequest?.end,
      });
    },
  });

  const pickerQuery = useQuery({
    queryKey: ["question-picker", search],
    enabled: isExplicit,
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      return listQuestions(token, { q: search || undefined, limit: 20, offset: 0 });
    },
  });

  const pickedIds = useMemo(() => new Set(picks.map((p) => p.question_id)), [picks]);

  const available = availabilityQuery.data?.available;
  const countTooHigh =
    !isExplicit && available !== undefined && effectiveCount > available;

  const canCreate =
    name.trim().length > 0 &&
    (isExplicit ? picks.length > 0 : !countTooHigh && availabilityReady) &&
    (!rangeSet || rangeValid) &&
    !creating;

  function toggleId(list: string[], id: string, setList: (next: string[]) => void) {
    setList(list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);
  }

  async function handleCreate() {
    setSubmitError("");
    setCreating(true);
    try {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      const timeLimit =
        timeLimitMinutes.trim() === "" ? null : Number(timeLimitMinutes) * 60;
      const input = {
        name: name.trim(),
        description: description.trim() || null,
        question_count: effectiveCount,
        source_type: sourceMode as TestSourceType,
        source_ids:
          sourceMode === "documents"
            ? documentIds
            : sourceMode === "subjects"
              ? subjectIds
              : sourceMode === "topics"
                ? selectedTopicIds
                : sourceMode === "explicit"
                  ? picks.map((p) => p.question_id)
                  : null,
        question_range_start: rangeForRequest?.start ?? null,
        question_range_end: rangeForRequest?.end ?? null,
        marking_config_id:
          markingChoice === "custom" ? null : markingChoice === "default" ? null : markingChoice,
        marking:
          markingChoice === "custom"
            ? {
                name: customName.trim() || "Custom marking",
                correct_marks: Number(customCorrect),
                incorrect_marks: Number(customIncorrect),
                unattempted_marks: Number(customUnattempted),
              }
            : null,
        allow_repetition: allowRepetition,
        include_unknown: includeUnknown,
        time_limit_seconds: timeLimit,
      };
      const created = await createTest(token, input);
      router.push(`/dashboard/tests/${created.test_id}`);
    } catch (err) {
      setSubmitError(
        err instanceof ApiError
          ? err.message
          : "Could not create this test. Please try again.",
      );
      setCreating(false);
    }
  }

  return (
    <div className="space-y-8">
      <SectionHeading
        title="Build a new test"
        description="Pick where the questions come from, how many, and how they are marked. The test freezes its own copy of every question — editing the bank later never changes it."
        level="h1"
        align="left"
      />

      <section className="space-y-3">
        <h2 className="text-base font-semibold text-slate-900">1. Name your test</h2>
        <div className="max-w-xl space-y-3">
          <Input
            label="Test name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. PPSC Practice — Current Affairs"
          />
          <Textarea
            label="Description (optional)"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What is this test for?"
          />
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-base font-semibold text-slate-900">2. Where do the questions come from?</h2>
        <div className="flex flex-wrap gap-2" role="group" aria-label="Question source">
          {(Object.keys(SOURCE_LABELS) as SourceMode[]).map((mode) => (
            <Button
              key={mode}
              variant={sourceMode === mode ? "primary" : "secondary"}
              onClick={() => setSourceMode(mode)}
              aria-pressed={sourceMode === mode}
            >
              {SOURCE_LABELS[mode]}
            </Button>
          ))}
        </div>

        {sourceMode === "documents" ? (
          docsQuery.isPending ? (
            <p className="flex items-center gap-2 text-sm text-slate-600">
              <Spinner /> Loading your documents…
            </p>
          ) : docsQuery.isError || !docsQuery.data ? (
            <ErrorState
              title="Could not load your documents"
              description="The engine did not answer."
              onRetry={() => docsQuery.refetch()}
            />
          ) : docsQuery.data.documents.length === 0 ? (
            <p className="text-sm text-slate-600">
              You have no documents yet. Upload a paper first — the test builder needs
              extracted questions.
            </p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {docsQuery.data.documents.map((doc) => (
                <button
                  key={doc.id}
                  type="button"
                  onClick={() => toggleId(documentIds, doc.id, setDocumentIds)}
                  aria-pressed={documentIds.includes(doc.id)}
                  className={cn(
                    "rounded-full border px-4 py-2 text-sm",
                    documentIds.includes(doc.id)
                      ? "border-brand-600 bg-brand-600 font-semibold text-white"
                      : "border-slate-300 text-slate-700 hover:bg-slate-50",
                  )}
                >
                  {doc.title}
                </button>
              ))}
            </div>
          )
        ) : null}

        {sourceMode === "subjects" ? (
          subjectsQuery.isPending ? (
            <p className="flex items-center gap-2 text-sm text-slate-600">
              <Spinner /> Loading subjects…
            </p>
          ) : subjectsQuery.isError || !subjectsQuery.data ? (
            <ErrorState
              title="Could not load subjects"
              description="The engine did not answer."
              onRetry={() => subjectsQuery.refetch()}
            />
          ) : subjectsQuery.data.subjects.length === 0 ? (
            <p className="text-sm text-slate-600">No subjects are available yet.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {subjectsQuery.data.subjects.map((subject) => (
                <button
                  key={subject.id}
                  type="button"
                  onClick={() => toggleId(subjectIds, subject.id, setSubjectIds)}
                  aria-pressed={subjectIds.includes(subject.id)}
                  className={cn(
                    "rounded-full border px-4 py-2 text-sm",
                    subjectIds.includes(subject.id)
                      ? "border-brand-600 bg-brand-600 font-semibold text-white"
                      : "border-slate-300 text-slate-700 hover:bg-slate-50",
                  )}
                >
                  {subject.name}
                </button>
              ))}
            </div>
          )
        ) : null}

        {sourceMode === "topics" ? (
          subjectsQuery.isPending ? (
            <p className="flex items-center gap-2 text-sm text-slate-600">
              <Spinner /> Loading subjects…
            </p>
          ) : subjectsQuery.isError || !subjectsQuery.data ? (
            <ErrorState
              title="Could not load subjects"
              description="The engine did not answer."
              onRetry={() => subjectsQuery.refetch()}
            />
          ) : (
            <div className="space-y-3">
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
                          setTopicsSubjectId(subject.id);
                          setSelectedSections([]);
                          setRangeStart("");
                          setRangeEnd("");
                        }}
                        aria-pressed={topicsSubject?.id === subject.id}
                        className={cn(
                          "rounded-full border px-4 py-2 text-sm",
                          topicsSubject?.id === subject.id
                            ? "border-brand-600 bg-brand-600 font-semibold text-white"
                            : "border-slate-300 text-slate-700 hover:bg-slate-50",
                        )}
                      >
                        {subject.name}
                      </button>
                    ))}
                </div>
              </div>
              {topicsSubject ? (
                <div>
                  <p className="text-sm font-medium text-slate-900">
                    Sections of {topicsSubject.name} — pick one or more
                  </p>
                  {sectionCountsQuery.isPending ? (
                    <p className="mt-2 flex items-center gap-2 text-sm text-slate-600">
                      <Spinner /> Counting questions per section…
                    </p>
                  ) : (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {topicGroups.map((group) => {
                        const count = sectionCounts.get(group.name);
                        const selected = selectedSections.includes(group.name);
                        return (
                          <button
                            key={group.name}
                            type="button"
                            onClick={() => toggleId(selectedSections, group.name, setSelectedSections)}
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
              ) : null}
              {singleSection ? (
                <div className="max-w-xl space-y-2">
                  <p className="text-sm font-medium text-slate-900">
                    Only part of this section? (optional)
                  </p>
                  <p className="text-sm text-slate-600">
                    {singleSection.name} holds{" "}
                    {singleSectionTotal !== undefined && singleSectionTotal >= 0
                      ? `${singleSectionTotal} question${singleSectionTotal === 1 ? "" : "s"}`
                      : "…"}{" "}
                    — enter a range to test only the part you have read, e.g. 1 to 500.
                    Leave both empty for the whole section.
                  </p>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Input
                      label="From question"
                      type="number"
                      min={1}
                      max={
                        singleSectionTotal !== undefined && singleSectionTotal >= 0
                          ? singleSectionTotal
                          : undefined
                      }
                      value={rangeStart}
                      onChange={(e) => setRangeStart(e.target.value)}
                      placeholder="1"
                    />
                    <Input
                      label="To question"
                      type="number"
                      min={1}
                      max={
                        singleSectionTotal !== undefined && singleSectionTotal >= 0
                          ? singleSectionTotal
                          : undefined
                      }
                      value={rangeEnd}
                      onChange={(e) => setRangeEnd(e.target.value)}
                      placeholder={
                        singleSectionTotal !== undefined && singleSectionTotal >= 0
                          ? String(singleSectionTotal)
                          : ""
                      }
                    />
                  </div>
                  {rangeError ? (
                    <Alert tone="warning" title="Check the range">
                      {rangeError}
                    </Alert>
                  ) : null}
                </div>
              ) : null}
            </div>
          )
        ) : null}

        {isExplicit ? (
          <div className="space-y-3">
            <form
              className="flex max-w-xl gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                setSearch(searchInput.trim());
              }}
            >
              <Input
                label="Search the question bank"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder="Search question text…"
              />
              <Button type="submit" variant="secondary" className="mt-6">
                Search
              </Button>
            </form>
            {picks.length > 0 ? (
              <div>
                <p className="text-sm font-medium text-slate-900">
                  Picked ({picks.length})
                </p>
                <ul className="mt-2 space-y-2">
                  {picks.map((pick) => (
                    <li
                      key={pick.question_id}
                      className="flex items-start justify-between gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
                    >
                      <span>
                        {pick.text}
                        {pick.correct_index !== null && pick.correct_index < 0 ? (
                          <span className="ml-2 font-semibold text-amber-700">
                            — unknown answer
                          </span>
                        ) : null}
                      </span>
                      <Button
                        variant="ghost"
                        onClick={() =>
                          setPicks(picks.filter((p) => p.question_id !== pick.question_id))
                        }
                      >
                        Remove
                      </Button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {pickerQuery.isPending ? (
              <p className="flex items-center gap-2 text-sm text-slate-600">
                <Spinner /> Loading questions…
              </p>
            ) : pickerQuery.data ? (
              <ul className="space-y-2">
                {pickerQuery.data.questions.map((question) => (
                  <li
                    key={question.question_id}
                    className="flex items-start justify-between gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
                  >
                    <span>
                      {question.text}
                      <span className="ml-2 text-xs text-slate-500">
                        {question.document_title}
                      </span>
                      {question.correct_index !== null && question.correct_index < 0 ? (
                        <span className="ml-2 font-semibold text-amber-700">
                          — unknown answer
                        </span>
                      ) : null}
                    </span>
                    <Button
                      variant="secondary"
                      disabled={pickedIds.has(question.question_id)}
                      onClick={() => setPicks([...picks, question])}
                    >
                      {pickedIds.has(question.question_id) ? "Picked" : "Add"}
                    </Button>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
      </section>

      <section className="space-y-3">
        <h2 className="text-base font-semibold text-slate-900">3. How many questions?</h2>
        {isExplicit ? (
          <p className="text-sm text-slate-700">
            {picks.length} question{picks.length === 1 ? "" : "s"} picked — the test will
            contain exactly the questions you picked.
          </p>
        ) : (
          <>
            <div className="flex flex-wrap gap-2" role="group" aria-label="Question count">
              {QUICK_COUNTS.map((n) => (
                <Button
                  key={n}
                  variant={count === n ? "primary" : "secondary"}
                  onClick={() => setCount(n)}
                  aria-pressed={count === n}
                >
                  {n}
                </Button>
              ))}
            </div>
            <div className="max-w-xs">
              <Input
                label="Or a custom count (1–200)"
                type="number"
                min={1}
                max={200}
                value={count}
                onChange={(e) => setCount(Number(e.target.value))}
              />
            </div>
          </>
        )}
        {availabilityReady ? (
          availabilityQuery.isPending ? (
            <p className="flex items-center gap-2 text-sm text-slate-600">
              <Spinner /> Checking how many questions are available…
            </p>
          ) : availabilityQuery.data ? (
            <div className="space-y-2">
              <p className="text-sm text-slate-700">
                <strong>{availabilityQuery.data.available}</strong> question
                {availabilityQuery.data.available === 1 ? "" : "s"} available from this
                source
                {availabilityQuery.data.excluded_unknown > 0
                  ? ` (${availabilityQuery.data.excluded_unknown} with unknown answers excluded)`
                  : ""}
                {availabilityQuery.data.excluded_no_options > 0
                  ? ` (${availabilityQuery.data.excluded_no_options} Q&A pairs without options excluded)`
                  : ""}
                .
              </p>
              {rangeForRequest && singleSection ? (
                <p className="text-sm text-slate-700">
                  From questions {rangeForRequest.start}–{rangeForRequest.end} of{" "}
                  {singleSection.name} — the test will draw only from this range.
                </p>
              ) : null}
              {countTooHigh ? (
                <Alert tone="warning" title="Not enough questions">
                  Only {availabilityQuery.data.available} question
                  {availabilityQuery.data.available === 1 ? " is" : "s are"} available
                  from this source, but the test asks for {effectiveCount}. Lower the
                  count or widen the source — a short test is never built silently.
                </Alert>
              ) : null}
              {availabilityQuery.data.sample.length > 0 ? (
                <div>
                  <p className="text-sm font-medium text-slate-900">A sample of the pool:</p>
                  <ul className="mt-1 list-disc pl-5 text-sm text-slate-700">
                    {availabilityQuery.data.sample.map((item) => (
                      <li key={item.question_id}>
                        {item.text}
                        {item.correct_index < 0 ? (
                          <span className="font-semibold text-amber-700">
                            {" "}— unknown answer
                          </span>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : null
        ) : (
          <p className="text-sm text-slate-600">
            Select at least one{" "}
            {sourceMode === "documents"
              ? "document"
              : sourceMode === "topics"
                ? "section"
                : "subject"}{" "}
            to see how many questions are available.
          </p>
        )}
      </section>

      <section className="space-y-3">
        <h2 className="text-base font-semibold text-slate-900">4. How is it marked?</h2>
        <p className="max-w-2xl text-sm text-slate-700">
          PPSC default: a correct answer earns <strong>+1</strong>, a wrong answer costs{" "}
          <strong>−0.25</strong>, and skipping costs <strong>0</strong>. The marking is
          stored with the test and the score is always calculated on the server — never
          in the browser.
        </p>
        {configsQuery.isPending ? (
          <p className="flex items-center gap-2 text-sm text-slate-600">
            <Spinner /> Loading marking schemes…
          </p>
        ) : configsQuery.data ? (
          <div className="max-w-xl space-y-3">
            <label className="block text-sm font-medium text-slate-900" htmlFor="marking">
              Marking scheme
            </label>
            <select
              id="marking"
              value={markingChoice}
              onChange={(e) => setMarkingChoice(e.target.value)}
              className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
            >
              {defaultConfig ? (
                <option value="default">
                  {defaultConfig.name} ({markingLabel(defaultConfig)}) — default
                </option>
              ) : null}
              {configsQuery.data
                .filter((c) => !c.is_default)
                .map((config) => (
                  <option key={config.id} value={config.id}>
                    {config.name} ({markingLabel(config)})
                  </option>
                ))}
              <option value="custom">Custom marking…</option>
            </select>
            {markingChoice === "custom" ? (
              <div className="grid gap-3 sm:grid-cols-2">
                <Input
                  label="Custom scheme name"
                  value={customName}
                  onChange={(e) => setCustomName(e.target.value)}
                />
                <Input
                  label="Correct answer (0.25–10)"
                  type="number"
                  step="0.25"
                  min={0.25}
                  max={10}
                  value={customCorrect}
                  onChange={(e) => setCustomCorrect(e.target.value)}
                />
                <Input
                  label="Wrong answer (−5–0)"
                  type="number"
                  step="0.25"
                  min={-5}
                  max={0}
                  value={customIncorrect}
                  onChange={(e) => setCustomIncorrect(e.target.value)}
                />
                <Input
                  label="Skipped (−1–0)"
                  type="number"
                  step="0.25"
                  min={-1}
                  max={0}
                  value={customUnattempted}
                  onChange={(e) => setCustomUnattempted(e.target.value)}
                />
              </div>
            ) : null}
          </div>
        ) : null}
        <div className="max-w-xs">
          <Input
            label="Time limit in minutes (optional — empty means no limit)"
            type="number"
            min={1}
            value={timeLimitMinutes}
            onChange={(e) => setTimeLimitMinutes(e.target.value)}
            placeholder="e.g. 60"
          />
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-base font-semibold text-slate-900">5. Options</h2>
        <label className="flex items-start gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={allowRepetition}
            onChange={(e) => setAllowRepetition(e.target.checked)}
            className="mt-1"
          />
          <span>
            <strong>Allow repetition.</strong> The same question may appear more than
            once in this test. Off by default — a test never repeats a question unless
            you explicitly choose this.
          </span>
        </label>
        <label className="flex items-start gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={includeUnknown}
            onChange={(e) => setIncludeUnknown(e.target.checked)}
            className="mt-1"
          />
          <span>
            <strong>Include questions with unknown answers.</strong> Off by default —
            questions the engine could not answer are left out. If you include them,
            they stay flagged as unknown in the test and can never be scored.
          </span>
        </label>
      </section>

      {submitError ? (
        <Alert tone="danger" title="Could not create the test">
          {submitError}
        </Alert>
      ) : null}

      <div className="flex gap-2">
        <Button disabled={!canCreate} onClick={handleCreate}>
          {creating ? "Creating test…" : "Create test"}
        </Button>
        <Button
          variant="secondary"
          onClick={() => router.push("/dashboard/tests")}
        >
          Cancel
        </Button>
      </div>
      <p className="text-sm text-slate-600">
        Taking this test arrives in Milestone 7 — this page only builds and previews
        it.
      </p>
    </div>
  );
}

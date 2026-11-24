// OfficerPath AI — FastAPI engine client (Phase 2, M3).
//
// The browser calls the engine directly (Bearer JWT from the
// Supabase session). CORS on the engine allows only the configured
// frontend origins (ADR-011); the browser never calls Supabase
// PostgREST for engine tables — all data goes through this API.

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request<T>(
  path: string,
  accessToken: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
      ...(init?.headers ?? {}),
    },
  });
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const err = body?.error ?? {};
    throw new ApiError(
      res.status,
      typeof err.code === "string" ? err.code : "request_failed",
      typeof err.message === "string" ? err.message : `Request failed (${res.status}).`,
    );
  }
  return body as T;
}

export interface StudentProfile {
  user_id: string;
  email: string | null;
  full_name: string;
  phone: string | null;
  preferred_exam: string | null;
  education_level: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface ProfileInput {
  full_name: string;
  phone?: string | null;
  preferred_exam?: string | null;
  education_level?: string | null;
}

export async function getProfile(accessToken: string): Promise<StudentProfile> {
  return request<StudentProfile>("/api/v1/me", accessToken);
}

// ---------------------------------------------------------------------------
// Dashboard + documents (Phase 2, M4). All values come from the
// engine database; the frontend never invents a count.
// ---------------------------------------------------------------------------

export type JobStatus =
  | "queued"
  | "uploading"
  | "processing"
  | "done"
  | "failed"
  | "cancelled";

export const JOB_STATUSES: JobStatus[] = [
  "queued",
  "uploading",
  "processing",
  "done",
  "failed",
  "cancelled",
];

export interface DocumentJob {
  id: string;
  user_id: string;
  document_id: string;
  status: JobStatus;
  retry_count: number;
  error: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface DashboardDocument {
  id: string;
  title: string;
  file_type: string;
  file_size_bytes: number;
  page_count: number | null;
  created_at: string;
  job: DocumentJob | null;
  questions: number | null;
  answered: number | null;
  is_shared: boolean;
}

export interface DocumentListResponse {
  documents: DashboardDocument[];
  total: number;
  limit: number;
  offset: number;
}

export interface JobStage {
  stage: string;
  status: string;
  detail: Record<string, unknown> | null;
  created_at: string | null;
}

export interface DocumentDetail {
  document: {
    id: string;
    user_id: string;
    title: string;
    storage_path: string;
    file_type: string;
    file_size_bytes: number;
    page_count: number | null;
    content_hash: string | null;
    created_at: string;
  };
  job: (DocumentJob & { result_summary: Record<string, unknown> | null }) | null;
  stages: JobStage[];
}

export interface DashboardSummary {
  documents_total: number;
  jobs_by_status: Record<string, number>;
  recent_documents: DashboardDocument[];
}

export async function getDashboardSummary(accessToken: string): Promise<DashboardSummary> {
  return request<DashboardSummary>("/api/v1/dashboard/summary", accessToken);
}

export async function listDocuments(
  accessToken: string,
  opts: { limit?: number; offset?: number; status?: JobStatus; include_shared?: boolean },
): Promise<DocumentListResponse> {
  const params = new URLSearchParams();
  params.set("limit", String(opts.limit ?? 20));
  params.set("offset", String(opts.offset ?? 0));
  if (opts.status) params.set("status", opts.status);
  if (opts.include_shared) params.set("include_shared", "true");
  return request<DocumentListResponse>(`/api/v1/documents?${params}`, accessToken);
}

export async function getDocument(accessToken: string, id: string): Promise<DocumentDetail> {
  return request<DocumentDetail>(`/api/v1/documents/${id}`, accessToken);
}

export async function deleteDocument(
  accessToken: string,
  id: string,
): Promise<{ document_id: string; deleted: boolean; job_cancelled: boolean }> {
  return request<{ document_id: string; deleted: boolean; job_cancelled: boolean }>(
    `/api/v1/documents/${id}`,
    accessToken,
    { method: "DELETE" },
  );
}

export async function getJob(accessToken: string, jobId: string): Promise<DocumentJob> {
  return request<DocumentJob>(`/api/v1/jobs/${jobId}`, accessToken);
}

export async function cancelJob(accessToken: string, jobId: string): Promise<void> {
  await request(`/api/v1/async-jobs/${jobId}/cancel`, accessToken, { method: "POST" });
}

export async function retryJob(accessToken: string, jobId: string): Promise<DocumentJob> {
  return request<DocumentJob>(`/api/v1/jobs/${jobId}/retry`, accessToken, {
    method: "POST",
  });
}

/** The current Supabase session's access token, or null when signed out. */
export async function getSessionToken(): Promise<string | null> {
  const { createClient } = await import("@/lib/supabase/client");
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  return session?.access_token ?? null;
}

/** One uploaded file's outcome (single-upload and batch share the shape). */
export interface UploadedDocumentInfo {
  id: string;
  user_id: string;
  title: string;
  storage_path: string;
  file_type: string;
  file_size_bytes: number;
  page_count: number | null;
  content_hash: string | null;
  created_at: string;
}

export interface UploadResult {
  status: "stored" | "replay" | "rejected";
  filename: string;
  document: UploadedDocumentInfo | null;
  job: DocumentJob | null;
  storage_path: string | null;
  idempotent_replay: boolean;
  sha256: string | null;
  issues: { code: string; message: string; severity: string }[];
}

export interface BatchUploadResponse {
  results: UploadResult[];
  stored: number;
  replayed: number;
  rejected: number;
}

function uploadForm<T>(
  path: string,
  accessToken: string,
  form: FormData,
  onProgress?: (percent: number) => void,
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_URL}${path}`);
    xhr.setRequestHeader("Authorization", `Bearer ${accessToken}`);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };
    xhr.onload = () => {
      type ErrorEnvelope = { error?: { code?: string; message?: string } };
      let body: ErrorEnvelope | null = null;
      try {
        body = JSON.parse(xhr.responseText) as ErrorEnvelope;
      } catch {
        body = null;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body as T);
        return;
      }
      const err = body?.error ?? {};
      reject(
        new ApiError(
          xhr.status,
          typeof err.code === "string" ? err.code : "request_failed",
          typeof err.message === "string"
            ? err.message
            : `Upload failed (${xhr.status}).`,
        ),
      );
    };
    xhr.onerror = () => {
      reject(
        new ApiError(
          0,
          "network_error",
          "Could not reach the engine. Check that it is running and try again.",
        ),
      );
    };
    xhr.send(form);
  });
}

/** Upload ONE file (single-upload endpoint, honest per-file progress).
 * `opts.multiPass` (M14, ADR-010) asks the worker for the
 * three-variant union OCR instead of the single path — slower
 * (~3x) but recovers more questions from scans. Default off. */
export async function uploadFile(
  accessToken: string,
  file: File,
  onProgress?: (percent: number) => void,
  opts: { multiPass?: boolean } = {},
): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file, file.name);
  const path = opts.multiPass
    ? "/api/v1/documents/upload?multi_pass=true"
    : "/api/v1/documents/upload";
  return uploadForm<UploadResult>(path, accessToken, form, onProgress);
}

/** Upload 2–20 files in one batch request (one rate-limit charge).
 * `opts.multiPass` (M14) applies to every file in the batch. */
export async function uploadBatch(
  accessToken: string,
  files: File[],
  onProgress?: (percent: number) => void,
  opts: { multiPass?: boolean } = {},
): Promise<BatchUploadResponse> {
  const form = new FormData();
  for (const file of files) form.append("files", file, file.name);
  const path = opts.multiPass
    ? "/api/v1/documents/upload/batch?multi_pass=true"
    : "/api/v1/documents/upload/batch";
  return uploadForm<BatchUploadResponse>(path, accessToken, form, onProgress);
}

export async function createProfile(
  accessToken: string,
  input: ProfileInput,
): Promise<StudentProfile> {
  return request<StudentProfile>("/api/v1/me", accessToken, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function updateProfile(
  accessToken: string,
  input: ProfileInput,
): Promise<StudentProfile> {
  return request<StudentProfile>("/api/v1/me", accessToken, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

// ---------------------------------------------------------------------------
// Extraction results + question bank (Phase 2, M5). All values come
// from the engine database; the frontend never invents an answer.
// correct_index -1 means UNKNOWN — the UI renders it as unknown,
// never as a correct option. confidence is null when the engine
// has no answer row.
// ---------------------------------------------------------------------------

export interface SubjectAssignment {
  subject_id: string;
  subject_name: string;
  subject_slug: string;
  topic_id: string | null;
  topic_name: string | null;
}

export type AnswerStatus =
  | "verified"
  | "detected"
  | "unknown"
  | "needs_review"
  | "conflicting"
  | "withheld";

export interface QuestionItem {
  question_id: string;
  document_id: string;
  document_title: string;
  number: string | null;
  text: string;
  options: string[];
  kind: string;
  // null = key withheld (test not submitted yet); the card
  // renders "Answer hidden" instead of an answer.
  correct_index: number | null;
  correct_letter: string;
  answer_source: string;
  // Stored verbatim explanation (M10); null when the source
  // gave none — never invented. Reading mode shows it under
  // the question.
  explanation: string | null;
  confidence: number | null;
  verified: boolean;
  inferred: boolean;
  corrected: boolean;
  status: string;
  answer_status: AnswerStatus;
  page: number | null;
  subjects: SubjectAssignment[];
  created_at: string | null;
}

export interface QuestionListResponse {
  questions: QuestionItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface EvidenceItem {
  detector: string;
  source_type: string;
  value_normalized: string | null;
  page_number: number | null;
  detector_confidence: number | null;
  artifact_ref: string | null;
}

export interface CorrectionItem {
  id: string;
  field_name: string;
  old_value: string | null;
  new_value: string | null;
  reason: string | null;
  created_at: string | null;
}

export interface QuestionDetail extends QuestionItem {
  evidence: EvidenceItem[];
  corrections: CorrectionItem[];
}

export interface DocumentQuestionsResponse {
  document_id: string;
  questions: QuestionItem[];
  total: number;
  limit: number;
  offset: number;
  counts: Record<string, number>;
  qa_pairs: number;
}

export interface DocumentReport {
  document_id: string;
  job_id: string | null;
  rule_set_version: string;
  questions_extracted: number;
  questions_missing_options: number;
  uncertain_answers: number;
  conflicting_answers: number;
  unmatched_key_entries: number;
  duplicates_found: number;
  requires_review: boolean;
  review_reasons: string[];
  summary: Record<string, unknown>;
  created_at: string | null;
}

export interface SubjectTopic {
  id: string;
  name: string;
  slug: string;
}

export interface SubjectItem {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  topics: SubjectTopic[];
}

export type BankStatus =
  | "answered"
  | "unknown"
  | "pending"
  | "inferred"
  | "corrected"
  | "conflicting";

export const BANK_STATUSES: BankStatus[] = [
  "answered",
  "unknown",
  "pending",
  "inferred",
  "corrected",
  "conflicting",
];

/** Human label for an answer source, exactly as the engine reports it. */
export function answerSourceLabel(source: string): string {
  switch (source) {
    case "manual":
      return "Manual verification";
    case "trailing-key":
      return "Answer key";
    case "inline":
      return "Inline answer";
    case "style":
      return "Digital style";
    case "visual":
      return "Visual marking";
    case "inferred":
      return "Inferred";
    default:
      return "No source";
  }
}

export async function listQuestions(
  accessToken: string,
  opts: {
    q?: string;
    document_id?: string;
    status?: BankStatus;
    subject_id?: string;
    confidence_min?: number;
    confidence_max?: number;
    limit?: number;
    offset?: number;
  },
): Promise<QuestionListResponse> {
  const params = new URLSearchParams();
  if (opts.q) params.set("q", opts.q);
  if (opts.document_id) params.set("document_id", opts.document_id);
  if (opts.status) params.set("status", opts.status);
  if (opts.subject_id) params.set("subject_id", opts.subject_id);
  if (opts.confidence_min !== undefined)
    params.set("confidence_min", String(opts.confidence_min));
  if (opts.confidence_max !== undefined)
    params.set("confidence_max", String(opts.confidence_max));
  params.set("limit", String(opts.limit ?? 20));
  params.set("offset", String(opts.offset ?? 0));
  return request<QuestionListResponse>(`/api/v1/questions?${params}`, accessToken);
}

export async function getQuestion(
  accessToken: string,
  questionId: string,
): Promise<QuestionDetail> {
  return request<QuestionDetail>(`/api/v1/questions/${questionId}`, accessToken);
}

export async function listDocumentQuestions(
  accessToken: string,
  documentId: string,
  opts: { limit?: number; offset?: number } = {},
): Promise<DocumentQuestionsResponse> {
  const params = new URLSearchParams();
  params.set("limit", String(opts.limit ?? 50));
  params.set("offset", String(opts.offset ?? 0));
  return request<DocumentQuestionsResponse>(
    `/api/v1/documents/${documentId}/questions?${params}`,
    accessToken,
  );
}

export async function getDocumentReport(
  accessToken: string,
  documentId: string,
): Promise<DocumentReport> {
  return request<DocumentReport>(`/api/v1/documents/${documentId}/report`, accessToken);
}

export async function listCorrections(
  accessToken: string,
  documentId: string,
  questionId: string,
): Promise<{ question_id: string; corrections: CorrectionItem[]; total: number }> {
  return request(
    `/api/v1/documents/${documentId}/questions/${questionId}/corrections`,
    accessToken,
  );
}

export async function submitCorrection(
  accessToken: string,
  documentId: string,
  questionId: string,
  field: string,
  newValue: string,
  reason: string,
): Promise<{
  question_id: string;
  number: string | null;
  field: string;
  old_value: string | null;
  new_value: string;
  validation_status: string;
  validation_issues: { code: string; message: string }[];
}> {
  return request(
    `/api/v1/documents/${documentId}/questions/${questionId}/corrections`,
    accessToken,
    {
      method: "POST",
      body: JSON.stringify({ field, new_value: newValue, reason }),
    },
  );
}

export async function listSubjects(
  accessToken: string,
): Promise<{ subjects: SubjectItem[]; total: number }> {
  return request<{ subjects: SubjectItem[]; total: number }>(
    "/api/v1/subjects",
    accessToken,
  );
}

export async function assignSubject(
  accessToken: string,
  questionId: string,
  subjectId: string,
): Promise<{
  question_id: string;
  subject_id: string;
  subject_name: string;
  subject_slug: string;
  topic_id: string | null;
  topic_name: string | null;
  already_assigned: boolean;
}> {
  return request(
    `/api/v1/questions/${questionId}/subjects`,
    accessToken,
    { method: "POST", body: JSON.stringify({ subject_id: subjectId }) },
  );
}

export async function unassignSubject(
  accessToken: string,
  questionId: string,
  subjectId: string,
): Promise<{ question_id: string; subject_id: string; removed: boolean }> {
  return request(
    `/api/v1/questions/${questionId}/subjects/${subjectId}`,
    accessToken,
    { method: "DELETE" },
  );
}

// ---------------------------------------------------------------------------
// Test builder (Phase 2, M6). A test is a frozen snapshot: the
// questions, options, answers and marking travel with the test,
// and a later bank edit never changes them. Marking is stored
// with the test and computed on the backend (M7/M8) — the
// frontend never computes or supplies marks.
// ---------------------------------------------------------------------------

export interface MarkingConfig {
  id: string;
  name: string;
  correct_marks: number;
  incorrect_marks: number;
  unattempted_marks: number;
  is_default: boolean;
}

export interface MarkingConfigInput {
  name: string;
  correct_marks: number;
  incorrect_marks: number;
  unattempted_marks: number;
}

export interface TestSnapshot {
  snapshot_id: string;
  question_id: string | null;
  position: number;
  question_text: string;
  options: { label: string; text: string }[];
  // null = key withheld: the test has not been submitted yet.
  // -1 = UNKNOWN (explicit opt-in only); >= 0 = the answer.
  correct_index: number | null;
  answer_source: string | null;
  // Stored verbatim explanation, frozen at test creation (M10).
  // null pre-submit (withheld with the key) or when the bank
  // holds none — never invented.
  explanation: string | null;
  // True when the frozen correct_index is -1. Always present,
  // so the UI can flag unknown questions without the key.
  is_unknown: boolean;
  source_document_id: string | null;
  source_page: number | null;
}

export type TestSourceType =
  | "all"
  | "documents"
  | "subjects"
  | "topics"
  | "mixed"
  | "explicit";

export interface TestSummary {
  test_id: string;
  template_id: string;
  title: string;
  description: string | null;
  question_count: number;
  source_type: string;
  source_ids: Record<string, unknown> | null;
  allow_repetition: boolean;
  include_unknown: boolean;
  status: string;
  marking_config: MarkingConfig;
  created_at: string | null;
  updated_at: string | null;
}

export interface TestDetail extends TestSummary {
  snapshots: TestSnapshot[];
  excluded_unknown: number;
  excluded_no_options: number;
}

export interface TestListResponse {
  tests: TestSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface TestCreateInput {
  name: string;
  description?: string | null;
  question_count: number;
  source_type: TestSourceType;
  source_ids?: Record<string, unknown> | string[] | null;
  marking_config_id?: string | null;
  marking?: MarkingConfigInput | null;
  allow_repetition?: boolean;
  include_unknown?: boolean;
  time_limit_seconds?: number | null;
  // M12 — 1-based inclusive positions into the chosen
  // section's bank-ordered pool. Single-section only.
  question_range_start?: number | null;
  question_range_end?: number | null;
}

export interface AvailabilitySample {
  question_id: string;
  document_id: string;
  document_title: string;
  number: string | null;
  text: string;
  correct_index: number;
}

export interface TopicAvailability {
  topic_id: string;
  topic_name: string;
  available: number;
  excluded_unknown: number;
  excluded_no_options: number;
}

export interface Availability {
  available: number;
  excluded_unknown: number;
  excluded_no_options: number;
  sample: AvailabilitySample[];
  // M12 — per-topic counts, only when source_type is "topics"
  // and no range is given.
  by_topic?: TopicAvailability[] | null;
}

export const QUICK_COUNTS = [25, 50, 100, 150, 200] as const;

export function markingLabel(config: MarkingConfig): string {
  const fmt = (n: number) => (n > 0 ? `+${n}` : `${n}`);
  return `${fmt(config.correct_marks)} / ${fmt(config.incorrect_marks)} / ${fmt(config.unattempted_marks)}`;
}

export async function listMarkingConfigs(accessToken: string): Promise<MarkingConfig[]> {
  const res = await request<{ marking_configs: MarkingConfig[]; total: number }>(
    "/api/v1/marking-configs",
    accessToken,
  );
  return res.marking_configs;
}

export async function createMarkingConfig(
  accessToken: string,
  input: MarkingConfigInput,
): Promise<MarkingConfig> {
  return request<MarkingConfig>("/api/v1/marking-configs", accessToken, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function getTestAvailability(
  accessToken: string,
  opts: {
    source_type: TestSourceType;
    document_ids?: string[];
    subject_ids?: string[];
    topic_ids?: string[];
    include_unknown?: boolean;
    question_range_start?: number | null;
    question_range_end?: number | null;
  },
): Promise<Availability> {
  const params = new URLSearchParams();
  params.set("source_type", opts.source_type);
  for (const id of opts.document_ids ?? []) params.append("document_ids", id);
  for (const id of opts.subject_ids ?? []) params.append("subject_ids", id);
  for (const id of opts.topic_ids ?? []) params.append("topic_ids", id);
  if (opts.include_unknown) params.set("include_unknown", "true");
  if (opts.question_range_start != null)
    params.set("question_range_start", String(opts.question_range_start));
  if (opts.question_range_end != null)
    params.set("question_range_end", String(opts.question_range_end));
  return request<Availability>(`/api/v1/tests/availability?${params}`, accessToken);
}

export async function listSectionQuestions(
  accessToken: string,
  topicIds: string[],
  opts: { limit?: number; offset?: number } = {},
): Promise<QuestionListResponse> {
  const params = new URLSearchParams();
  for (const id of topicIds) params.append("topic_ids", id);
  params.set("limit", String(opts.limit ?? 20));
  params.set("offset", String(opts.offset ?? 0));
  return request<QuestionListResponse>(
    `/api/v1/tests/sections/questions?${params}`,
    accessToken,
  );
}

export interface TopicSectionGroup {
  /** Display name of the section, e.g. "Synonyms". */
  name: string;
  /** Topic ids of the section's parts, in section order. */
  topicIds: string[];
}

/**
 * Group a subject's topics into user-facing sections (M12).
 * The bank import names one topic per (subtopic, section)
 * group — "Synonyms — Section 1", "Synonyms — Section 2" —
 * but a student picks the section "Synonyms" as one tab, so
 * topics sharing a base name collapse into one group. A
 * topic without a " — Section N" suffix is its own group.
 * Topic ids inside a group are ordered by section number
 * (names alone would sort "Section 10" before "Section 2").
 */
export function groupTopicsBySection(topics: SubjectTopic[]): TopicSectionGroup[] {
  function sectionIndex(topic: SubjectTopic): number {
    const fromSlug = /-s(\d+)$/.exec(topic.slug);
    if (fromSlug) return Number(fromSlug[1]);
    const fromName = /—\s*Section\s+(\d+)\s*$/.exec(topic.name);
    if (fromName) return Number(fromName[1]);
    return 0;
  }
  const groups = new Map<string, { name: string; parts: { id: string; index: number }[] }>();
  for (const topic of topics) {
    const base = topic.name.replace(/\s+—\s+Section\s+\d+\s*$/, "").trim() || topic.name;
    const existing = groups.get(base);
    if (!existing) {
      groups.set(base, { name: base, parts: [{ id: topic.id, index: sectionIndex(topic) }] });
    } else {
      existing.parts.push({ id: topic.id, index: sectionIndex(topic) });
    }
  }
  return [...groups.values()].map(({ name, parts }) => ({
    name,
    topicIds: parts
      .slice()
      .sort((a, b) => a.index - b.index)
      .map((part) => part.id),
  }));
}

export async function createTest(
  accessToken: string,
  input: TestCreateInput,
): Promise<TestDetail> {
  return request<TestDetail>("/api/v1/tests", accessToken, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function listTests(
  accessToken: string,
  opts: { limit?: number; offset?: number },
): Promise<TestListResponse> {
  const params = new URLSearchParams();
  params.set("limit", String(opts.limit ?? 20));
  params.set("offset", String(opts.offset ?? 0));
  return request<TestListResponse>(`/api/v1/tests?${params}`, accessToken);
}

export async function getTest(accessToken: string, id: string): Promise<TestDetail> {
  return request<TestDetail>(`/api/v1/tests/${id}`, accessToken);
}

export async function updateTest(
  accessToken: string,
  id: string,
  input: { name?: string; description?: string | null },
): Promise<TestSummary> {
  return request<TestSummary>(`/api/v1/tests/${id}`, accessToken, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export async function deleteTest(
  accessToken: string,
  id: string,
): Promise<{ test_id: string; deleted: boolean }> {
  return request<{ test_id: string; deleted: boolean }>(`/api/v1/tests/${id}`, accessToken, {
    method: "DELETE",
  });
}

// ---------------------------------------------------------------------------
// Examination interface (Phase 2, M7, GAP-6). The timer is server
// truth: remaining_seconds comes from the server (server_started_at
// + time limit) and the page re-syncs it by polling — it never
// trusts the browser clock.
// ---------------------------------------------------------------------------

export interface StartTestResponse {
  test_id: string;
  title: string;
  status: string;
  time_limit_seconds: number | null;
  server_started_at: string;
  expires_at: string | null;
  remaining_seconds: number | null;
  marking_config: MarkingConfig;
}

export interface ExamResponseItem {
  snapshot_id: string;
  selected_index: number | null;
  marked_for_review: boolean;
  answered_at: string | null;
  updated_at: string | null;
}

export interface ExamSessionSnapshot {
  snapshot_id: string;
  question_id: string | null;
  position: number;
  question_text: string;
  options: { label: string; text: string }[];
  // M9: the session response deliberately carries NO correct_index
  // (the answer key must not reach the browser mid-exam). Only
  // is_unknown is sent — the take page disables options for it.
  is_unknown: boolean;
  source_document_id: string | null;
  source_page: number | null;
}

export interface ExamSession {
  test_id: string;
  title: string;
  status: string;
  time_limit_seconds: number | null;
  server_started_at: string | null;
  expires_at: string | null;
  remaining_seconds: number | null;
  server_time: string;
  marking_config: MarkingConfig;
  snapshots: ExamSessionSnapshot[];
  responses: ExamResponseItem[];
}

export interface ExamResult {
  result_id: string;
  test_id: string;
  template_id: string | null;
  title: string;
  status: string;
  total_questions: number;
  correct: number;
  incorrect: number;
  unattempted: number;
  unknown_count: number;
  total_marks: number;
  max_marks: number;
  percentage: number;
  time_taken_seconds: number;
  marking_config: MarkingConfig;
  submitted_at: string | null;
}

export async function startTest(accessToken: string, id: string): Promise<StartTestResponse> {
  return request<StartTestResponse>(`/api/v1/tests/${id}/start`, accessToken, {
    method: "POST",
  });
}

export async function getExamSession(accessToken: string, id: string): Promise<ExamSession> {
  return request<ExamSession>(`/api/v1/tests/${id}/session`, accessToken);
}

export async function saveAnswers(
  accessToken: string,
  id: string,
  answers: { snapshot_id: string; selected_index: number | null; marked_for_review?: boolean }[],
): Promise<{
  test_id: string;
  status: string;
  remaining_seconds: number | null;
  saved: ExamResponseItem[];
}> {
  return request(`/api/v1/tests/${id}/answers`, accessToken, {
    method: "POST",
    body: JSON.stringify({ answers }),
  });
}

export async function submitTest(accessToken: string, id: string): Promise<ExamResult> {
  return request<ExamResult>(`/api/v1/tests/${id}/submit`, accessToken, {
    method: "POST",
  });
}

export async function getTestResult(accessToken: string, id: string): Promise<ExamResult> {
  return request<ExamResult>(`/api/v1/tests/${id}/result`, accessToken);
}

// ---------------------------------------------------------------------------
// Results + analytics (Phase 2, M8, GAP-7) and question collections
// (GAP-8: bookmarks + mistake notebook). Every number shown comes
// from the stored test_results row — the frontend never computes
// marks, breakdowns, or trends.
// ---------------------------------------------------------------------------

export interface BreakdownItem {
  key: string;
  name: string;
  slug: string | null;
  scored: number;
  correct: number;
  incorrect: number;
  unattempted: number;
  marks: number;
  max_marks: number;
  accuracy: number | null;
}

export interface WeakStrongArea {
  subject_name: string;
  accuracy: number | null;
  scored: number;
}

export interface ReviewItem {
  snapshot_id: string;
  question_id: string | null;
  position: number;
  question_text: string;
  options: { label: string; text: string }[];
  correct_index: number;
  selected_index: number | null;
  marked_for_review: boolean;
  status: "correct" | "incorrect" | "unattempted" | "unknown";
  answer_source: string | null;
  // Stored verbatim explanation (M10). Null = none stored.
  explanation: string | null;
  source_document_id: string | null;
  source_page: number | null;
  is_bookmarked: boolean;
  bookmark_id: string | null;
  is_mistake: boolean;
}

export interface ExamResultDetail extends ExamResult {
  subject_breakdown: BreakdownItem[] | null;
  topic_breakdown: BreakdownItem[] | null;
  weak_areas: WeakStrongArea[];
  strong_areas: WeakStrongArea[];
  review: ReviewItem[];
}

export interface ResultsListResponse {
  results: ExamResultDetail[];
  total: number;
  limit: number;
  offset: number;
}

export async function getTestResultDetail(
  accessToken: string,
  id: string,
): Promise<ExamResultDetail> {
  return request<ExamResultDetail>(`/api/v1/tests/${id}/result`, accessToken);
}

export async function listResults(
  accessToken: string,
  opts: { limit?: number; offset?: number },
): Promise<ResultsListResponse> {
  const params = new URLSearchParams();
  params.set("limit", String(opts.limit ?? 20));
  params.set("offset", String(opts.offset ?? 0));
  return request<ResultsListResponse>(`/api/v1/results?${params}`, accessToken);
}

export async function retryTest(accessToken: string, id: string): Promise<TestDetail> {
  return request<TestDetail>(`/api/v1/tests/${id}/retry`, accessToken, {
    method: "POST",
  });
}

export async function createTestFromMistakes(
  accessToken: string,
  input: {
    name: string;
    question_ids?: string[] | null;
    time_limit_seconds?: number | null;
    marking_config_id?: string | null;
    marking?: MarkingConfigInput | null;
  },
): Promise<TestDetail> {
  return request<TestDetail>("/api/v1/tests/from-mistakes", accessToken, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export interface CollectionQuestion {
  question_id: string;
  document_id: string;
  document_title: string;
  number: string | null;
  text: string;
  options: string[];
  correct_index: number;
  answer_source: string;
  // Stored verbatim explanation (M10). Null = none stored.
  explanation: string | null;
}

export interface CollectionItem {
  id: string;
  question_id: string;
  collection_type: string;
  note: string | null;
  created_at: string | null;
  updated_at: string | null;
  question: CollectionQuestion | null;
  already_exists?: boolean | null;
}

export interface CollectionListResponse {
  collections: CollectionItem[];
  total: number;
  limit: number;
  offset: number;
}

export async function listCollections(
  accessToken: string,
  opts: { collection_type?: string; limit?: number; offset?: number },
): Promise<CollectionListResponse> {
  const params = new URLSearchParams();
  if (opts.collection_type) params.set("collection_type", opts.collection_type);
  params.set("limit", String(opts.limit ?? 20));
  params.set("offset", String(opts.offset ?? 0));
  return request<CollectionListResponse>(`/api/v1/collections?${params}`, accessToken);
}

export async function createCollection(
  accessToken: string,
  input: { question_id: string; collection_type: "bookmark" | "custom"; note?: string | null },
): Promise<CollectionItem> {
  return request<CollectionItem>("/api/v1/collections", accessToken, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function updateCollectionNote(
  accessToken: string,
  id: string,
  note: string | null,
): Promise<CollectionItem> {
  return request<CollectionItem>(`/api/v1/collections/${id}`, accessToken, {
    method: "PATCH",
    body: JSON.stringify({ note }),
  });
}

export async function deleteCollection(
  accessToken: string,
  id: string,
): Promise<{ id: string; deleted: boolean }> {
  return request<{ id: string; deleted: boolean }>(`/api/v1/collections/${id}`, accessToken, {
    method: "DELETE",
  });
}

// --- Notifications (Phase 2, M9, GAP-9) -------------------------------------
// In-app only. No email is ever claimed sent.

export interface NotificationItem {
  id: string;
  user_id: string;
  type: string;
  title: string;
  body: string;
  link: string | null;
  is_read: boolean;
  created_at: string | null;
}

export interface NotificationListResponse {
  items: NotificationItem[];
  total: number;
  unread_count: number;
  limit: number;
  offset: number;
}

export async function listNotifications(
  accessToken: string,
  opts: { unread_only?: boolean; limit?: number; offset?: number },
): Promise<NotificationListResponse> {
  const params = new URLSearchParams();
  if (opts.unread_only) params.set("unread_only", "true");
  params.set("limit", String(opts.limit ?? 20));
  params.set("offset", String(opts.offset ?? 0));
  return request<NotificationListResponse>(`/api/v1/notifications?${params}`, accessToken);
}

export async function markNotificationRead(
  accessToken: string,
  id: string,
): Promise<NotificationItem> {
  return request<NotificationItem>(`/api/v1/notifications/${id}/read`, accessToken, {
    method: "PATCH",
  });
}

// --- Admin (Phase 2, M9, GAP-10) --------------------------------------------
// Read-only views over real engine rows. The backend enforces the
// admin claim (require_admin); a non-admin gets 404 from every
// call below. The /admin layout guard is UX only.

export interface AdminOverview {
  users: number;
  documents: number;
  jobs: number;
  jobs_by_status: Record<string, number>;
  questions: number;
  tests: number;
  results: number;
  errors: number;
  notifications: number;
}

export interface AdminUserItem {
  user_id: string;
  full_name: string;
  phone: string | null;
  preferred_exam: string | null;
  education_level: string | null;
  documents: number;
  tests: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface AdminDocumentItem {
  id: string;
  user_id: string;
  title: string;
  file_type: string;
  file_size_bytes: number;
  page_count: number | null;
  latest_job_status: string | null;
  is_shared: boolean;
  deleted_at: string | null;
  created_at: string | null;
}

export interface AdminJobItem {
  id: string;
  user_id: string;
  document_id: string;
  document_title: string | null;
  status: string;
  retry_count: number;
  error: string | null;
  error_rows: number;
  result_summary: Record<string, unknown> | null;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface AdminErrorItem {
  id: string;
  document_id: string;
  document_title: string | null;
  job_id: string | null;
  page_number: number | null;
  stage: string | null;
  error_code: string;
  message: string;
  created_at: string | null;
}

export interface AdminQuestionItem {
  id: string;
  document_id: string;
  question_number: string | null;
  text: string;
  options_count: number;
  correct_index: number;
  answer_status: string | null;
  validation_status: string;
  extraction_method: string | null;
  created_at: string | null;
}

export interface AdminListResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export async function getAdminOverview(accessToken: string): Promise<AdminOverview> {
  return request<AdminOverview>("/api/v1/admin/overview", accessToken);
}

export async function listAdminUsers(
  accessToken: string,
  opts: { limit?: number; offset?: number },
): Promise<AdminListResponse<AdminUserItem>> {
  const params = new URLSearchParams();
  params.set("limit", String(opts.limit ?? 20));
  params.set("offset", String(opts.offset ?? 0));
  return request<AdminListResponse<AdminUserItem>>(`/api/v1/admin/users?${params}`, accessToken);
}

export async function listAdminDocuments(
  accessToken: string,
  opts: { user_id?: string; limit?: number; offset?: number },
): Promise<AdminListResponse<AdminDocumentItem>> {
  const params = new URLSearchParams();
  if (opts.user_id) params.set("user_id", opts.user_id);
  params.set("limit", String(opts.limit ?? 20));
  params.set("offset", String(opts.offset ?? 0));
  return request<AdminListResponse<AdminDocumentItem>>(
    `/api/v1/admin/documents?${params}`,
    accessToken,
  );
}

export interface DocumentSharing {
  id: string;
  user_id: string;
  title: string;
  is_shared: boolean;
}

export async function setDocumentSharing(
  accessToken: string,
  documentId: string,
  isShared: boolean,
): Promise<DocumentSharing> {
  return request<DocumentSharing>(
    `/api/v1/admin/documents/${documentId}/sharing`,
    accessToken,
    { method: "PATCH", body: JSON.stringify({ is_shared: isShared }) },
  );
}

export async function listAdminJobs(
  accessToken: string,
  opts: { status?: string; limit?: number; offset?: number },
): Promise<AdminListResponse<AdminJobItem>> {
  const params = new URLSearchParams();
  if (opts.status) params.set("status", opts.status);
  params.set("limit", String(opts.limit ?? 20));
  params.set("offset", String(opts.offset ?? 0));
  return request<AdminListResponse<AdminJobItem>>(`/api/v1/admin/jobs?${params}`, accessToken);
}

export async function listAdminErrors(
  accessToken: string,
  opts: { limit?: number; offset?: number },
): Promise<AdminListResponse<AdminErrorItem>> {
  const params = new URLSearchParams();
  params.set("limit", String(opts.limit ?? 20));
  params.set("offset", String(opts.offset ?? 0));
  return request<AdminListResponse<AdminErrorItem>>(`/api/v1/admin/errors?${params}`, accessToken);
}

export async function listAdminQuestions(
  accessToken: string,
  opts: { validation_status?: string; document_id?: string; search?: string; limit?: number; offset?: number },
): Promise<AdminListResponse<AdminQuestionItem>> {
  const params = new URLSearchParams();
  if (opts.validation_status) params.set("validation_status", opts.validation_status);
  if (opts.document_id) params.set("document_id", opts.document_id);
  if (opts.search) params.set("search", opts.search);
  params.set("limit", String(opts.limit ?? 20));
  params.set("offset", String(opts.offset ?? 0));
  return request<AdminListResponse<AdminQuestionItem>>(
    `/api/v1/admin/questions?${params}`,
    accessToken,
  );
}

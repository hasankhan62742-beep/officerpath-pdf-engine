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
  opts: { limit?: number; offset?: number; status?: JobStatus },
): Promise<DocumentListResponse> {
  const params = new URLSearchParams();
  params.set("limit", String(opts.limit ?? 20));
  params.set("offset", String(opts.offset ?? 0));
  if (opts.status) params.set("status", opts.status);
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

/** Upload ONE file (single-upload endpoint, honest per-file progress). */
export async function uploadFile(
  accessToken: string,
  file: File,
  onProgress?: (percent: number) => void,
): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file, file.name);
  return uploadForm<UploadResult>("/api/v1/documents/upload", accessToken, form, onProgress);
}

/** Upload 2–20 files in one batch request (one rate-limit charge). */
export async function uploadBatch(
  accessToken: string,
  files: File[],
  onProgress?: (percent: number) => void,
): Promise<BatchUploadResponse> {
  const form = new FormData();
  for (const file of files) form.append("files", file, file.name);
  return uploadForm<BatchUploadResponse>(
    "/api/v1/documents/upload/batch",
    accessToken,
    form,
    onProgress,
  );
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

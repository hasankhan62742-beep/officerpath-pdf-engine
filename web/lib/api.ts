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

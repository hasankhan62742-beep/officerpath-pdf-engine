// OfficerPath AI — Supabase auth callback (Phase 2, M3).
//
// Supabase redirects here after the user clicks the link in a
// confirmation or password-reset email. The `code` is exchanged for
// a session (the PKCE verifier lives in the browser cookies set
// when the email was requested).
//
// On a confirmation (type absent, or type=signup): the session is
// created, and the user's engine profile is created from the
// metadata collected at sign-up (full_name, phone, preferred_exam,
// education_level). If the engine is unreachable, profile creation
// is retried lazily by /dashboard/profile (create-on-404) — the
// sign-in itself never fails because of it.
// On a password reset (type=recovery): the session is created and
// the user is sent to /auth/reset-password to choose a new password.

import { NextResponse, type NextRequest } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { API_URL } from "@/lib/api";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const code = searchParams.get("code");
  const type = searchParams.get("type");
  const next = searchParams.get("next") ?? "/dashboard/profile";

  if (!code) {
    return NextResponse.redirect(new URL("/login?error=missing_code", request.url));
  }

  const supabase = await createClient();
  const { data, error } = await supabase.auth.exchangeCodeForSession(code);

  if (error || !data.session) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("error", "invalid_link");
    return NextResponse.redirect(loginUrl);
  }

  if (type === "recovery") {
    return NextResponse.redirect(new URL("/auth/reset-password", request.url));
  }

  // First confirmed sign-in: create the engine profile from the
  // sign-up metadata. Best effort — a failure is logged server-side
  // and the profile page creates it on first visit instead.
  const meta = data.user.user_metadata ?? {};
  const fullName = typeof meta.full_name === "string" ? meta.full_name.trim() : "";
  if (fullName) {
    try {
      const res = await fetch(`${API_URL}/api/v1/me`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${data.session.access_token}`,
        },
        body: JSON.stringify({
          full_name: fullName,
          phone: typeof meta.phone === "string" ? meta.phone : null,
          preferred_exam: typeof meta.preferred_exam === "string" ? meta.preferred_exam : null,
          education_level: typeof meta.education_level === "string" ? meta.education_level : null,
        }),
      });
      if (!res.ok && res.status !== 409) {
        console.error("M3 callback: engine profile create failed", res.status);
      }
    } catch (err) {
      console.error("M3 callback: engine profile create unreachable", err);
    }
  }

  const redirectTo = next.startsWith("/") ? next : "/dashboard/profile";
  return NextResponse.redirect(new URL(redirectTo, request.url));
}

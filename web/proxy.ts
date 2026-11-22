// OfficerPath AI — auth proxy (Phase 2, M3).
//
// Next.js 16 renamed the `middleware` convention to `proxy` (the
// `middleware.ts` file is deprecated). This file runs before routes
// render: it refreshes the Supabase session on every matched request
// and guards the protected area.
//
// Guard rules:
//  - /dashboard/* without a session  -> /login?next=<path>
//  - /login, /register with a session -> /dashboard/profile
// The dashboard layout re-checks the session server-side as well —
// the proxy is a convenience gate, never the only check (Next.js
// docs warn a matcher change can silently drop proxy coverage).

import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

const PROTECTED_PREFIX = "/dashboard";
const AUTH_PAGES = new Set(["/login", "/register"]);

export async function proxy(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value),
          );
          supabaseResponse = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options),
          );
        },
      },
    },
  );

  // getUser() asks Supabase Auth itself and refreshes the session
  // cookies when needed. A missing/invalid token returns null, never
  // throws — so an unauthenticated visitor is simply redirected.
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const pathname = request.nextUrl.pathname;

  if (pathname.startsWith(PROTECTED_PREFIX) && !user) {
    const loginUrl = request.nextUrl.clone();
    loginUrl.pathname = "/login";
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  if (AUTH_PAGES.has(pathname) && user) {
    const dashboardUrl = request.nextUrl.clone();
    dashboardUrl.pathname = "/dashboard/profile";
    dashboardUrl.search = "";
    return NextResponse.redirect(dashboardUrl);
  }

  return supabaseResponse;
}

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/login",
    "/register",
    "/forgot-password",
    "/auth/reset-password",
  ],
};

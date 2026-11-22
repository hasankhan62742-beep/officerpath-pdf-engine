// OfficerPath AI — Supabase browser client (Phase 2, M3).
//
// The browser holds ONLY the publishable anon key (from env) and the
// user's session tokens, stored in cookies by @supabase/ssr so the
// server (proxy.ts, Server Components) can read the same session.
// The service-role key must NEVER appear here or anywhere in web/.

import { createBrowserClient } from "@supabase/ssr";

export function createClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anonKey) {
    throw new Error(
      "Supabase is not configured: set NEXT_PUBLIC_SUPABASE_URL and " +
        "NEXT_PUBLIC_SUPABASE_ANON_KEY in web/.env.local (see web/.env.example).",
    );
  }
  return createBrowserClient(url, anonKey);
}

// OfficerPath AI — Supabase server client (Phase 2, M3).
//
// Used by Server Components, Route Handlers and proxy.ts. Reads the
// session from the same cookies the browser client writes, so the
// server sees the same user. Never decodes or trusts a token
// locally — getUser() asks Supabase Auth itself.

import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

export async function createClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anonKey) {
    throw new Error(
      "Supabase is not configured: set NEXT_PUBLIC_SUPABASE_URL and " +
        "NEXT_PUBLIC_SUPABASE_ANON_KEY in web/.env.local (see web/.env.example).",
    );
  }
  const cookieStore = await cookies();
  return createServerClient(url, anonKey, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        try {
          cookiesToSet.forEach(({ name, value, options }) =>
            cookieStore.set(name, value, options),
          );
        } catch {
          // setAll is called from Server Components, where setting
          // cookies is not allowed — the proxy refreshes them.
        }
      },
    },
  });
}

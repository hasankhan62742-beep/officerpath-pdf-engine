// OfficerPath AI — protected dashboard shell (Phase 2, M3).
//
// Server-side session check: the proxy already redirects
// unauthenticated visitors, but this layout re-checks here so the
// protected area stays protected even if the proxy matcher changes.
// The full dashboard (stats, documents) is M4 — this shell only
// carries the profile page in M3.

import type { ReactNode } from "react";
import Link from "next/link";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

export default async function DashboardLayout({
  children,
}: {
  children: ReactNode;
}) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login?next=/dashboard/profile");
  }

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-10 sm:px-6">
      <nav aria-label="Dashboard" className="mb-8 flex flex-wrap gap-2">
        <Link
          href="/dashboard/profile"
          className="rounded-full bg-brand-600 px-4 py-2 text-sm font-semibold text-white"
          aria-current="page"
        >
          Profile
        </Link>
        <span
          className="rounded-full border border-slate-300 px-4 py-2 text-sm font-medium text-slate-500"
          title="Documents and statistics arrive in Milestone 4"
        >
          Documents — coming in M4
        </span>
      </nav>
      {children}
    </div>
  );
}

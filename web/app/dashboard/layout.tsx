// OfficerPath AI — protected dashboard shell (Phase 2, M3/M4).
//
// Server-side session check: the proxy already redirects
// unauthenticated visitors, but this layout re-checks here so the
// protected area stays protected even if the proxy matcher changes.

import type { ReactNode } from "react";
import { redirect } from "next/navigation";
import { DashboardNav } from "@/components/dashboard/dashboard-nav";
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
    redirect("/login?next=/dashboard");
  }

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-10 sm:px-6">
      <DashboardNav />
      {children}
    </div>
  );
}

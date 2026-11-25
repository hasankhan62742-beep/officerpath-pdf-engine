// OfficerPath AI — protected dashboard shell (Phase 2, M3/M4).
//
// Server-side session check: the proxy already redirects
// unauthenticated visitors, but this layout re-checks here so the
// protected area stays protected even if the proxy matcher changes.

import type { Metadata } from "next";
import type { ReactNode } from "react";
import { redirect } from "next/navigation";
import { DashboardNav } from "@/components/dashboard/dashboard-nav";
import { Providers } from "@/components/providers";
import { createClient } from "@/lib/supabase/server";

// M9 SEO: the whole dashboard is private — never indexed.
export const metadata: Metadata = {
  robots: {
    index: false,
    follow: false,
  },
};

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

  // Admin link in the dashboard nav is UX only (same claim the admin
  // layout reads); the engine enforces admin access server-side.
  const appMetadata = (user.app_metadata ?? {}) as Record<string, unknown>;
  const isAdmin = appMetadata.is_admin === true;

  return (
    <Providers>
      <div className="mx-auto w-full max-w-5xl px-4 py-10 sm:px-6">
        <DashboardNav isAdmin={isAdmin} />
        {children}
      </div>
    </Providers>
  );
}

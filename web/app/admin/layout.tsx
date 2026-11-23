// OfficerPath AI — admin shell (Phase 2, M9, GAP-10).
//
// Server-side guard: no session -> /login; session without the
// app_metadata.is_admin claim -> /dashboard. This is UX ONLY —
// the real enforcement is the engine's require_admin dependency,
// which returns 404 for non-admins on every /api/v1/admin/*
// route. A student can never reach admin data by changing a URL
// or flipping frontend state.
//
// M9 SEO: the admin area is private — never indexed.

import type { Metadata } from "next";
import type { ReactNode } from "react";
import { redirect } from "next/navigation";
import { AdminNav } from "@/components/admin/admin-nav";
import { Providers } from "@/components/providers";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  robots: {
    index: false,
    follow: false,
  },
};

export default async function AdminLayout({ children }: { children: ReactNode }) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login?next=/admin");
  }

  const appMetadata = (user.app_metadata ?? {}) as Record<string, unknown>;
  if (appMetadata.is_admin !== true) {
    redirect("/dashboard");
  }

  return (
    <Providers>
      <div className="mx-auto w-full max-w-5xl px-4 py-10 sm:px-6">
        <AdminNav />
        {children}
      </div>
    </Providers>
  );
}

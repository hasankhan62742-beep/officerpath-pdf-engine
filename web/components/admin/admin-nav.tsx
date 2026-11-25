// OfficerPath AI — admin section navigation (Phase 2, M9).
// Mirrors DashboardNav: current section marked, plain links.

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/admin", label: "Overview", exact: true },
  { href: "/admin/users", label: "Users", exact: false },
  { href: "/admin/documents", label: "Documents", exact: false },
  { href: "/admin/jobs", label: "Jobs", exact: false },
  { href: "/admin/errors", label: "Errors", exact: false },
  { href: "/admin/community", label: "Community", exact: false },
  { href: "/admin/questions", label: "Questions", exact: false },
];

export function AdminNav() {
  const pathname = usePathname();
  return (
    <nav aria-label="Admin" className="mb-8 flex flex-wrap gap-2">
      {LINKS.map((link) => {
        const active = link.exact
          ? pathname === link.href
          : pathname === link.href || pathname.startsWith(`${link.href}/`);
        return (
          <Link
            key={link.href}
            href={link.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "rounded-full px-4 py-2 text-sm font-medium",
              active
                ? "bg-brand-600 font-semibold text-white"
                : "border border-slate-300 text-slate-700 hover:bg-slate-50",
            )}
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}

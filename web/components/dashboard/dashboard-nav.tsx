"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/dashboard", label: "Dashboard", exact: true },
  { href: "/dashboard/upload", label: "Upload", exact: false },
  { href: "/dashboard/documents", label: "Documents", exact: false },
  { href: "/dashboard/questions", label: "Questions", exact: false },
  { href: "/dashboard/tests", label: "Tests", exact: false },
  { href: "/dashboard/profile", label: "Profile", exact: true },
];

/** Dashboard section navigation with the current section marked. */
export function DashboardNav() {
  const pathname = usePathname();
  return (
    <nav aria-label="Dashboard" className="mb-8 flex flex-wrap gap-2">
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

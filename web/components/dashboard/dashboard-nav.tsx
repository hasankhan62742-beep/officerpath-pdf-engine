"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { getSessionToken, listNotifications } from "@/lib/api";

const LINKS = [
  { href: "/dashboard", label: "Dashboard", exact: true },
  { href: "/dashboard/upload", label: "Upload", exact: false },
  { href: "/dashboard/documents", label: "Documents", exact: false },
  { href: "/dashboard/questions", label: "Questions", exact: false },
  { href: "/dashboard/add-questions", label: "Add Questions", exact: false },
  { href: "/dashboard/tests", label: "Tests", exact: false },
  { href: "/dashboard/results", label: "Results", exact: false },
  { href: "/dashboard/mistakes", label: "Mistakes", exact: false },
  { href: "/dashboard/notifications", label: "Notifications", exact: false },
  { href: "/dashboard/profile", label: "Profile", exact: true },
];

const ADMIN_LINK = { href: "/admin", label: "Admin", exact: false };

/**
 * Dashboard section navigation with the current section marked.
 *
 * The Admin link is shown only when `isAdmin` is true — the dashboard
 * layout reads `app_metadata.is_admin` from the server-side session
 * (same claim as the admin layout). This is UX only: the real
 * enforcement is the engine's require_admin (non-admins get 404 on
 * every /api/v1/admin/* route, and /admin redirects them away).
 */
export function DashboardNav({ isAdmin = false }: { isAdmin?: boolean }) {
  const pathname = usePathname();
  const links = isAdmin ? [...LINKS, ADMIN_LINK] : LINKS;
  // Unread notification count (M9): the badge shows real rows
  // only; a missing token or failed fetch simply hides it.
  const { data: unreadCount } = useQuery({
    queryKey: ["notifications-unread-count"],
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) return 0;
      const res = await listNotifications(token, { unread_only: true, limit: 1 });
      return res.unread_count;
    },
    staleTime: 30_000,
  });
  return (
    <nav aria-label="Dashboard" className="mb-8 flex flex-wrap gap-2">
      {links.map((link) => {
        const active = link.exact
          ? pathname === link.href
          : pathname === link.href || pathname.startsWith(`${link.href}/`);
        const showBadge = link.href === "/dashboard/notifications" && (unreadCount ?? 0) > 0;
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
            {showBadge && (
              <span
                aria-label={`${unreadCount} unread notifications`}
                className="ml-1.5 rounded-full bg-white px-1.5 py-0.5 text-xs font-bold text-brand-700"
              >
                {unreadCount}
              </span>
            )}
          </Link>
        );
      })}
    </nav>
  );
}

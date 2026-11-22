"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { NAV_LINKS, SITE_NAME } from "@/lib/site";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

function Logo() {
  return (
    <Link href="/" className="flex shrink-0 items-center gap-2.5" aria-label={`${SITE_NAME} — home`}>
      <span
        aria-hidden
        className="flex size-10 items-center justify-center rounded-xl bg-brand-600 text-base font-extrabold text-white shadow-sm"
      >
        OP
      </span>
      <span className="leading-tight">
        <span className="block text-base font-extrabold tracking-tight text-slate-900">
          OfficerPath <span className="text-brand-600">AI</span>
        </span>
        <span className="block text-[11px] font-medium text-slate-500">
          Competitive Exam Preparation
        </span>
      </span>
    </Link>
  );
}

/** Sticky site header: desktop nav + mobile hamburger menu (44px touch targets). */
export function Header() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/95 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
        <Logo />
        <nav aria-label="Primary" className="hidden items-center gap-1 lg:flex">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              aria-current={pathname === link.href ? "page" : undefined}
              className={cn(
                "rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                pathname === link.href
                  ? "bg-brand-50 text-brand-700"
                  : "text-slate-700 hover:bg-slate-100 hover:text-slate-900",
              )}
            >
              {link.label}
            </Link>
          ))}
        </nav>
        <div className="hidden items-center gap-2 lg:flex">
          <Button href="/login" variant="ghost">
            Log in
          </Button>
          <Button href="/register" size="md">
            Start Your Preparation
          </Button>
        </div>
        <button
          type="button"
          className="flex min-h-11 min-w-11 items-center justify-center rounded-lg text-slate-700 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-brand-600 lg:hidden"
          aria-expanded={open}
          aria-controls="mobile-menu"
          aria-label={open ? "Close menu" : "Open menu"}
          onClick={() => setOpen((v) => !v)}
        >
          <span aria-hidden className="text-2xl leading-none">
            {open ? "✕" : "☰"}
          </span>
        </button>
      </div>
      {open ? (
        <nav
          id="mobile-menu"
          aria-label="Mobile"
          className="border-t border-slate-200 bg-white px-4 pb-5 pt-2 lg:hidden"
        >
          <ul className="flex flex-col">
            {NAV_LINKS.map((link) => (
              <li key={link.href}>
                <Link
                  href={link.href}
                  aria-current={pathname === link.href ? "page" : undefined}
                  onClick={() => setOpen(false)}
                  className={cn(
                    "flex min-h-11 items-center rounded-lg px-3 text-base font-medium",
                    pathname === link.href
                      ? "bg-brand-50 text-brand-700"
                      : "text-slate-700 hover:bg-slate-100",
                  )}
                >
                  {link.label}
                </Link>
              </li>
            ))}
          </ul>
          <div className="mt-3 flex flex-col gap-2">
            <Button href="/login" variant="secondary" className="w-full">
              Log in
            </Button>
            <Button href="/register" className="w-full">
              Start Your Preparation
            </Button>
          </div>
        </nav>
      ) : null}
    </header>
  );
}

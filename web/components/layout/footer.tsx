"use client";

import { Suspense } from "react";
import Link from "next/link";
import { CONTACT_EMAIL, EXAMS, SITE_NAME } from "@/lib/site";
import { CurrentYear } from "@/components/layout/current-year";

const productLinks = [
  { href: "/features", label: "Features" },
  { href: "/how-it-works", label: "How It Works" },
  { href: "/exam-preparation", label: "Exam Preparation" },
  { href: "/pricing", label: "Pricing" },
  { href: "/register", label: "Register" },
];

const companyLinks = [
  { href: "/about", label: "About" },
  { href: "/contact", label: "Contact" },
  { href: "/privacy", label: "Privacy Policy" },
  { href: "/terms", label: "Terms and Conditions" },
];

export function Footer() {
  return (
    <footer className="border-t border-slate-200 bg-slate-950 text-slate-300">
      <div className="mx-auto grid max-w-7xl gap-10 px-4 py-12 sm:grid-cols-2 sm:px-6 lg:grid-cols-4 lg:px-8">
        <div>
          <p className="text-base font-extrabold tracking-tight text-white">
            OfficerPath <span className="text-brand-400">AI</span>
          </p>
          <p className="mt-3 text-sm leading-relaxed text-slate-400">
            Prepare smarter from your own books. Upload PDFs and papers, get
            traceable MCQs, and practise with timed, exam-style tests.
          </p>
          <p className="mt-4 text-sm">
            <a href={`mailto:${CONTACT_EMAIL}`} className="text-brand-400 hover:underline">
              {CONTACT_EMAIL}
            </a>
          </p>
        </div>
        <nav aria-label="Product">
          <p className="text-sm font-semibold text-white">Product</p>
          <ul className="mt-3 space-y-2.5 text-sm">
            {productLinks.map((l) => (
              <li key={l.href}>
                <Link href={l.href} className="hover:text-white">
                  {l.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
        <nav aria-label="Exams">
          <p className="text-sm font-semibold text-white">Exams</p>
          <ul className="mt-3 space-y-2.5 text-sm">
            {EXAMS.slice(0, 6).map((e) => (
              <li key={e.short}>
                <Link href="/exam-preparation" className="hover:text-white">
                  {e.short} — {e.name}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
        <nav aria-label="Company">
          <p className="text-sm font-semibold text-white">Company</p>
          <ul className="mt-3 space-y-2.5 text-sm">
            {companyLinks.map((l) => (
              <li key={l.href}>
                <Link href={l.href} className="hover:text-white">
                  {l.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </div>
      <div className="border-t border-slate-800">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-2 px-4 py-5 text-xs text-slate-500 sm:flex-row sm:px-6 lg:px-8">
          <p>
            ©{" "}
            <Suspense fallback={2026}>
              <CurrentYear />
            </Suspense>{" "}
            {SITE_NAME}. All rights reserved.
          </p>
          <p>Practice platform — exam success depends on your preparation.</p>
        </div>
      </div>
    </footer>
  );
}

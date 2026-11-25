// OfficerPath AI — named study collections on the Main Page (B1/B2).
//
// The three shared collections the user asked for as visible
// tabs/sections: "PPSC Past Paper 2026", "Most Important
// Questions — Computer", "Fact Book for PMS and CSS 2027".
// Titles + counts only, from the public study-collections
// endpoint — no login needed to see them. Opening a paper's
// questions needs a login (user decision #1); the read page
// enforces that, and the link here says so.
//
// Naming rules, enforced by construction: "Past Papers" is
// said only about the PPSC collection — the Computer and Fact
// Book collections are question banks, never past papers. The
// year on a PPSC paper is derived from its title (decision
// #2), never a separate tag. The forbidden source names never
// appear anywhere — not in copy, not in code, not in comments.
//
// Public page: no React Query here (providers live in the
// dashboard/admin layouts only, M10) — plain fetch on mount.

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Alert } from "@/components/ui/alert";
import { SectionHeading } from "@/components/ui/section-heading";
import { Spinner } from "@/components/ui/spinner";
import {
  listStudyCollections,
  type StudyCollection,
  type StudyCollectionDocument,
} from "@/lib/api";
import { cn } from "@/lib/utils";

/** Short honest description per known collection; anything a
 * future import adds gets the generic line — never invented. */
export function collectionBlurb(name: string): string {
  if (name === "PPSC Past Paper 2026") {
    return "Past papers 2026 — each paper on its own page, every question checked against the printed answer key.";
  }
  if (name === "Most Important Questions — Computer") {
    return "The most important Computer questions, collected for revision — MCQs plus one-liner Q&A cards.";
  }
  if (name === "Fact Book for PMS and CSS 2027") {
    return "Current-affairs facts and practice questions for PMS & CSS 2027.";
  }
  return "A shared question collection.";
}

/** The year a PPSC paper belongs to, derived from its title —
 * no separate tag (user decision #2). Null when the title
 * carries no year. */
function yearFromTitle(title: string): string | null {
  const match = title.match(/\b(19|20)\d{2}\b/);
  return match ? match[0] : null;
}

export function CollectionDocumentRow({
  collection,
  doc,
}: {
  collection: StudyCollection;
  doc: StudyCollectionDocument;
}) {
  const year = yearFromTitle(doc.title);
  const sections = Object.entries(doc.sections ?? {}).slice(0, 3);
  const extraSections = Object.keys(doc.sections ?? {}).length - sections.length;
  return (
    <li className="rounded-2xl border border-slate-200 bg-white p-5 shadow-[var(--shadow-card)]">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="text-base font-semibold text-slate-900">{doc.title}</h3>
        <span className="flex items-center gap-2">
          {year ? (
            <span className="rounded-full bg-brand-50 px-2 py-0.5 text-xs font-bold text-brand-700">
              {year}
            </span>
          ) : null}
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-700">
            {doc.question_count.toLocaleString("en-US")} question
            {doc.question_count === 1 ? "" : "s"}
          </span>
        </span>
      </div>
      {sections.length > 0 ? (
        <p className="mt-2 text-sm text-slate-600">
          {sections
            .map(([name, value]) => `${name} · ${value}`)
            .join(" — ")}
          {extraSections > 0 ? ` — +${extraSections} more` : ""}
        </p>
      ) : null}
      <p className="mt-3">
        <Link
          href={`/collections/${collection.slug}/${doc.id}`}
          className="text-sm font-medium text-brand-700 hover:underline"
        >
          Read the questions →
        </Link>
      </p>
    </li>
  );
}

export function CollectionsSection({ showHeading = true }: { showHeading?: boolean }) {
  const [collections, setCollections] = useState<StudyCollection[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeSlug, setActiveSlug] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listStudyCollections()
      .then((res) => {
        if (cancelled) return;
        setCollections(res.collections);
        setActiveSlug(res.collections[0]?.slug ?? null);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "The collections did not load.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const active =
    collections?.find((c) => c.slug === activeSlug) ?? collections?.[0] ?? null;

  return (
    <section id="collections" className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
      {showHeading ? (
        <SectionHeading
          eyebrow="Question collections"
          title="Past papers & question banks, ready to read"
          description="Three shared collections from the bank — open a paper and read its questions. Reading needs a free account."
        />
      ) : null}
      {error ? (
        <Alert tone="danger" title="The collections did not load">
          {error} Try again in a moment — the engine may be waking up.
        </Alert>
      ) : collections === null ? (
        <div className="flex items-center gap-2 py-10 text-slate-600">
          <Spinner /> Loading the collections…
        </div>
      ) : collections.length === 0 ? (
        <p className="py-10 text-slate-600">
          No collections yet — the first shared collection will appear here.
        </p>
      ) : (
        <div className="mt-10">
          <div role="tablist" aria-label="Question collections" className="flex flex-wrap gap-2">
            {collections.map((collection) => (
              <button
                key={collection.slug}
                type="button"
                role="tab"
                aria-selected={active?.slug === collection.slug}
                onClick={() => setActiveSlug(collection.slug)}
                className={cn(
                  "rounded-full px-4 py-2 text-sm font-semibold transition-colors",
                  active?.slug === collection.slug
                    ? "bg-brand-600 text-white"
                    : "bg-slate-100 text-slate-700 hover:bg-slate-200",
                )}
              >
                {collection.name}
                <span className="ml-2 text-xs font-normal opacity-80">
                  {collection.question_count.toLocaleString("en-US")}
                </span>
              </button>
            ))}
          </div>
          {active ? (
            <div role="tabpanel" className="mt-6">
              <p className="max-w-3xl text-base leading-relaxed text-slate-600">
                {collectionBlurb(active.name)}
              </p>
              <ul className="mt-5 space-y-4">
                {active.documents.map((doc) => (
                  <CollectionDocumentRow key={doc.id} collection={active} doc={doc} />
                ))}
              </ul>
              <p className="mt-5 text-sm text-slate-500">
                {active.question_count.toLocaleString("en-US")} question
                {active.question_count === 1 ? "" : "s"} in {active.document_count} document
                {active.document_count === 1 ? "" : "s"} ·{" "}
                <Link href="/login" className="font-medium text-brand-700 hover:underline">
                  Sign in
                </Link>{" "}
                to read them.
              </p>
            </div>
          ) : null}
        </div>
      )}
    </section>
  );
}

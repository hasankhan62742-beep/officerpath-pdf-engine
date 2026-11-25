// OfficerPath AI — study collections index (B1/B2).
//
// Public: the three named collections as tabs — PPSC Past Paper
// 2026, Most Important Questions — Computer, Fact Book for PMS
// and CSS 2027. Titles + counts only; reading a paper's
// questions needs a login.

import type { Metadata } from "next";
import { CollectionsSection } from "@/components/landing/collections-section";
import { SectionHeading } from "@/components/ui/section-heading";

export const metadata: Metadata = {
  title: "Study Collections | OfficerPath AI",
  description:
    "Past papers and shared question collections — PPSC Past Paper 2026, Most Important Questions — Computer, Fact Book for PMS and CSS 2027.",
};

export default function CollectionsPage() {
  return (
    <>
      <section className="mx-auto max-w-7xl px-4 pt-14 sm:px-6 lg:px-8">
        <SectionHeading
          eyebrow="Question collections"
          title="Study collections"
          description="Past papers and shared question banks from the bank. Open a paper and read its questions — reading needs a free account."
          level="h1"
          align="left"
        />
      </section>
      <CollectionsSection showHeading={false} />
    </>
  );
}

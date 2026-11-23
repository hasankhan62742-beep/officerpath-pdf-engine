import type { Metadata } from "next";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { SectionHeading } from "@/components/ui/section-heading";
import { SITE_NAME, SITE_URL } from "@/lib/site";

export const metadata: Metadata = {
  title: `Pricing | ${SITE_NAME}`,
  description:
    "OfficerPath AI is free to use during this phase. Paid plans and subscription management are planned for Phase 3 — no prices are charged or promised yet.",
  alternates: {
    canonical: `${SITE_URL}/pricing`,
  },
  openGraph: {
    url: `${SITE_URL}/pricing`,
  },
};

const FREE_FEATURES = [
  "Register and verify your email",
  "Upload PDFs and images of your books and papers",
  "MCQ extraction with evidence and review",
  "Question bank with search, filters and bookmarks",
  "Custom tests — 25, 50, 100, 150 or 200 questions",
  "Timed exams with PPSC-style marking",
  "Results, analytics and test history",
  "Mistake notebook",
];

const COMING_FEATURES = [
  "Subscription plans with usage limits",
  "Payment processing",
  "Premium question sets",
  "Advanced analytics and study plans",
];

export default function PricingPage() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-14 sm:px-6 lg:px-8">
      <SectionHeading
        align="left"
        level="h1"
        eyebrow="Pricing"
        title="Free during this phase"
        description="There is no payment system yet, and no price list to show you. Everything below is free to use right now — paid plans are planned for Phase 3, and nothing will be charged without your clear agreement."
      />

      <div className="mt-10 grid gap-5 lg:grid-cols-2">
        <Card className="border-brand-300 ring-1 ring-brand-200">
          <div className="flex items-center justify-between gap-3">
            <CardTitle>Free — available now</CardTitle>
            <Badge tone="success">Current plan</Badge>
          </div>
          <p className="mt-2 text-3xl font-extrabold tracking-tight text-slate-900">
            Rs 0 <span className="text-base font-medium text-slate-500">/ no card required</span>
          </p>
          <CardDescription>
            The full Phase 2 platform, free while it is being built and
            verified. Your account, documents, tests and results are yours.
          </CardDescription>
          <ul className="mt-5 space-y-2.5 text-sm text-slate-700">
            {FREE_FEATURES.map((f) => (
              <li key={f} className="flex gap-2.5">
                <span aria-hidden className="font-bold text-success-600">✓</span>
                {f}
              </li>
            ))}
          </ul>
          <div className="mt-6">
            <Button href="/register">Start free</Button>
          </div>
        </Card>

        <Card>
          <div className="flex items-center justify-between gap-3">
            <CardTitle>Paid plans — coming in Phase 3</CardTitle>
            <Badge tone="accent">Planned</Badge>
          </div>
          <p className="mt-2 text-3xl font-extrabold tracking-tight text-slate-900">
            Not priced yet
          </p>
          <CardDescription>
            Subscription plans and payment processing belong to Phase 3.
            Prices will be published here only when the payment system is
            real — no prices are promised or implied today.
          </CardDescription>
          <ul className="mt-5 space-y-2.5 text-sm text-slate-700">
            {COMING_FEATURES.map((f) => (
              <li key={f} className="flex gap-2.5">
                <span aria-hidden className="font-bold text-accent-600">○</span>
                {f}
              </li>
            ))}
          </ul>
          <div className="mt-6">
            <Button href="/register" variant="secondary">
              Start free now
            </Button>
          </div>
        </Card>
      </div>

      <p className="mt-8 max-w-3xl text-sm leading-relaxed text-slate-500">
        Honest note: because there is no payment system in this phase, the
        free plan has no usage limits enforced by billing. Fair-use limits
        may be introduced with the paid plans in Phase 3, and will be
        announced before they apply.
      </p>
    </div>
  );
}

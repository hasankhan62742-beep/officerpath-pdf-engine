import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { SectionHeading } from "@/components/ui/section-heading";
import { PakistanMapWatermark } from "@/components/landing/pakistan-map";
import { RotatingTagline } from "@/components/landing/rotating-tagline";
import { EXAMS, SITE_DESCRIPTION, SITE_NAME, SITE_URL } from "@/lib/site";

export const metadata: Metadata = {
  title: `${SITE_NAME} — Prepare Smarter. Practice Better. Become Exam Ready.`,
  description: SITE_DESCRIPTION,
  alternates: {
    canonical: SITE_URL,
  },
  openGraph: {
    url: SITE_URL,
  },
};

// Structured data (M9 SEO): Organization + WebSite, using only
// real site facts — no invented ratings, counts, or partnerships.
const STRUCTURED_DATA = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      "@id": `${SITE_URL}/#organization`,
      name: SITE_NAME,
      url: SITE_URL,
      description: SITE_DESCRIPTION,
      email: "hello@abdulqadeerml.com",
    },
    {
      "@type": "WebSite",
      "@id": `${SITE_URL}/#website`,
      url: SITE_URL,
      name: SITE_NAME,
      description: SITE_DESCRIPTION,
      publisher: { "@id": `${SITE_URL}/#organization` },
    },
  ],
};

const FEATURES = [
  {
    title: "Prepare from your own books",
    body: "Upload the books, notes and past papers you already study from. The platform works with your material — not a fixed, generic syllabus.",
    tone: "bg-brand-100 text-brand-700",
    mark: "◈",
  },
  {
    title: "Upload PDFs and images",
    body: "PDFs, JPG and PNG scans, multi-page documents. The Python engine reads digital text first and OCRs scanned pages where needed.",
    tone: "bg-info-100 text-info-700",
    mark: "⇪",
  },
  {
    title: "Extract traceable MCQs",
    body: "Every question keeps its source document, page and evidence. Answers are never invented — an unknown answer stays unknown.",
    tone: "bg-success-100 text-success-700",
    mark: "✓",
  },
  {
    title: "Generate customised tests",
    body: "Build tests of 25, 50, 100, 150 or 200 questions from your documents, subjects, topics or mistakes — with a saved snapshot that never changes.",
    tone: "bg-accent-100 text-accent-700",
    mark: "▦",
  },
  {
    title: "Practise with exam-style marking",
    body: "Timed attempts with PPSC-style marking: +1 correct, −0.25 incorrect, 0 unattempted. Results are calculated on the server, not in the browser.",
    tone: "bg-brand-100 text-brand-700",
    mark: "◷",
  },
  {
    title: "Track performance, fix weak areas",
    body: "Subject-wise analytics, test history and a mistake notebook show exactly where you lose marks — so the next test is better than the last.",
    tone: "bg-info-100 text-info-700",
    mark: "↗",
  },
];

const STEPS = [
  {
    n: "1",
    title: "Create your free account",
    body: "Register with your email and choose the exam you are preparing for. Your documents and results stay private to you.",
  },
  {
    n: "2",
    title: "Upload your material",
    body: "Drop in a PDF or a photo of a paper. The engine extracts questions, options and answers — with evidence for every answer.",
  },
  {
    n: "3",
    title: "Review and build a test",
    body: "Check what was extracted, fix anything that needs review, then generate a test of the size and subjects you want.",
  },
  {
    n: "4",
    title: "Attempt, analyse, improve",
    body: "Take the timed test, see your score and weak areas, and practise your mistakes again until they stop being mistakes.",
  },
];

export default function HomePage() {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(STRUCTURED_DATA) }}
      />
      {/* Hero */}
      <section className="relative overflow-hidden bg-gradient-to-b from-brand-50 via-white to-white">
        <div className="relative mx-auto max-w-7xl px-4 pb-16 pt-14 sm:px-6 sm:pt-20 lg:px-8">
          <div className="grid items-center gap-10 lg:grid-cols-[1.15fr_0.85fr] lg:gap-12">
            <div className="hero-enter max-w-3xl">
              <p className="inline-flex items-center rounded-full bg-white px-3 py-1 text-xs font-bold uppercase tracking-widest text-brand-700 ring-1 ring-brand-200">
                PPSC · FPSC · CSS · PMS · NTS & more
              </p>
              <h1 className="mt-5 text-4xl font-extrabold leading-[1.1] tracking-tight text-slate-900 sm:text-5xl lg:text-6xl">
                Prepare Smarter. Practice Better.{" "}
                <span className="text-brand-600">Become Exam Ready.</span>
              </h1>
              <p className="mt-5 max-w-2xl text-lg leading-relaxed text-slate-600">
                OfficerPath AI turns your own books, PDFs and past papers into
                structured, traceable MCQs — then helps you practise with timed,
                exam-style tests and see exactly where you stand.
              </p>
              <RotatingTagline />
              <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                <Button href="/register" size="lg">
                  Start Your Preparation
                </Button>
                <Button href="/how-it-works" variant="secondary" size="lg">
                  See how it works
                </Button>
              </div>
              <p className="mt-4 text-sm text-slate-500">
                Free during this phase. No APK to install — it works in your
                phone browser.
              </p>
            </div>
            {/* Map poster: tilted on desktop, framed as a deliberate
                card (white frame + ring + shadow + gradient glow) so
                the illustration's cream background reads as a poster,
                not an accidental box. Gentle float; no tilt on mobile. */}
            <div className="hero-enter mx-auto w-fit">
              <figure className="relative rotate-0 lg:-rotate-5">
                <div className="hero-float relative">
                  <div
                    aria-hidden
                    className="absolute -inset-5 -z-10 rounded-[2.5rem] bg-gradient-to-br from-brand-300/60 via-amber-200/50 to-emerald-200/60 blur-2xl"
                  />
                  <div className="rounded-[1.75rem] bg-white p-2.5 shadow-[var(--shadow-lift)] ring-1 ring-slate-200/80">
                    <Image
                      src="/images/pakistan-map-hero.webp"
                      width={1120}
                      height={2240}
                      alt="Illustrated map of Pakistan showing the Indus River, northern mountains, green plains and the Thar desert"
                      sizes="(max-width: 1023px) 340px, 320px"
                      preload
                      className="h-auto w-full max-w-[300px] rounded-[1.25rem] sm:max-w-[340px] lg:h-[540px] lg:w-auto lg:max-w-none"
                    />
                    <figcaption className="px-2 pb-1.5 pt-2.5 text-center text-sm font-medium text-slate-500">
                      Indus River · Karakoram · Thar Desert
                    </figcaption>
                  </div>
                </div>
              </figure>
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
        <SectionHeading
          eyebrow="What you can do"
          title="Everything you need to prepare — in one place"
          description="Built around your own material and honest about what it knows. Nothing is invented, and nothing is hidden."
        />
        <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <Card key={f.title} className="transition-shadow hover:shadow-[var(--shadow-lift)]">
              <span
                aria-hidden
                className={`inline-flex size-11 items-center justify-center rounded-xl text-lg font-bold ${f.tone}`}
              >
                {f.mark}
              </span>
              <CardTitle>
                <span className="mt-4 block">{f.title}</span>
              </CardTitle>
              <CardDescription>{f.body}</CardDescription>
            </Card>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section className="bg-slate-50">
        <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
          <SectionHeading
            eyebrow="How it works"
            title="From your book to your test in four steps"
          />
          <ol className="mt-10 grid gap-5 md:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((s) => (
              <li key={s.n} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-[var(--shadow-card)]">
                <span className="flex size-10 items-center justify-center rounded-full bg-brand-600 text-base font-extrabold text-white">
                  {s.n}
                </span>
                <h3 className="mt-4 text-base font-semibold text-slate-900">{s.title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-slate-600">{s.body}</p>
              </li>
            ))}
          </ol>
          <div className="mt-8 text-center">
            <Button href="/how-it-works" variant="secondary">
              Read the full walkthrough
            </Button>
          </div>
        </div>
      </section>

      {/* Exams */}
      <section className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
        <SectionHeading
          eyebrow="Exams covered"
          title="Built for Pakistan's competitive examinations"
          description="One platform for the papers you are actually preparing for — federal, provincial and testing-service exams."
        />
        <ul className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {EXAMS.map((e) => (
            <li key={e.short}>
              <Link
                href="/exam-preparation"
                className="block rounded-2xl border border-slate-200 bg-white p-5 shadow-[var(--shadow-card)] transition-shadow hover:shadow-[var(--shadow-lift)]"
              >
                <p className="text-lg font-extrabold text-brand-700">{e.short}</p>
                <p className="mt-1 text-sm leading-relaxed text-slate-600">{e.name}</p>
              </Link>
            </li>
          ))}
        </ul>
      </section>

      {/* Honest note + CTA */}
      <section className="mx-auto max-w-7xl px-4 pb-20 sm:px-6 lg:px-8">
        <div className="relative overflow-hidden rounded-3xl bg-slate-950 px-6 py-12 text-center sm:px-12">
          <PakistanMapWatermark className="right-[-6%] top-1/2 hidden h-[360px] w-[360px] -translate-y-1/2 text-white opacity-[0.05] md:block" />
          <h2 className="relative text-2xl font-bold tracking-tight text-white sm:text-3xl">
            Your books. Your questions. Your progress.
          </h2>
          <p className="relative mx-auto mt-3 max-w-xl text-base leading-relaxed text-slate-300">
            Start free today. Upload a paper, see what the engine extracts,
            and take your first timed test — no installation, no card.
          </p>
          <div className="relative mt-7">
            <Button href="/register" size="lg">
              Start Your Preparation
            </Button>
          </div>
          <p className="relative mt-4 text-xs text-slate-500">
            Extraction quality depends on the quality of your document. Answers
            are never fabricated — if the engine cannot verify an answer, it
            says so.
          </p>
        </div>
      </section>
    </>
  );
}

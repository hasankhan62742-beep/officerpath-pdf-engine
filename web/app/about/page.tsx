import type { Metadata } from "next";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { SectionHeading } from "@/components/ui/section-heading";
import { SITE_NAME, SITE_URL } from "@/lib/site";

export const metadata: Metadata = {
  title: `About | ${SITE_NAME}`,
  description:
    "OfficerPath AI is an AI-assisted competitive exam preparation platform that turns your own books, PDFs and past papers into traceable MCQs and timed practice tests.",
  alternates: {
    canonical: `${SITE_URL}/about`,
  },
  openGraph: {
    url: `${SITE_URL}/about`,
  },
};

export default function AboutPage() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-14 sm:px-6 lg:px-8">
      <div className="max-w-3xl">
        <p className="text-sm font-bold uppercase tracking-widest text-brand-600">About</p>
        <h1 className="mt-2 text-3xl font-extrabold tracking-tight text-slate-900 sm:text-4xl">
          Preparation that starts from your own books
        </h1>
        <p className="mt-4 text-lg leading-relaxed text-slate-600">
          OfficerPath AI is an AI-assisted competitive examination preparation
          platform for students preparing for PPSC, FPSC, BPSC, SPSC, KPSC,
          CSS, PMS, NTS and other provincial and federal examinations in
          Pakistan.
        </p>
        <p className="mt-4 text-base leading-relaxed text-slate-600">
          Most preparation platforms ask you to study their material. This
          one works the other way round: you bring the books, notes and past
          papers you already trust, and the platform turns them into
          structured, traceable multiple-choice questions — then helps you
          practise them under exam conditions and understand where you lose
          marks.
        </p>
      </div>

      <div className="mt-12 grid gap-5 md:grid-cols-3">
        <Card>
          <CardTitle>Traceable, not invented</CardTitle>
          <CardDescription>
            Every extracted question keeps its source document, page and
            evidence. If the engine cannot verify an answer, it marks it
            unknown — it never guesses and presents a guess as correct.
          </CardDescription>
        </Card>
        <Card>
          <CardTitle>Your material, your pace</CardTitle>
          <CardDescription>
            Upload a whole book or a single photographed page. Build tests of
            25 to 200 questions from the subjects and topics you choose, and
            re-attempt your mistakes until they stop being mistakes.
          </CardDescription>
        </Card>
        <Card>
          <CardTitle>Honest measurement</CardTitle>
          <CardDescription>
            Scores are calculated on the server with PPSC-style marking
            (+1 correct, −0.25 incorrect, 0 unattempted). No inflated
            numbers, no guaranteed outcomes — just your real performance,
            tracked over time.
          </CardDescription>
        </Card>
      </div>

      <div className="mt-16 max-w-3xl">
        <SectionHeading
          align="left"
          eyebrow="How it is built"
          title="A Python document engine, a modern web app"
          description="The document intelligence engine is a Python FastAPI service that reads digital text, OCRs scanned pages, detects question layouts, and resolves answers from the paper's own answer key — with a strict rule that original content is never silently changed. The web application you are using is the student-facing front end for that engine. The Flutter app remains as a legacy client; the web app is the primary product."
        />
        <div className="mt-8 flex flex-col gap-3 sm:flex-row">
          <Button href="/register">Start Your Preparation</Button>
          <Button href="/features" variant="secondary">
            Explore features
          </Button>
        </div>
      </div>
    </div>
  );
}

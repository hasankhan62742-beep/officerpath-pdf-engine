import type { Metadata } from "next";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { SectionHeading } from "@/components/ui/section-heading";
import { SITE_NAME } from "@/lib/site";

export const metadata: Metadata = {
  title: `How It Works | ${SITE_NAME}`,
  description:
    "Register, upload your books or past papers, review the extracted MCQs, build a custom test, and take a timed exam with PPSC-style marking — step by step.",
};

const STEPS = [
  {
    n: "1",
    title: "Register — free",
    body: "Create your account with an email address and choose the exam you are preparing for. Email verification is real: you will receive a verification link before your account is fully active.",
    detail: "What you provide: full name, email, password, optional phone number, preferred examination and education level. Nothing else is required.",
  },
  {
    n: "2",
    title: "Upload your material",
    body: "Upload a PDF, a scanned paper or a photo of a page. The platform accepts PDF, JPG, JPEG and PNG files, including multi-page documents. You see the file name, size, upload progress and processing status.",
    detail: "Your documents are private to your account. The original file is never modified.",
  },
  {
    n: "3",
    title: "The engine extracts MCQs",
    body: "The Python document engine reads the document — digital text first, OCR for scanned pages — detects the question layout, extracts questions and options, and resolves answers from the paper's own answer key or inline markings.",
    detail: "Every answer carries evidence: which detector found it, how confident it is, and where it came from. Unknown stays unknown.",
  },
  {
    n: "4",
    title: "Review what was extracted",
    body: "Before you practise, review the extracted questions. Anything uncertain is flagged for review. You can correct eligible content through the review workflow, and every correction is recorded — the original extraction is never silently changed.",
    detail: "Your corrections affect your own copy only. They never change another student's content.",
  },
  {
    n: "5",
    title: "Build a test",
    body: "Choose 25, 50, 100, 150 or 200 questions from all your questions, selected documents, subjects, topics, bookmarks, unattempted questions or past mistakes. The builder tells you honestly if fewer questions are available than you asked for.",
    detail: "The test saves a snapshot of its questions, options, answer key and marking rules — editing the question bank later never changes a test you already took.",
  },
  {
    n: "6",
    title: "Take the timed exam",
    body: "Attempt the test in a distraction-free interface with a question palette, mark-for-review, a server-aware timer and periodic answer saving. Submit once, with a confirmation step — duplicate submissions are prevented.",
    detail: "Marking is PPSC-style: correct +1, incorrect −0.25, unattempted 0.",
  },
  {
    n: "7",
    title: "Analyse and improve",
    body: "See your score, percentage, time taken and subject-wise performance. Review correct, incorrect and unattempted questions with their sources, save mistakes to your notebook, and build your next test from them.",
    detail: "Your history is preserved, so you can compare performance over time.",
  },
];

export default function HowItWorksPage() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-14 sm:px-6 lg:px-8">
      <SectionHeading
        align="left"
        level="h1"
        eyebrow="How it works"
        title="From your book to a better score — in seven steps"
        description="No technical knowledge is needed. If you can upload a photo, you can use this platform."
      />
      <ol className="mt-10 space-y-5">
        {STEPS.map((s) => (
          <li key={s.n}>
            <Card className="sm:flex sm:gap-6">
              <span className="flex size-12 shrink-0 items-center justify-center rounded-full bg-brand-600 text-lg font-extrabold text-white">
                {s.n}
              </span>
              <div>
                <CardTitle>{s.title}</CardTitle>
                <CardDescription>{s.body}</CardDescription>
                <p className="mt-2 text-sm leading-relaxed text-slate-500">{s.detail}</p>
              </div>
            </Card>
          </li>
        ))}
      </ol>
      <div className="mt-10 flex flex-col gap-3 sm:flex-row">
        <Button href="/register">Start Your Preparation</Button>
        <Button href="/exam-preparation" variant="secondary">
          See exams and subjects
        </Button>
      </div>
    </div>
  );
}

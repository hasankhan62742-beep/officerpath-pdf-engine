import type { Metadata } from "next";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { SectionHeading } from "@/components/ui/section-heading";
import { EXAMS, SITE_NAME, SUBJECTS } from "@/lib/site";

export const metadata: Metadata = {
  title: `Exam Preparation | ${SITE_NAME}`,
  description:
    "Prepare for PPSC, FPSC, BPSC, SPSC, KPSC, CSS, PMS and NTS with your own books — General Knowledge, Pakistan Affairs, Current Affairs, English, Mathematics and more.",
};

export default function ExamPreparationPage() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-14 sm:px-6 lg:px-8">
      <SectionHeading
        align="left"
        level="h1"
        eyebrow="Exam preparation"
        title="One platform for Pakistan's competitive examinations"
        description="Prepare from your own material for the exam you are actually sitting. Subjects and topics are flexible — you assign them, and the platform never forces a question into a category it is unsure about."
      />

      <h2 className="mt-12 text-xl font-bold text-slate-900">Examinations</h2>
      <div className="mt-5 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {EXAMS.map((e) => (
          <Card key={e.short}>
            <p className="text-lg font-extrabold text-brand-700">{e.short}</p>
            <CardTitle>
              <span className="mt-1 block text-base">{e.name}</span>
            </CardTitle>
            <CardDescription>
              Upload past papers and books for {e.short} preparation, extract
              MCQs, and build timed practice tests from them.
            </CardDescription>
          </Card>
        ))}
      </div>

      <h2 className="mt-14 text-xl font-bold text-slate-900">Subjects and topics</h2>
      <p className="mt-2 max-w-3xl text-base leading-relaxed text-slate-600">
        Questions are organised by subject and topic so you can practise
        exactly where you are weak. More subjects and examination categories
        can be added later — the system is designed to grow.
      </p>
      <div className="mt-5 flex flex-wrap gap-2">
        {SUBJECTS.map((s) => (
          <Badge key={s} tone="info" className="px-3 py-1.5 text-sm">
            {s}
          </Badge>
        ))}
      </div>

      <div className="mt-14 rounded-2xl border border-slate-200 bg-slate-50 p-6 sm:p-8">
        <h2 className="text-xl font-bold text-slate-900">How preparation works here</h2>
        <ol className="mt-4 list-decimal space-y-2 pl-5 text-base leading-relaxed text-slate-600">
          <li>Upload the book or past paper for the exam you are preparing for.</li>
          <li>Review the extracted questions and assign subjects and topics.</li>
          <li>Build a test from the subjects where you score lowest.</li>
          <li>Attempt it under timed, exam-style conditions.</li>
          <li>Study your mistakes in the mistake notebook and test them again.</li>
        </ol>
        <div className="mt-6">
          <Button href="/register">Start Your Preparation</Button>
        </div>
      </div>
    </div>
  );
}

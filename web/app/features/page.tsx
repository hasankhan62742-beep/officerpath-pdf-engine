import type { Metadata } from "next";
import { Accordion } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { SectionHeading } from "@/components/ui/section-heading";
import { SITE_NAME, SITE_URL } from "@/lib/site";

export const metadata: Metadata = {
  title: `Features | ${SITE_NAME}`,
  description:
    "Upload your books, extract traceable MCQs, build custom tests, take timed exams with PPSC-style marking, and track your performance with OfficerPath AI.",
  alternates: {
    canonical: `${SITE_URL}/features`,
  },
  openGraph: {
    url: `${SITE_URL}/features`,
  },
};

const FEATURES = [
  {
    title: "Document upload",
    body: "PDFs, JPG and PNG files, scanned papers and multi-page documents. Drag and drop, with real upload progress and processing status for every file.",
    badge: "Core",
  },
  {
    title: "MCQ extraction with evidence",
    body: "The Python engine extracts questions, four options and answers, and attaches the evidence behind each answer — source page, detector and confidence. Unknown answers are labelled unknown.",
    badge: "Core",
  },
  {
    title: "Question review",
    body: "Review what was extracted before you practise it. Correct mistakes through an auditable review workflow — the original extraction is never silently overwritten.",
    badge: "Core",
  },
  {
    title: "Question bank",
    body: "Search, filter and organise questions by subject, topic and source document. Bookmark the important ones and keep them private to your account.",
    badge: "Core",
  },
  {
    title: "Custom test builder",
    body: "Tests of 25, 50, 100, 150 or 200 questions from all your questions, selected documents, subjects, topics, bookmarks, unattempted questions or past mistakes. Every test saves a snapshot, so editing the question bank never changes a past test.",
    badge: "Core",
  },
  {
    title: "Timed examination interface",
    body: "Question palette, mark-for-review, clear response, progress indicator and a reliable server-aware timer. Answers are saved periodically, so a refresh or a dropped connection does not wipe your attempt.",
    badge: "Core",
  },
  {
    title: "PPSC-style marking",
    body: "Correct +1, incorrect −0.25, unattempted 0 — calculated on the server and stored with the test session, so results are consistent everywhere.",
    badge: "Core",
  },
  {
    title: "Results and analytics",
    body: "Score, percentage, time taken, subject-wise and topic-wise performance, weak and strong areas, and improvement over time — all computed from your saved attempts.",
    badge: "Core",
  },
  {
    title: "Mistake notebook and bookmarks",
    body: "Every incorrect answer can be saved to your mistake notebook with a personal note. Practise them again and track repeated mistakes by subject.",
    badge: "Core",
  },
  {
    title: "Test history",
    body: "Every past test keeps its original questions, options, answer key snapshot and marking configuration. Re-attempt a test or build a new one from its mistakes.",
    badge: "Core",
  },
  {
    title: "Admin foundation",
    body: "A protected admin area for user, document and job monitoring, with privileges enforced by the backend. Payment and subscription management arrive in Phase 3.",
    badge: "Phase 2",
  },
  {
    title: "Mobile-first, no APK needed",
    body: "The full platform works in a mobile browser on Android and iPhone, on tablets and on desktop. Nothing to install.",
    badge: "Core",
  },
];

export default function FeaturesPage() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-14 sm:px-6 lg:px-8">
      <SectionHeading
        align="left"
        level="h1"
        eyebrow="Features"
        title="A complete preparation platform"
        description="From upload to result — every step is a real, working part of the product. Nothing here is a mockup."
      />
      <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map((f) => (
          <Card key={f.title}>
            <Badge tone={f.badge === "Core" ? "brand" : "accent"}>{f.badge}</Badge>
            <CardTitle>
              <span className="mt-3 block">{f.title}</span>
            </CardTitle>
            <CardDescription>{f.body}</CardDescription>
          </Card>
        ))}
      </div>

      <div className="mt-16 max-w-3xl">
        <SectionHeading align="left" eyebrow="Questions" title="Frequently asked" />
        <div className="mt-6">
          <Accordion
            items={[
              {
                title: "Do I need to install an app?",
                content:
                  "No. OfficerPath AI is a web application. It works in the browser on your phone, tablet or computer — no APK or installation is needed.",
              },
              {
                title: "Where do the questions come from?",
                content:
                  "From your own uploads. The engine extracts MCQs from the PDFs and images you provide and keeps the source document and page with every question, so you can always check where a question came from.",
              },
              {
                title: "What happens if the engine cannot find an answer?",
                content:
                  "The question is labelled Unknown Answer and shown as unanswered. The platform never invents an answer or marks a guess as correct.",
              },
              {
                title: "Is there a payment system yet?",
                content:
                  "No. During this phase the platform is free to use. Paid plans and subscription management are planned for Phase 3 — see the Pricing page for the honest current position.",
              },
            ]}
          />
        </div>
        <div className="mt-8">
          <Button href="/register">Start Your Preparation</Button>
        </div>
      </div>
    </div>
  );
}

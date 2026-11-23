import type { Metadata } from "next";
import { SITE_NAME, SITE_URL } from "@/lib/site";

export const metadata: Metadata = {
  title: `Terms and Conditions | ${SITE_NAME}`,
  description:
    "The terms for using OfficerPath AI — accounts, uploads, tests, marking, acceptable use, and the limits of what the platform promises.",
  alternates: {
    canonical: `${SITE_URL}/terms`,
  },
  openGraph: {
    url: `${SITE_URL}/terms`,
  },
};

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-8">
      <h2 className="text-xl font-bold text-slate-900">{title}</h2>
      <div className="mt-3 space-y-3 text-base leading-relaxed text-slate-600">{children}</div>
    </section>
  );
}

export default function TermsPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-14 sm:px-6">
      <p className="text-sm font-bold uppercase tracking-widest text-brand-600">Legal</p>
      <h1 className="mt-2 text-3xl font-extrabold tracking-tight text-slate-900 sm:text-4xl">
        Terms and Conditions
      </h1>
      <p className="mt-3 text-sm text-slate-500">Last updated: 22 November 2026</p>

      <Section title="1. The service">
        <p>
          {SITE_NAME} is an AI-assisted competitive examination preparation
          platform. It lets you upload your own educational material, extract
          multiple-choice questions from it, build custom tests, attempt
          timed examinations, and track your performance. The service is
          provided &ldquo;as is&rdquo; while it is under active development.
        </p>
      </Section>

      <Section title="2. Your account">
        <p>
          You must provide accurate information when registering, keep your
          password secure, and not share your account with others. You are
          responsible for everything done under your account. We may suspend
          accounts that abuse the service or break these terms.
        </p>
      </Section>

      <Section title="3. Your uploads">
        <p>
          You keep ownership of the documents you upload. By uploading, you
          confirm you have the right to use the material for your own study,
          and you give us permission to process it only to provide the
          service — extraction, storage and display back to you. Do not
          upload material you do not have the right to use, or material that
          is unlawful, harmful or infringing.
        </p>
        <p>
          Original extracted content is never silently changed. If you
          correct something through the review workflow, the correction is
          recorded separately and the original is preserved.
        </p>
      </Section>

      <Section title="4. Accuracy — what we do and do not promise">
        <p>
          The platform extracts questions and answers from your documents
          using automated processing. Extraction quality depends on the
          quality of the document — scanned, handwritten or low-contrast
          pages may produce incomplete or incorrect results. Answers that
          cannot be verified are marked unknown and are never presented as
          correct.
        </p>
        <p>
          <strong className="text-slate-900">
            We do not guarantee any examination result, score, selection or
            success.
          </strong>{" "}
          The platform is a practice aid. Always check important questions
          against your own books and official sources.
        </p>
      </Section>

      <Section title="5. Tests and marking">
        <p>
          Tests are marked on the server with the marking rules stored with
          each test (by default: correct +1, incorrect −0.25, unattempted 0).
          A test you have already taken keeps its original questions, answer
          key and marking rules even if the question bank changes later.
        </p>
      </Section>

      <Section title="6. Acceptable use">
        <p>You agree not to:</p>
        <ul className="list-disc space-y-1.5 pl-5">
          <li>Attempt to access other users&apos; documents, tests or results.</li>
          <li>Upload malware, or try to disrupt, overload or reverse-engineer the service.</li>
          <li>Use the service to cheat in a live examination or to impersonate anyone.</li>
          <li>Resell, redistribute or republish the platform&apos;s content as your own.</li>
        </ul>
      </Section>

      <Section title="7. Pricing and payments">
        <p>
          The platform is free to use during this phase. Paid plans and
          subscription management are planned for a later phase. No payment
          will be charged without your clear agreement to a published price
          at that time.
        </p>
      </Section>

      <Section title="8. Availability and liability">
        <p>
          We aim to keep the service available, but we do not guarantee
          uninterrupted access. To the extent permitted by law, we are not
          liable for any loss arising from the use of, or inability to use,
          the service, or from reliance on extracted content.
        </p>
      </Section>

      <Section title="9. Changes">
        <p>
          We may update these terms as the platform develops. Material
          changes will be announced on the website, and continued use of the
          service after a change means you accept the updated terms.
        </p>
      </Section>

      <Section title="10. Contact">
        <p>
          Questions about these terms:{" "}
          <a href="mailto:hello@abdulqadeerml.com" className="font-medium text-brand-700 hover:underline">
            hello@abdulqadeerml.com
          </a>
          .
        </p>
      </Section>
    </div>
  );
}

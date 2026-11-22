import type { Metadata } from "next";
import { SITE_NAME } from "@/lib/site";

export const metadata: Metadata = {
  title: `Privacy Policy | ${SITE_NAME}`,
  description:
    "How OfficerPath AI collects, uses, stores and protects your personal data, uploaded documents and test results.",
};

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-8">
      <h2 className="text-xl font-bold text-slate-900">{title}</h2>
      <div className="mt-3 space-y-3 text-base leading-relaxed text-slate-600">{children}</div>
    </section>
  );
}

export default function PrivacyPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-14 sm:px-6">
      <p className="text-sm font-bold uppercase tracking-widest text-brand-600">Legal</p>
      <h1 className="mt-2 text-3xl font-extrabold tracking-tight text-slate-900 sm:text-4xl">
        Privacy Policy
      </h1>
      <p className="mt-3 text-sm text-slate-500">Last updated: 22 November 2026</p>

      <Section title="1. Who we are">
        <p>
          {SITE_NAME} (&ldquo;we&rdquo;, &ldquo;us&rdquo;) is a competitive
          examination preparation platform. This policy explains what personal
          data we collect when you use the website, why we collect it, and
          what rights you have.
        </p>
      </Section>

      <Section title="2. Data we collect">
        <p>
          <strong className="text-slate-900">Account data:</strong> your full
          name, email address, password (stored only as a secure hash — we
          never see your password in plain text), optional phone number,
          preferred examination and education level.
        </p>
        <p>
          <strong className="text-slate-900">Uploaded documents:</strong> the
          PDFs and images you upload, and the questions, options and answers
          extracted from them, together with processing metadata (file name,
          size, page count, processing status).
        </p>
        <p>
          <strong className="text-slate-900">Learning data:</strong> the tests
          you create and attempt, your answers, scores, time taken, bookmarks
          and mistake-notebook entries.
        </p>
        <p>
          <strong className="text-slate-900">Technical data:</strong> basic
          usage information such as pages visited, device type and approximate
          location derived from your connection, used to keep the service
          running and secure.
        </p>
      </Section>

      <Section title="3. How we use your data">
        <p>
          We use your data only to provide the service: to create and secure
          your account, to process your documents, to generate and mark your
          tests, to show you your results, and to contact you about your
          account or the service. We do not sell your personal data, and we
          do not share your uploaded documents or test results with other
          students.
        </p>
      </Section>

      <Section title="4. Who can see your data">
        <p>
          Your documents, questions, tests and results are private to your
          account. Our administrators can see account and processing records
          only to operate and support the platform. We do not publish your
          data, and we do not use your uploaded material to train models
          without your explicit consent.
        </p>
      </Section>

      <Section title="5. Where data is stored">
        <p>
          Account and learning data is stored in a PostgreSQL database
          hosted by our database provider, and uploaded files are stored in
          private storage that is not publicly accessible. Access is
          protected by authentication and per-user ownership checks enforced
          on the server.
        </p>
      </Section>

      <Section title="6. How long we keep it">
        <p>
          We keep your account data while your account is active. If you
          delete your account, your personal data and uploaded documents are
          deleted; anonymised usage statistics may be kept for service
          improvement. Backups may retain deleted data for a limited period
          before they expire.
        </p>
      </Section>

      <Section title="7. Your rights">
        <p>
          You can view and update your profile, download your data on
          request, and ask us to delete your account and personal data by
          contacting us. You can also object to processing or ask for a
          correction to inaccurate data.
        </p>
      </Section>

      <Section title="8. Cookies and tracking">
        <p>
          We use only the cookies and local storage needed for the service
          to work — keeping you signed in and remembering your preferences.
          We do not run third-party advertising trackers on this website.
        </p>
      </Section>

      <Section title="9. Children">
        <p>
          The service is intended for students preparing for competitive
          examinations. If you are under 16, please use the service only
          with a parent or guardian&apos;s permission.
        </p>
      </Section>

      <Section title="10. Changes to this policy">
        <p>
          If we change this policy, we will update the date above and, for
          material changes, tell you by email or with a notice on the
          website before the change takes effect.
        </p>
      </Section>

      <Section title="11. Contact">
        <p>
          For any privacy question or request, email us at{" "}
          <a href="mailto:hello@abdulqadeerml.com" className="font-medium text-brand-700 hover:underline">
            hello@abdulqadeerml.com
          </a>
          .
        </p>
      </Section>
    </div>
  );
}

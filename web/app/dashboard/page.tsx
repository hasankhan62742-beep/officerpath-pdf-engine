"use client";

// OfficerPath AI — student dashboard (Phase 2, M4).
//
// Every number on this page comes from GET /api/v1/dashboard/summary
// (real engine-DB rows for the signed-in user). A zero is a measured
// zero; an empty account shows honest empty states, never invented
// activity. While any job is queued/processing the summary refetches
// every 5 s (15 s after 2 min) and stops on terminal states.

import { useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { SectionHeading } from "@/components/ui/section-heading";
import { Spinner } from "@/components/ui/spinner";
import { JobStatusBadge } from "@/components/dashboard/job-status-badge";
import {
  getDashboardSummary,
  getSessionToken,
  type DashboardDocument,
} from "@/lib/api";
import { DASHBOARD_ORGS } from "@/lib/site";
import { formatDateTime } from "@/lib/utils";

function activeJobCount(jobsByStatus: Record<string, number>): number {
  return (
    (jobsByStatus.queued ?? 0) +
    (jobsByStatus.uploading ?? 0) +
    (jobsByStatus.processing ?? 0)
  );
}

function StatCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: number;
  hint: string;
}) {
  return (
    <Card className="p-5">
      <p className="text-sm font-medium text-slate-600">{label}</p>
      <p className="mt-1 text-3xl font-bold text-slate-900">{value}</p>
      <p className="mt-1 text-xs text-slate-500">{hint}</p>
    </Card>
  );
}

function RecentDocumentRow({ doc }: { doc: DashboardDocument }) {
  return (
    <li className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-slate-100 py-3 last:border-b-0">
      <div className="min-w-0">
        <Link
          href={`/dashboard/documents/${doc.id}`}
          className="block truncate font-medium text-brand-700 hover:underline"
        >
          {doc.title}
        </Link>
        <p className="text-xs text-slate-500">
          {doc.file_type.toUpperCase()} · {formatDateTime(doc.created_at)}
          {doc.job?.status === "done" && doc.questions !== null
            ? ` · ${doc.answered ?? 0} of ${doc.questions} answered`
            : ""}
        </p>
      </div>
      {doc.job ? <JobStatusBadge status={doc.job.status} /> : null}
    </li>
  );
}

export default function DashboardPage() {
  const pollStartedAt = useRef<number | null>(null);

  const summaryQuery = useQuery({
    queryKey: ["dashboard-summary"],
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      return getDashboardSummary(token);
    },
    refetchInterval: (query) => {
      const summary = query.state.data;
      const active = summary ? activeJobCount(summary.jobs_by_status) > 0 : false;
      if (!active) {
        pollStartedAt.current = null;
        return false;
      }
      if (pollStartedAt.current === null) pollStartedAt.current = Date.now();
      return Date.now() - pollStartedAt.current > 120_000 ? 15_000 : 5_000;
    },
  });

  if (summaryQuery.isPending) {
    return (
      <div className="flex items-center gap-2 py-16 text-slate-600">
        <Spinner /> Loading your dashboard…
      </div>
    );
  }

  if (summaryQuery.isError || !summaryQuery.data) {
    return (
      <ErrorState
        title="Could not load your dashboard"
        description={
          (summaryQuery.error as Error | null)?.message ??
          "The engine did not answer. Check that it is running and try again."
        }
        onRetry={() => summaryQuery.refetch()}
      />
    );
  }

  const summary = summaryQuery.data;
  const active = activeJobCount(summary.jobs_by_status);

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <SectionHeading
          title="Dashboard"
          description="Your documents and their processing status — live from your account."
          level="h1"
          align="left"
        />
        <Button href="/dashboard/upload">Upload a document</Button>
      </div>

      {/* M16 — exam organisations, bold, wrapping on mobile. */}
      <p
        aria-label="Exams covered"
        className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-bold text-slate-900 sm:text-base"
      >
        {DASHBOARD_ORGS.join(" · ")}
      </p>

      {active > 0 ? (
        <Alert tone="info" title={`${active} job${active === 1 ? "" : "s"} still processing`}>
          This page refreshes automatically while jobs run. You can leave and
          come back — nothing is lost.
        </Alert>
      ) : null}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label="Documents"
          value={summary.documents_total}
          hint="Papers and photos you uploaded"
        />
        <StatCard
          label="Processing"
          value={active}
          hint="Queued or running right now"
        />
        <StatCard
          label="Done"
          value={summary.jobs_by_status.done ?? 0}
          hint="Finished processing"
        />
        <StatCard
          label="Failed"
          value={summary.jobs_by_status.failed ?? 0}
          hint="Need a retry — see Documents"
        />
      </div>

      <Card className="p-5">
        <CardTitle>Recent documents</CardTitle>
        <CardDescription>
          {summary.documents_total === 0
            ? "Nothing here yet."
            : "Your newest uploads, with their current status."}
        </CardDescription>
        {summary.recent_documents.length === 0 ? (
          <div className="mt-4">
            <EmptyState
              title="No documents yet"
              description="Upload your first paper — a PPSC past paper PDF or a photo of a question table — and its questions will be extracted here."
              actionLabel="Upload your first document"
              actionHref="/dashboard/upload"
            />
          </div>
        ) : (
          <ul className="mt-2">
            {summary.recent_documents.map((doc) => (
              <RecentDocumentRow key={doc.id} doc={doc} />
            ))}
          </ul>
        )}
        {summary.documents_total > summary.recent_documents.length ? (
          <div className="mt-4">
            <Button variant="secondary" href="/dashboard/documents">
              View all {summary.documents_total} documents
            </Button>
          </div>
        ) : null}
      </Card>

      <Card className="p-5">
        <CardTitle>Tests</CardTitle>
        <CardDescription>
          No tests yet — the test builder arrives in Milestone 6. Upload a
          paper first; your extracted questions become the question bank
          that tests are built from.
        </CardDescription>
      </Card>
    </div>
  );
}

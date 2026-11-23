// OfficerPath AI — admin overview (Phase 2, M9, GAP-10).
//
// Real counts from GET /api/v1/admin/overview — every figure is
// a COUNT(*) over an engine table. The layout guard redirects
// non-admins away; the API 404 is the real enforcement.

"use client";

import { useQuery } from "@tanstack/react-query";
import { Card, CardTitle } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/empty-state";
import { SectionHeading } from "@/components/ui/section-heading";
import { Spinner } from "@/components/ui/spinner";
import { ApiError, getAdminOverview, getSessionToken } from "@/lib/api";

function CountCard({ label, value }: { label: string; value: number }) {
  return (
    <Card>
      <p className="text-sm font-medium text-slate-600">{label}</p>
      <p className="mt-1 text-3xl font-extrabold text-slate-900">{value}</p>
    </Card>
  );
}

export default function AdminOverviewPage() {
  const query = useQuery({
    queryKey: ["admin-overview"],
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new ApiError(401, "unauthorized", "Sign in to view the admin area.");
      return getAdminOverview(token);
    },
  });

  if (query.isPending) return <Spinner />;
  if (query.isError) {
    return (
      <ErrorState
        title="Admin overview could not be loaded"
        description={query.error instanceof Error ? query.error.message : "Try again."}
        onRetry={() => void query.refetch()}
      />
    );
  }

  const data = query.data;
  return (
    <div>
      <SectionHeading
        eyebrow="Admin"
        title="Overview"
        description="Real platform counts from the engine database — students, documents, jobs, questions, tests and errors."
      />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <CountCard label="Students" value={data.users} />
        <CountCard label="Documents" value={data.documents} />
        <CountCard label="Questions in bank" value={data.questions} />
        <CountCard label="Jobs" value={data.jobs} />
        <CountCard label="Tests" value={data.tests} />
        <CountCard label="Results" value={data.results} />
        <CountCard label="Processing errors" value={data.errors} />
        <CountCard label="Notifications sent" value={data.notifications} />
      </div>
      <Card className="mt-6">
        <CardTitle>Jobs by status</CardTitle>
        {Object.keys(data.jobs_by_status).length === 0 ? (
          <p className="mt-2 text-sm text-slate-600">No jobs yet.</p>
        ) : (
          <ul className="mt-2 space-y-1 text-sm text-slate-700">
            {Object.entries(data.jobs_by_status).map(([status, count]) => (
              <li key={status} className="flex justify-between gap-4">
                <span className="capitalize">{status}</span>
                <span className="font-semibold">{count}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

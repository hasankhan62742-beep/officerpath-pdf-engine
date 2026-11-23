// OfficerPath AI — notifications (Phase 2, M9, GAP-9).
//
// Real list from GET /api/v1/notifications (newest first,
// owner-only). In-app only — no email is ever claimed sent.
// Marking a row read is PATCH /{id}/read (idempotent).

"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { Pagination } from "@/components/ui/pagination";
import { SectionHeading } from "@/components/ui/section-heading";
import { Spinner } from "@/components/ui/spinner";
import {
  ApiError,
  getSessionToken,
  listNotifications,
  markNotificationRead,
  type NotificationItem,
} from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

const PAGE_SIZE = 20;

const TYPE_LABELS: Record<string, string> = {
  upload_done: "Upload complete",
  upload_failed: "Upload failed",
  review_needed: "Review needed",
  test_submitted: "Test submitted",
  result_ready: "Result ready",
  subscription_change: "Subscription",
};

function NotificationCard({
  item,
  onMarkRead,
  marking,
}: {
  item: NotificationItem;
  onMarkRead: (id: string) => void;
  marking: string | null;
}) {
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <CardTitle>{item.title}</CardTitle>
          <p className="mt-1 text-sm text-slate-600">{item.body}</p>
          <p className="mt-1 text-xs text-slate-500">
            {TYPE_LABELS[item.type] ?? item.type}
            {item.created_at ? ` · ${formatDateTime(item.created_at)}` : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {item.is_read ? (
            <Badge>Read</Badge>
          ) : (
            <>
              <Badge>Unread</Badge>
              <Button
                variant="secondary"
                size="sm"
                disabled={marking === item.id}
                onClick={() => onMarkRead(item.id)}
              >
                {marking === item.id ? "Saving…" : "Mark read"}
              </Button>
            </>
          )}
        </div>
      </div>
    </Card>
  );
}

export default function NotificationsPage() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [marking, setMarking] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ["notifications", page, unreadOnly],
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new ApiError(401, "unauthorized", "Sign in to view notifications.");
      return listNotifications(token, {
        unread_only: unreadOnly,
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
      });
    },
  });

  const markRead = useMutation({
    mutationFn: async (id: string) => {
      const token = await getSessionToken();
      if (!token) throw new ApiError(401, "unauthorized", "Sign in to update notifications.");
      return markNotificationRead(token, id);
    },
    onMutate: (id: string) => setMarking(id),
    onSettled: () => {
      setMarking(null);
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
      void queryClient.invalidateQueries({ queryKey: ["notifications-unread-count"] });
    },
  });

  if (query.isPending) {
    return <Spinner />;
  }
  if (query.isError) {
    return (
      <ErrorState
        title="Notifications could not be loaded"
        description={query.error instanceof Error ? query.error.message : "Try again."}
        onRetry={() => void query.refetch()}
      />
    );
  }

  const data = query.data;
  const totalPages = Math.max(1, Math.ceil(data.total / PAGE_SIZE));

  return (
    <div>
      <SectionHeading
        eyebrow="Dashboard"
        title="Notifications"
        description={
          data.unread_count > 0
            ? `You have ${data.unread_count} unread notification${data.unread_count === 1 ? "" : "s"}.`
            : "All caught up — no unread notifications."
        }
      />
      <div className="mb-6 flex gap-2">
        <Button variant={unreadOnly ? "secondary" : "primary"} size="sm" onClick={() => { setUnreadOnly(false); setPage(1); }}>
          All ({data.total})
        </Button>
        <Button variant={unreadOnly ? "primary" : "secondary"} size="sm" onClick={() => { setUnreadOnly(true); setPage(1); }}>
          Unread ({data.unread_count})
        </Button>
      </div>
      {data.items.length === 0 ? (
        <EmptyState
          title={unreadOnly ? "No unread notifications" : "No notifications yet"}
          description={
            unreadOnly
              ? "You have read everything. New upload and result notifications will appear here."
              : "Notifications about your uploads and test results will appear here."
          }
        />
      ) : (
        <div className="space-y-3">
          {data.items.map((item) => (
            <NotificationCard
              key={item.id}
              item={item}
              marking={marking}
              onMarkRead={(id) => markRead.mutate(id)}
            />
          ))}
        </div>
      )}
      {markRead.isError && (
        <Alert tone="danger" className="mt-4">
          {markRead.error instanceof Error ? markRead.error.message : "Could not mark as read."}
        </Alert>
      )}
      <div className="mt-6">
        <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
      </div>
    </div>
  );
}

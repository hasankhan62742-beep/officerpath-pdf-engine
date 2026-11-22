import { Badge } from "@/components/ui/badge";
import type { JobStatus } from "@/lib/api";

const LABELS: Record<JobStatus, string> = {
  queued: "Queued",
  uploading: "Uploading",
  processing: "Processing",
  done: "Done",
  failed: "Failed",
  cancelled: "Cancelled",
};

const TONES: Record<
  JobStatus,
  "brand" | "success" | "info" | "accent" | "danger" | "neutral"
> = {
  queued: "info",
  uploading: "info",
  processing: "accent",
  done: "success",
  failed: "danger",
  cancelled: "neutral",
};

/** Job status as a coloured badge. The status shown is always the
 * one the engine returned — never computed or guessed locally. */
export function JobStatusBadge({ status }: { status: JobStatus }) {
  return <Badge tone={TONES[status]}>{LABELS[status]}</Badge>;
}

/** A job that still needs polling (queued / uploading / processing). */
export function isJobActive(status: JobStatus | null | undefined): boolean {
  return status === "queued" || status === "uploading" || status === "processing";
}

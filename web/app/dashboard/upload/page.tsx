"use client";

// OfficerPath AI — document upload (Phase 2, M4).
//
// PDF, JPG and PNG only; 100 MB per file, at most 20 files at
// once (the engine's limits — the server re-validates everything
// and is the truth; this page only pre-checks for a faster answer).
// One file uses the single-upload endpoint; several use the batch
// endpoint (one rate-limit charge for the whole batch). Every
// result shown is the engine's own response — a file is never
// called "uploaded" before the engine says so, and processing
// continues in the background with live status below.

import { useRef, useState } from "react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { SectionHeading } from "@/components/ui/section-heading";
import { Spinner } from "@/components/ui/spinner";
import { JobTracker } from "@/components/dashboard/job-tracker";
import {
  ApiError,
  getSessionToken,
  uploadBatch,
  uploadFile,
  type UploadResult,
} from "@/lib/api";
import { cn, formatBytes } from "@/lib/utils";

const MAX_FILES = 20;
const MAX_FILE_BYTES = 100 * 1024 * 1024; // 100 MB — the engine's limit
const ACCEPTED_EXTENSIONS = [".pdf", ".jpg", ".jpeg", ".png"];

interface RejectedFile {
  name: string;
  reason: string;
}

function validateFiles(files: File[]): { accepted: File[]; rejected: RejectedFile[] } {
  const accepted: File[] = [];
  const rejected: RejectedFile[] = [];
  for (const file of files) {
    const lower = file.name.toLowerCase();
    const ext = lower.slice(lower.lastIndexOf("."));
    if (!ACCEPTED_EXTENSIONS.includes(ext)) {
      rejected.push({
        name: file.name,
        reason: "Only PDF, JPG and PNG files are accepted.",
      });
    } else if (file.size > MAX_FILE_BYTES) {
      rejected.push({
        name: file.name,
        reason: `Larger than the 100 MB limit (${formatBytes(file.size)}).`,
      });
    } else if (file.size === 0) {
      rejected.push({ name: file.name, reason: "The file is empty." });
    } else {
      accepted.push(file);
    }
  }
  return { accepted, rejected };
}

function ResultRow({ result }: { result: UploadResult }) {
  const stored = result.status === "stored";
  const replay = result.status === "replay";
  return (
    <li className="space-y-2 border-b border-slate-100 py-4 last:border-b-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-medium text-slate-900">{result.filename}</p>
        {stored ? (
          <span className="rounded-full bg-success-100 px-2.5 py-0.5 text-xs font-semibold text-success-800">
            Uploaded
          </span>
        ) : replay ? (
          <span className="rounded-full bg-info-100 px-2.5 py-0.5 text-xs font-semibold text-info-800">
            Already uploaded
          </span>
        ) : (
          <span className="rounded-full bg-danger-100 px-2.5 py-0.5 text-xs font-semibold text-danger-700">
            Rejected
          </span>
        )}
      </div>
      {replay ? (
        <p className="text-sm text-slate-600">
          This exact file was already uploaded — the original upload is
          shown instead of a duplicate.
        </p>
      ) : null}
      {result.status === "rejected" ? (
        <Alert tone="danger" title="The engine rejected this file">
          {result.issues.map((i) => i.message).join(" ") ||
            "Invalid file."}
        </Alert>
      ) : null}
      {result.job ? (
        <JobTracker jobId={result.job.id} documentId={result.document?.id} />
      ) : null}
    </li>
  );
}

export default function UploadPage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [rejected, setRejected] = useState<RejectedFile[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [results, setResults] = useState<UploadResult[]>([]);
  const [error, setError] = useState<string | null>(null);

  function addFiles(list: FileList | File[]) {
    const incoming = Array.from(list);
    const { accepted, rejected: bad } = validateFiles(incoming);
    const room = MAX_FILES - files.length;
    const take = accepted.slice(0, Math.max(room, 0));
    const overflow = accepted.slice(Math.max(room, 0));
    setFiles((prev) => [...prev, ...take]);
    setRejected((prev) => [
      ...prev,
      ...bad,
      ...overflow.map((f) => ({
        name: f.name,
        reason: `Only ${MAX_FILES} files at a time — remove some files first.`,
      })),
    ]);
    setResults([]);
    setError(null);
  }

  async function startUpload() {
    if (files.length === 0 || uploading) return;
    setUploading(true);
    setProgress(0);
    setError(null);
    setResults([]);
    try {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      if (files.length === 1) {
        const result = await uploadFile(token, files[0], setProgress);
        setResults([result]);
      } else {
        const batch = await uploadBatch(token, files, setProgress);
        setResults(batch.results);
      }
      setFiles([]);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.code === "rate_limited"
            ? "Too many uploads in the last minute — wait a little and try again."
            : err.message
          : err instanceof Error
            ? err.message
            : "Upload failed. Please try again.",
      );
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="space-y-8">
      <SectionHeading
        title="Upload a document"
        description="A past paper PDF or a photo of a question table. The engine extracts the questions — scans take a while, so processing runs in the background."
        level="h1"
        align="left"
      />

      {error ? (
        <Alert tone="danger" title="Upload did not finish">
          {error}
        </Alert>
      ) : null}

      <Card className="p-5">
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            addFiles(e.dataTransfer.files);
          }}
          className={cn(
            "flex flex-col items-center rounded-2xl border-2 border-dashed px-6 py-12 text-center transition-colors",
            dragOver
              ? "border-brand-500 bg-brand-50"
              : "border-slate-300 bg-slate-50 hover:border-slate-400",
          )}
        >
          <p className="text-base font-semibold text-slate-900">
            Drop files here, or choose them from your device
          </p>
          <p className="mt-1 text-sm text-slate-600">
            PDF, JPG or PNG · up to 100 MB per file · up to {MAX_FILES} files
            at once
          </p>
          <Button
            variant="secondary"
            className="mt-5"
            onClick={() => inputRef.current?.click()}
          >
            Choose files
          </Button>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept=".pdf,.jpg,.jpeg,.png"
            className="hidden"
            aria-label="Choose files to upload"
            onChange={(e) => {
              if (e.target.files) addFiles(e.target.files);
              e.target.value = "";
            }}
          />
        </div>

        {files.length > 0 ? (
          <ul className="mt-4 space-y-2">
            {files.map((file) => (
              <li
                key={`${file.name}-${file.size}`}
                className="flex items-center justify-between gap-4 rounded-lg border border-slate-200 px-3 py-2 text-sm"
              >
                <span className="min-w-0 truncate font-medium text-slate-900">
                  {file.name}
                </span>
                <span className="shrink-0 text-slate-500">{formatBytes(file.size)}</span>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={uploading}
                  onClick={() => setFiles((prev) => prev.filter((f) => f !== file))}
                  aria-label={`Remove ${file.name}`}
                >
                  Remove
                </Button>
              </li>
            ))}
          </ul>
        ) : null}

        {rejected.length > 0 ? (
          <div className="mt-4">
            <Alert tone="warning" title="Some files were not added">
              <ul className="list-disc pl-5">
                {rejected.map((r) => (
                  <li key={r.name}>
                    {r.name} — {r.reason}
                  </li>
                ))}
              </ul>
            </Alert>
          </div>
        ) : null}

        <div className="mt-5 flex flex-wrap items-center gap-3">
          <Button
            disabled={files.length === 0 || uploading}
            loading={uploading}
            onClick={startUpload}
          >
            {uploading
              ? "Uploading…"
              : `Upload ${files.length} file${files.length === 1 ? "" : "s"}`}
          </Button>
          {files.length > 0 && !uploading ? (
            <Button variant="ghost" onClick={() => setFiles([])}>
              Clear
            </Button>
          ) : null}
        </div>

        {uploading ? (
          <div className="mt-4">
            <Progress value={progress} label="Uploading" />
          </div>
        ) : null}
      </Card>

      {results.length > 0 ? (
        <Card className="p-5">
          <h2 className="text-lg font-semibold text-slate-900">Upload results</h2>
          <p className="mt-1 flex items-center gap-2 text-sm text-slate-600">
            <Spinner /> Processing runs in the background — the status below
            updates live. You can leave this page; nothing is lost.
          </p>
          <ul className="mt-2">
            {results.map((result) => (
              <ResultRow key={`${result.filename}-${result.job?.id ?? "rejected"}`} result={result} />
            ))}
          </ul>
        </Card>
      ) : null}
    </div>
  );
}

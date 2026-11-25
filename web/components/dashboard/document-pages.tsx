// OfficerPath AI — document page inventory (Phase A, A3).
//
// Per-page extraction status from GET /api/v1/documents/{id}/pages:
// which pages produced questions, which produced none, which
// failed or came back low-confidence, and the expected-vs-extracted
// completeness check. A failed page can be retried on its own —
// the retry re-runs the document and replaces only that page's
// questions; every other page is untouched. The extracted
// questions themselves live in "Extraction results" below.

"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import {
  ApiError,
  getDocumentPages,
  getSessionToken,
  retryDocumentPage,
  setExpectedQuestionCount,
  type DocumentPageItem,
  type PageExtractionStatus,
} from "@/lib/api";

const STATUS_LABEL: Record<PageExtractionStatus, string> = {
  processed: "Done",
  no_questions: "No questions",
  failed: "Failed",
  low_confidence: "Low confidence",
};

const STATUS_STYLE: Record<PageExtractionStatus, string> = {
  processed: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  no_questions: "bg-slate-100 text-slate-600 ring-slate-200",
  failed: "bg-red-50 text-red-700 ring-red-200",
  low_confidence: "bg-amber-50 text-amber-700 ring-amber-200",
};

function statusBadge(status: PageExtractionStatus | null) {
  if (!status) {
    return (
      <span className="inline-flex rounded-full px-2 py-0.5 text-xs font-medium text-slate-500">
        Not recorded yet
      </span>
    );
  }
  return (
    <span
      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${STATUS_STYLE[status]}`}
    >
      {STATUS_LABEL[status]}
    </span>
  );
}

function retryable(page: DocumentPageItem) {
  return (
    page.extraction_status === "failed" ||
    page.extraction_status === "low_confidence" ||
    page.extraction_status === "no_questions"
  );
}

export function DocumentPages({
  documentId,
  jobActive,
}: {
  documentId: string;
  jobActive: boolean;
}) {
  const queryClient = useQueryClient();
  const [expectedInput, setExpectedInput] = useState("");
  const [expectedError, setExpectedError] = useState<string | null>(null);
  const [savingExpected, setSavingExpected] = useState(false);
  const [retryingPage, setRetryingPage] = useState<number | null>(null);
  const [retryMessage, setRetryMessage] = useState<string | null>(null);
  const [pageError, setPageError] = useState<string | null>(null);

  const pagesQuery = useQuery({
    queryKey: ["document-pages", documentId],
    queryFn: async () => {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      return getDocumentPages(token, documentId);
    },
    // While a job (including a page retry) is running, refresh so
    // the inventory catches up when it finishes.
    refetchInterval: jobActive ? 10_000 : false,
  });

  async function saveExpected() {
    setExpectedError(null);
    const parsed = Number(expectedInput);
    if (!Number.isInteger(parsed) || parsed < 1 || parsed > 100_000) {
      setExpectedError("Enter a whole number between 1 and 100,000.");
      return;
    }
    setSavingExpected(true);
    try {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      await setExpectedQuestionCount(token, documentId, parsed);
      setExpectedInput("");
      await queryClient.invalidateQueries({ queryKey: ["document-pages", documentId] });
    } catch (err) {
      setExpectedError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Could not save the expected count. Please try again.",
      );
    } finally {
      setSavingExpected(false);
    }
  }

  async function clearExpected() {
    setExpectedError(null);
    setSavingExpected(true);
    try {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      await setExpectedQuestionCount(token, documentId, null);
      await queryClient.invalidateQueries({ queryKey: ["document-pages", documentId] });
    } catch (err) {
      setExpectedError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Could not clear the expected count. Please try again.",
      );
    } finally {
      setSavingExpected(false);
    }
  }

  async function retryPage(pageNumber: number) {
    setPageError(null);
    setRetryMessage(null);
    setRetryingPage(pageNumber);
    try {
      const token = await getSessionToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");
      const res = await retryDocumentPage(token, documentId, pageNumber);
      setRetryMessage(
        res.existing_job
          ? `Page ${pageNumber} already has a retry running — it will finish in the background.`
          : `Page ${pageNumber} retry queued. Only this page's questions will be replaced; the other pages stay as they are.`,
      );
      await queryClient.invalidateQueries({ queryKey: ["document-pages", documentId] });
      await queryClient.invalidateQueries({ queryKey: ["document", documentId] });
    } catch (err) {
      setPageError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Could not retry this page. Please try again.",
      );
    } finally {
      setRetryingPage(null);
    }
  }

  return (
    <Card className="p-5">
      <CardTitle>Pages</CardTitle>
      <CardDescription>
        One row per page: what the engine found on it, and which pages
        still need work. Extracted questions for each page are in
        Extraction results below.
      </CardDescription>

      {pagesQuery.isPending ? (
        <div className="mt-4 flex items-center gap-2 text-sm text-slate-600">
          <Spinner /> Loading the page inventory…
        </div>
      ) : pagesQuery.isError || !pagesQuery.data ? (
        <Alert tone="danger" title="Could not load the page inventory" className="mt-4">
          {(pagesQuery.error as Error | null)?.message ??
            "The engine did not answer. Try reloading the page."}
        </Alert>
      ) : (
        <div className="mt-4 space-y-4">
          <div className="rounded-xl bg-slate-50 px-3 py-3 text-sm text-slate-700">
            {pagesQuery.data.expected_question_count !== null ? (
              <p>
                <span className="font-semibold text-slate-900">
                  {pagesQuery.data.extracted_question_count} of{" "}
                  {pagesQuery.data.expected_question_count} expected questions
                  extracted.
                </span>{" "}
                {pagesQuery.data.missing_question_count !== null &&
                pagesQuery.data.missing_question_count > 0 ? (
                  <>
                    {pagesQuery.data.missing_question_count} still missing.
                    {pagesQuery.data.missing_numbers.length > 0 ? (
                      <>
                        {" "}
                        Missing numbers: {pagesQuery.data.missing_numbers.join(", ")}
                        {pagesQuery.data.missing_numbers_truncated ? "…" : ""}.
                      </>
                    ) : null}
                  </>
                ) : (
                  "Nothing missing."
                )}{" "}
                <button
                  type="button"
                  onClick={clearExpected}
                  disabled={savingExpected}
                  className="font-medium text-brand-700 hover:underline disabled:text-slate-400"
                >
                  Clear expected count
                </button>
              </p>
            ) : (
              <p>
                Extracted {pagesQuery.data.extracted_question_count} questions
                from {pagesQuery.data.page_count} pages. If you know how many
                questions this paper should have, enter it to see what is
                missing.
              </p>
            )}
            {pagesQuery.data.pending_question_count > 0 ? (
              <p className="mt-1">
                {pagesQuery.data.pending_question_count} question(s) need
                review — the engine found them but could not answer them
                from the paper.
              </p>
            ) : null}
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <label htmlFor="expected-count" className="text-sm font-medium text-slate-700">
                Expected questions
              </label>
              <input
                id="expected-count"
                type="number"
                min={1}
                max={100_000}
                inputMode="numeric"
                value={expectedInput}
                onChange={(event) => setExpectedInput(event.target.value)}
                placeholder="e.g. 100"
                className="w-28 rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm text-slate-900"
              />
              <Button
                variant="secondary"
                size="sm"
                disabled={savingExpected || expectedInput.trim() === ""}
                loading={savingExpected}
                onClick={saveExpected}
              >
                Save
              </Button>
            </div>
            {expectedError ? (
              <p className="mt-2 text-sm text-red-700">{expectedError}</p>
            ) : null}
          </div>

          {pagesQuery.data.failed_pages.length > 0 ||
          pagesQuery.data.low_confidence_pages.length > 0 ? (
            <p className="text-sm text-slate-600">
              Needs attention — failed pages:{" "}
              {pagesQuery.data.failed_pages.length > 0
                ? pagesQuery.data.failed_pages.join(", ")
                : "none"}
              ; low-confidence pages:{" "}
              {pagesQuery.data.low_confidence_pages.length > 0
                ? pagesQuery.data.low_confidence_pages.join(", ")
                : "none"}
              .
            </p>
          ) : null}

          {retryMessage ? (
            <Alert tone="info" title="Page retry queued">
              {retryMessage}
            </Alert>
          ) : null}
          {pageError ? (
            <Alert tone="danger" title="That page retry did not work">
              {pageError}
            </Alert>
          ) : null}

          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-left text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-xs font-medium text-slate-500">
                  <th scope="col" className="py-2 pr-3">
                    Page
                  </th>
                  <th scope="col" className="py-2 pr-3">
                    Type
                  </th>
                  <th scope="col" className="py-2 pr-3">
                    Status
                  </th>
                  <th scope="col" className="py-2 pr-3">
                    Questions
                  </th>
                  <th scope="col" className="py-2 pr-3">
                    Reason
                  </th>
                  <th scope="col" className="py-2">
                    Action
                  </th>
                </tr>
              </thead>
              <tbody>
                {pagesQuery.data.pages.map((page) => (
                  <tr
                    key={page.page_number}
                    className="border-b border-slate-100 last:border-0"
                  >
                    <td className="py-2 pr-3 font-medium text-slate-900">
                      {page.page_number}
                    </td>
                    <td className="py-2 pr-3 text-slate-600">
                      {page.classification ?? "—"}
                    </td>
                    <td className="py-2 pr-3">{statusBadge(page.extraction_status)}</td>
                    <td className="py-2 pr-3 text-slate-900">
                      {page.question_count > 0 ? (
                        <a href="#extraction-results" className="text-brand-700 hover:underline">
                          {page.question_count}
                        </a>
                      ) : (
                        "0"
                      )}
                    </td>
                    <td className="max-w-40 truncate py-2 pr-3 text-slate-600">
                      {page.error_message ?? "—"}
                    </td>
                    <td className="py-2">
                      {retryable(page) ? (
                        <Button
                          variant="secondary"
                          size="sm"
                          disabled={retryingPage !== null}
                          loading={retryingPage === page.page_number}
                          onClick={() => retryPage(page.page_number)}
                        >
                          Retry page
                        </Button>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Card>
  );
}

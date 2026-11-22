"use client";

import { Button } from "@/components/ui/button";

/** Simple numbered pagination. Server-side paging is decided when the backend contract lands (M4/M5); this control is ready for it. */
export function Pagination({
  page,
  totalPages,
  onPageChange,
}: {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}) {
  if (totalPages <= 1) return null;
  const pages = Array.from({ length: totalPages }, (_, i) => i + 1);
  return (
    <nav aria-label="Pagination" className="flex flex-wrap items-center justify-center gap-1.5">
      <Button
        variant="secondary"
        size="sm"
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
        aria-label="Previous page"
      >
        ← Prev
      </Button>
      {pages.map((p) => (
        <Button
          key={p}
          variant={p === page ? "primary" : "ghost"}
          size="sm"
          aria-current={p === page ? "page" : undefined}
          onClick={() => onPageChange(p)}
          className="min-w-11"
        >
          {p}
        </Button>
      ))}
      <Button
        variant="secondary"
        size="sm"
        disabled={page >= totalPages}
        onClick={() => onPageChange(page + 1)}
        aria-label="Next page"
      >
        Next →
      </Button>
    </nav>
  );
}

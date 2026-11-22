import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Card({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-slate-200 bg-white p-5 shadow-[var(--shadow-card)] sm:p-6",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function CardTitle({
  children,
  as: Tag = "h3",
}: {
  children: ReactNode;
  /** Use as="h1" when the card title is the page's main heading. */
  as?: "h1" | "h2" | "h3";
}) {
  return <Tag className="text-lg font-semibold text-slate-900">{children}</Tag>;
}

export function CardDescription({ children }: { children: ReactNode }) {
  return <p className="mt-1 text-sm leading-relaxed text-slate-600">{children}</p>;
}

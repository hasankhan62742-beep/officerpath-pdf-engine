import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * Minimal styled table primitives. Wrap in a horizontally scrollable
 * container on small screens (overflow-x-auto) so wide tables never
 * break the mobile layout.
 */
export function Table({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className="overflow-x-auto rounded-2xl border border-slate-200">
      <table className={cn("w-full min-w-[560px] border-collapse bg-white text-sm", className)}>
        {children}
      </table>
    </div>
  );
}

export function TableHead({ children }: { children: ReactNode }) {
  return <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">{children}</thead>;
}

export function TableBody({ children }: { children: ReactNode }) {
  return <tbody className="divide-y divide-slate-200">{children}</tbody>;
}

export function TableRow({ children }: { children: ReactNode }) {
  return <tr className="hover:bg-slate-50">{children}</tr>;
}

export function TableCell({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <td className={cn("px-4 py-3 align-top text-slate-700", className)}>{children}</td>;
}

export function TableHeaderCell({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <th scope="col" className={cn("px-4 py-3 font-semibold", className)}>{children}</th>;
}

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

type BadgeTone = "brand" | "success" | "info" | "accent" | "danger" | "neutral";

const tones: Record<BadgeTone, string> = {
  brand: "bg-brand-100 text-brand-800 ring-brand-200",
  success: "bg-success-100 text-success-800 ring-success-200",
  info: "bg-info-100 text-info-800 ring-info-200",
  accent: "bg-accent-100 text-accent-800 ring-accent-200",
  danger: "bg-danger-100 text-danger-700 ring-danger-100",
  neutral: "bg-slate-100 text-slate-700 ring-slate-200",
};

export function Badge({
  tone = "neutral",
  children,
  className,
}: {
  tone?: BadgeTone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

type AlertTone = "info" | "success" | "warning" | "danger";

const tones: Record<AlertTone, string> = {
  info: "border-info-200 bg-info-50 text-info-800",
  success: "border-success-200 bg-success-50 text-success-800",
  warning: "border-brand-200 bg-brand-50 text-brand-800",
  danger: "border-danger-100 bg-danger-50 text-danger-700",
};

/** Inline notice box. Use role="alert" for errors, role="status" otherwise. */
export function Alert({
  tone = "info",
  title,
  children,
  className,
}: {
  tone?: AlertTone;
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={cn("rounded-xl border px-4 py-3 text-sm leading-relaxed", tones[tone], className)}
    >
      {title ? <p className="font-semibold">{title}</p> : null}
      <div className={title ? "mt-0.5" : undefined}>{children}</div>
    </div>
  );
}

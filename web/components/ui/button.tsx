import type { ButtonHTMLAttributes, ReactNode } from "react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { Spinner } from "@/components/ui/spinner";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "success";
type ButtonSize = "sm" | "md" | "lg";

const variants: Record<ButtonVariant, string> = {
  primary:
    "bg-brand-600 text-white shadow-sm hover:bg-brand-700 focus-visible:outline-brand-600 disabled:bg-brand-300",
  secondary:
    "border border-slate-300 bg-white text-slate-900 shadow-sm hover:border-slate-400 hover:bg-slate-50 focus-visible:outline-slate-500 disabled:text-slate-400",
  ghost:
    "text-slate-700 hover:bg-slate-100 focus-visible:outline-slate-500 disabled:text-slate-400",
  danger:
    "bg-danger-600 text-white shadow-sm hover:bg-danger-700 focus-visible:outline-danger-600 disabled:bg-danger-500/60",
  success:
    "bg-success-600 text-white shadow-sm hover:bg-success-700 focus-visible:outline-success-600 disabled:bg-success-500/60",
};

const sizes: Record<ButtonSize, string> = {
  sm: "min-h-9 px-3 text-sm",
  md: "min-h-11 px-4 text-sm",
  lg: "min-h-12 px-6 text-base",
};

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  href?: string;
  children: ReactNode;
};

/**
 * Primary action control. Renders an <a> when href is given, otherwise
 * a <button>. Touch targets are >= 44px at md/lg (min-h-11/12).
 */
export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  href,
  className,
  disabled,
  children,
  ...rest
}: ButtonProps) {
  const classes = cn(
    "inline-flex items-center justify-center gap-2 rounded-lg font-semibold transition-colors",
    "focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed",
    variants[variant],
    sizes[size],
    className,
  );
  const content = (
    <>
      {loading ? <Spinner className="size-4" aria-label="Loading" /> : null}
      {children}
    </>
  );
  if (href) {
    return (
      <Link href={href} className={classes} aria-disabled={disabled || loading}>
        {content}
      </Link>
    );
  }
  return (
    <button type="button" className={classes} disabled={disabled || loading} {...rest}>
      {content}
    </button>
  );
}

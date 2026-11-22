import type { InputHTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";

export type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  hint?: string;
  error?: string;
  children?: ReactNode;
};

/** Labelled text input with hint + error states. Label is always rendered (a11y). */
export function Input({ label, hint, error, id, className, ...rest }: InputProps) {
  const inputId = id ?? rest.name;
  const hintId = hint ? `${inputId}-hint` : undefined;
  const errorId = error ? `${inputId}-error` : undefined;
  return (
    <div className="w-full">
      <label htmlFor={inputId} className="mb-1.5 block text-sm font-medium text-slate-900">
        {label}
      </label>
      <input
        id={inputId}
        aria-invalid={Boolean(error)}
        aria-describedby={[hintId, errorId].filter(Boolean).join(" ") || undefined}
        className={cn(
          "min-h-11 w-full rounded-lg border bg-white px-3.5 text-base text-slate-900 shadow-sm transition-colors",
          "placeholder:text-slate-400 focus:outline-2 focus:outline-offset-1",
          error
            ? "border-danger-500 focus:outline-danger-600"
            : "border-slate-300 focus:border-brand-600 focus:outline-brand-600",
          className,
        )}
        {...rest}
      />
      {hint && !error ? (
        <p id={hintId} className="mt-1.5 text-sm text-slate-500">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} role="alert" className="mt-1.5 text-sm font-medium text-danger-600">
          {error}
        </p>
      ) : null}
    </div>
  );
}

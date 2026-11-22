"use client";

import { useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export type AccordionItem = { title: string; content: ReactNode };

/** Single-open accordion. Buttons expose aria-expanded. */
export function Accordion({ items }: { items: AccordionItem[] }) {
  const [open, setOpen] = useState<number | null>(0);
  return (
    <div className="divide-y divide-slate-200 rounded-2xl border border-slate-200 bg-white">
      {items.map((item, i) => {
        const isOpen = open === i;
        return (
          <div key={item.title}>
            <button
              type="button"
              aria-expanded={isOpen}
              aria-controls={`accordion-panel-${i}`}
              onClick={() => setOpen(isOpen ? null : i)}
              className="flex min-h-14 w-full items-center justify-between gap-4 px-5 py-4 text-left text-base font-semibold text-slate-900 hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-brand-600"
            >
              {item.title}
              <span aria-hidden className={cn("shrink-0 text-slate-400 transition-transform", isOpen && "rotate-45")}>
                +
              </span>
            </button>
            {isOpen ? (
              <div id={`accordion-panel-${i}`} className="px-5 pb-5 text-sm leading-relaxed text-slate-600">
                {item.content}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

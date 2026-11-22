"use client";

import { useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export type TabItem = { id: string; label: string; content: ReactNode };

/** Controlled-by-default tabs (keyboard-focusable buttons, aria-selected). */
export function Tabs({ tabs, defaultId }: { tabs: TabItem[]; defaultId?: string }) {
  const [active, setActive] = useState(defaultId ?? tabs[0]?.id);
  const current = tabs.find((t) => t.id === active) ?? tabs[0];
  return (
    <div>
      <div role="tablist" aria-label="Sections" className="flex flex-wrap gap-1 border-b border-slate-200">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={t.id === active}
            onClick={() => setActive(t.id)}
            className={cn(
              "min-h-11 rounded-t-lg px-4 text-sm font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-brand-600",
              t.id === active
                ? "border-b-2 border-brand-600 text-brand-700"
                : "text-slate-600 hover:bg-slate-50 hover:text-slate-900",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" className="pt-5">
        {current?.content}
      </div>
    </div>
  );
}

"use client";

import { useEffect, useMemo, useState } from "react";
import { listStudyCollections } from "@/lib/api";

// Rotating typewriter tagline for the homepage hero (M17 v2).
// The three lines are honest, live facts — no invented numbers.
// The bank count comes from the public study-collections
// endpoint (``bank_total``: every question in every shared
// document) and is NEVER hardcoded: the old seed-bank total
// went stale the day the new collections were imported.
// While the count is loading — or if the engine is asleep —
// the count line simply does not rotate; the other two lines do.
// The engine may take ~50 s to wake on the free tier, so the
// hero never blocks on it.
const OTHER_LINES = [
  "Timed exam-style tests",
  "Read, practise, revise — all in one place",
];

const TYPE_MS = 55;
const DELETE_MS = 25;
const HOLD_MS = 1800;

export function RotatingTagline() {
  const [bankTotal, setBankTotal] = useState<number | null>(null);
  const lines = useMemo(
    () =>
      bankTotal !== null
        ? [`${bankTotal.toLocaleString("en-US")}+ real MCQs in the bank`, ...OTHER_LINES]
        : OTHER_LINES,
    [bankTotal],
  );
  // SSR / no-JS renders the full first line; the typewriter loop
  // only starts after mount, so there is no hydration mismatch.
  const [text, setText] = useState(lines[0]);
  // When the live count arrives the lines change: restart the
  // loop from the count line. State is adjusted during render
  // (the React pattern for resetting on a value change) — never
  // with a synchronous setState inside the effect below.
  const [prevLines, setPrevLines] = useState(lines);
  if (prevLines !== lines) {
    setPrevLines(lines);
    setText(lines[0]);
  }
  // Lazy initializer (no setState-in-effect): under reduced motion
  // the text stays on the first line and the cursor is static —
  // its blink animation is killed by CSS in globals.css.
  const [reduced] = useState(
    () =>
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );

  useEffect(() => {
    let cancelled = false;
    listStudyCollections()
      .then((res) => {
        if (!cancelled && typeof res.bank_total === "number") {
          setBankTotal(res.bank_total);
        }
      })
      .catch(() => {
        // The hero stays honest without the count — no number
        // is shown rather than a stale or invented one.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (reduced) return;
    // The loop restarts whenever the lines change (once, when
    // the live count arrives) — the displayed text itself is
    // reset during render above, not here.
    let line = 0;
    let char = lines[0].length;
    let deleting = true;
    let timer = 0;
    let cancelled = false;
    const schedule = (fn: () => void, ms: number) => {
      timer = window.setTimeout(() => {
        if (!cancelled) fn();
      }, ms);
    };
    const tick = () => {
      const current = lines[line];
      if (deleting) {
        char -= 1;
        setText(current.slice(0, char));
        if (char === 0) {
          deleting = false;
          line = (line + 1) % lines.length;
          schedule(tick, 350);
        } else {
          schedule(tick, DELETE_MS);
        }
      } else {
        char += 1;
        setText(current.slice(0, char));
        if (char === current.length) {
          deleting = true;
          schedule(tick, HOLD_MS);
        } else {
          schedule(tick, TYPE_MS);
        }
      }
    };
    schedule(tick, HOLD_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [reduced, lines]);

  return (
    <p
      className="mt-6 flex min-h-[3.5rem] items-center text-base font-semibold text-brand-700 sm:min-h-[1.75rem] sm:text-lg"
      aria-live="off"
    >
      <span>{text}</span>
      {/* Cursor always renders; its blink is disabled by CSS under
          prefers-reduced-motion, so it is a static bar there. */}
      <span
        aria-hidden
        className="hero-cursor ml-0.5 inline-block h-5 w-[2px] bg-brand-600 sm:h-6"
      />
      <span className="sr-only">{lines.join(". ")}</span>
    </p>
  );
}

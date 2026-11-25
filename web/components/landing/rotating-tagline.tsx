"use client";

import { useEffect, useState } from "react";

// Rotating typewriter tagline for the homepage hero (M17 v2).
// The three lines are honest, live facts — no invented numbers:
// the bank count is the live ExamVeda import total (52,573).
const LINES = [
  "52,573+ real MCQs in the bank",
  "Timed exam-style tests",
  "Read, practise, revise — all in one place",
];

const TYPE_MS = 55;
const DELETE_MS = 25;
const HOLD_MS = 1800;

export function RotatingTagline() {
  // SSR / no-JS renders the full first line; the typewriter loop
  // only starts after mount, so there is no hydration mismatch.
  const [text, setText] = useState(LINES[0]);
  // Lazy initializer (no setState-in-effect): under reduced motion
  // the text stays on the first line and the cursor is static —
  // its blink animation is killed by CSS in globals.css.
  const [reduced] = useState(
    () =>
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );

  useEffect(() => {
    if (reduced) return;
    let line = 0;
    let char = LINES[0].length;
    let deleting = true;
    let timer = 0;
    let cancelled = false;
    const schedule = (fn: () => void, ms: number) => {
      timer = window.setTimeout(() => {
        if (!cancelled) fn();
      }, ms);
    };
    const tick = () => {
      const current = LINES[line];
      if (deleting) {
        char -= 1;
        setText(current.slice(0, char));
        if (char === 0) {
          deleting = false;
          line = (line + 1) % LINES.length;
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
  }, [reduced]);

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
      <span className="sr-only">{LINES.join(". ")}</span>
    </p>
  );
}

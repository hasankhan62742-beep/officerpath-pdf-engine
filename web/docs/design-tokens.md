# OfficerPath AI — Design Tokens (Phase 2, M2)

Tokens live in `app/globals.css` inside Tailwind CSS v4's `@theme`
block (CSS-first configuration — there is no `tailwind.config` file;
that is the M1 doc 04 deviation, recorded here and in the M2 report).

## Brand palette

Brand colours (prompt §4): **orange, green, blue, purple** — balanced,
never all four in one place.

| Role | Tokens | Use |
|---|---|---|
| Primary | `brand-500/600/700` (`#f97316` / `#ea580c` / `#c2410c`) | Main CTAs, active states, exam accent |
| Success | `success-500/600/700` (`#22c55e` / `#16a34a` / `#15803d`) | Correct answers, passed states, positive deltas |
| Info | `info-500/600/700` (`#3b82f6` / `#2563eb` / `#1d4ed8`) | Links, info states, secondary accents |
| Accent | `accent-500/600/700` (`#a855f7` / `#9333ea` / `#7e22ce`) | Premium highlights, sparing use |
| Danger | `danger-500/600/700` (functional red) | Incorrect answers, destructive actions |
| Neutrals | Slate scale (`slate-50…950`) | Text, borders, surfaces |
| Surfaces | `surface` `#ffffff`, `surface-muted` `#f8fafc` | Page and card backgrounds |
| Ink | `ink` `#0f172a`, `ink-muted` `#475569`, `ink-faint` `#64748b` | Text |
| Lines | `line` `#e2e8f0` | Borders |

## Typography

- **Font:** Inter (`next/font/google`, `display: swap`), system stack fallback.
- **Scale:** display 40–60 (hero, `text-4xl`–`text-6xl`), h1 32 (`text-3xl`/`text-4xl`),
  h2 24–30 (`text-2xl`/`text-3xl`), body 16, small 14, tiny 12.
- **Weights:** 400 body, 500–600 labels/buttons, 700–800 headings.

## Spacing, radii, shadows, motion

- **Spacing:** 4 px base scale (4/8/12/16/24/32/48). Cards: 16–24 px padding,
  12–16 px radius (`rounded-2xl`), 1 px border + `--shadow-card`.
- **Shadows:** `--shadow-card` (subtle), `--shadow-lift` (hover/elevated).
- **Motion:** 150–200 ms transitions on interactive elements only;
  `prefers-reduced-motion` disables animation and smooth scrolling
  (see `globals.css`).
- **Touch targets:** ≥ 44 px (`min-h-11`/`min-h-12` on buttons and nav).

## Pakistan map watermark

`components/landing/pakistan-map.tsx` — simplified inline SVG outline,
`aria-hidden`, rendered at 5–7% opacity in hero/CTA sections only,
never over body text. It is a decorative mark, not a cartographic
document.

## Component rules

- Every page is built from `components/ui/` primitives — no one-off
  buttons or inputs.
- Every async view has four states: loading (skeleton/spinner), error
  (message + retry), empty (guidance + next action), success.
- Answer-status labels (from the engine, never invented): Verified
  Answer, Detected Answer, Needs Review, Unknown Answer (rendered as
  unanswered — never a green tick), Conflicting Answer.
- No non-functional controls: every visible button does something real
  or is labelled unavailable with a reason.

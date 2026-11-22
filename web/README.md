# OfficerPath AI — Web Frontend (Phase 2, M2)

Next.js (App Router) + React + TypeScript + Tailwind CSS web application
for the OfficerPath AI competitive-exam preparation platform. This is the
new primary frontend; the Flutter app remains as a legacy client.

The Python FastAPI document-intelligence engine (Phase 1, `../app/`) is
the backend. This frontend talks to it only through its HTTP API — it
never imports engine code and never receives backend secrets.

## Stack (pinned versions — see `package.json`)

- Next.js 16.4.6 (App Router, Turbopack) + React 19.3.0
- TypeScript 5.9.3 (strict) + ESLint 9.39.5 (`eslint-config-next`)
- Tailwind CSS 4.3.3 (CSS-first tokens in `app/globals.css` — no JS config file)
- TanStack Query 5.108.2 (data fetching, wired in `components/providers.tsx`)
- React Hook Form 7.92.0 + Zod 4.6.7 (+ `@hookform/resolvers` 7.0.8)

## Install and run

```bash
cd web
npm install        # or npm ci for a clean, lockfile-exact install
cp .env.example .env.local   # fill in real values; never commit .env.local
npm run dev        # http://localhost:3000
npm run build      # production build
npm start          # serve the production build
npm run lint       # ESLint
npx tsc --noEmit   # typecheck
```

Node 20.9+ is required (Next.js 16 minimum); Node 24 was used in M2.
The backend is expected at `NEXT_PUBLIC_API_URL`
(default `http://127.0.0.1:8000` for local development).

## What exists in M2

- **Design system:** tokens in `app/globals.css`, primitives in
  `components/ui/` (Button, Input, Textarea, Card, Badge, Modal, Toast,
  Spinner, EmptyState, ErrorState, Table, Pagination, Progress, Tabs,
  Accordion, Alert, SectionHeading). See `docs/design-tokens.md`.
- **Public pages (11):** Home, About, Features, How It Works, Exam
  Preparation, Pricing, Contact, Login, Register, Privacy Policy, Terms
  and Conditions — plus `/forgot-password`. All real content, no
  placeholder pages.
- **SEO:** per-page metadata, Open Graph tags, `public/robots.txt`,
  `public/sitemap.xml` (public pages only).
- **Pakistan map watermark:** decorative inline SVG in
  `components/landing/pakistan-map.tsx` (hero + CTA sections only).

## What is NOT connected yet (honest state)

- **Login / Register / Forgot password:** real forms with real
  validation, but authentication is M3. Submitting shows a clear
  "not yet connected" state — nothing is sent, no session is created,
  no login is faked.
- **Contact form:** validates locally; submissions are not sent anywhere
  yet (stated on the page). It will be wired in a later milestone.
- **Pricing:** no payment system exists in Phase 2 (Phase 3). The page
  states plainly that everything is free during this phase and that paid
  plans are not priced yet.
- **Dashboard, documents, tests, exam, results, admin:** M4–M9.

## Layout

```
app/            # App Router pages (public pages in M2)
components/
  ui/           # design-system primitives
  layout/       # Header, Footer
  landing/      # hero pieces (Pakistan map watermark)
lib/            # site constants, utils
public/         # robots.txt, sitemap.xml
docs/           # design-tokens.md
```

## Notes

- The canonical site URL (`https://officerpath.ai`) is a placeholder
  until the owner confirms the production domain.
- No real secrets live in this folder. `.env.example` has placeholders
  only; the frontend never receives a Supabase service-role key.
- `next dev` writes to `.next/dev` and `next build` to `.next` (Next 16
  behaviour); both are gitignored.

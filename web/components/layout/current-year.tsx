"use client";

/**
 * Current year, rendered on the client. Next.js 16 blocks `new Date()`
 * during static prerendering, so this component must be rendered
 * inside a <Suspense> boundary (see footer.tsx).
 */
export function CurrentYear() {
  return <>{new Date().getFullYear()}</>;
}

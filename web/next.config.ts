import type { NextConfig } from "next";

const SECURITY_HEADERS = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=()",
  },
];

const nextConfig: NextConfig = {
  // M1 doc 04 §9: strict mode on. The API base URL is env-configured
  // (NEXT_PUBLIC_API_URL, see .env.example) — never hardcoded here.
  reactStrictMode: true,
  cacheComponents: true,
  partialPrefetching: true,
  // M9 security hardening: response headers on every path. No CSP
  // here — a strict CSP breaks Next.js' own inline runtime scripts;
  // clickjacking is covered by X-Frame-Options: DENY instead.
  // X-Robots-Tag carries noindex for the private areas (the auth
  // pages are client components and cannot export metadata, so the
  // header is the mechanism there; dashboard/admin layouts also
  // export robots noindex metadata as a second layer).
  async headers() {
    return [
      {
        source: "/:path*",
        headers: SECURITY_HEADERS,
      },
      {
        // NOTE (M9, found by measuring): "/dashboard/:path*" does
        // match the bare /dashboard redirect, but "/admin/:path*"
        // does NOT match the bare /admin redirect — so the exact
        // paths get their own entries. A 307 is never indexed as
        // content, but the claim is "noindex on ALL private routes",
        // so the header must be present on every one of them.
        source: "/dashboard",
        headers: [{ key: "X-Robots-Tag", value: "noindex, nofollow" }],
      },
      {
        source: "/dashboard/:path*",
        headers: [{ key: "X-Robots-Tag", value: "noindex, nofollow" }],
      },
      {
        source: "/admin",
        headers: [{ key: "X-Robots-Tag", value: "noindex, nofollow" }],
      },
      {
        source: "/admin/:path*",
        headers: [{ key: "X-Robots-Tag", value: "noindex, nofollow" }],
      },
      {
        source: "/login",
        headers: [{ key: "X-Robots-Tag", value: "noindex, nofollow" }],
      },
      {
        source: "/register",
        headers: [{ key: "X-Robots-Tag", value: "noindex, nofollow" }],
      },
      {
        source: "/forgot-password",
        headers: [{ key: "X-Robots-Tag", value: "noindex, nofollow" }],
      },
      {
        source: "/auth/:path*",
        headers: [{ key: "X-Robots-Tag", value: "noindex, nofollow" }],
      },
    ];
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;

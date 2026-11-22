import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // M1 doc 04 §9: strict mode on. The API base URL is env-configured
  // (NEXT_PUBLIC_API_URL, see .env.example) — never hardcoded here.
  reactStrictMode: true,
  cacheComponents: true,
  partialPrefetching: true,
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

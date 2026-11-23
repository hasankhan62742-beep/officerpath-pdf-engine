// OfficerPath AI — PWA manifest (Phase 2, M9, evaluation).
//
// What this provides: the installable-app manifest (name, icons,
// theme colour) for the PUBLIC shell only. What it does NOT
// provide: offline support (no service worker in Phase 2) and no
// install prompt claim — installability also needs a service
// worker, which is deliberately out of scope. The manifest is
// served at /manifest.webmanifest by Next.js automatically.

import type { MetadataRoute } from "next";
import { SITE_DESCRIPTION, SITE_NAME } from "@/lib/site";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: SITE_NAME,
    short_name: SITE_NAME,
    description: SITE_DESCRIPTION,
    start_url: "/",
    display: "standalone",
    background_color: "#ffffff",
    theme_color: "#ea580c",
    icons: [
      {
        src: "/icon-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icon-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "any",
      },
    ],
  };
}

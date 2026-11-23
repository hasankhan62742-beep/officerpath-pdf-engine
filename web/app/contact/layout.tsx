// OfficerPath AI — contact segment layout (Phase 2, M9 SEO).
//
// The contact page itself is a client component (form), so it
// cannot export metadata — this server layout carries the page's
// canonical URL + Open Graph tags instead. Copy is the page's
// own wording ("Talk to us"); nothing is invented.

import type { Metadata } from "next";
import type { ReactNode } from "react";
import { SITE_DESCRIPTION, SITE_NAME, SITE_URL } from "@/lib/site";

export const metadata: Metadata = {
  title: `Contact | ${SITE_NAME}`,
  description:
    "Talk to us about OfficerPath AI — questions, feedback, or help with your exam preparation.",
  alternates: {
    canonical: `${SITE_URL}/contact`,
  },
  openGraph: {
    url: `${SITE_URL}/contact`,
    title: `Contact | ${SITE_NAME}`,
    description: SITE_DESCRIPTION,
  },
};

export default function ContactLayout({ children }: { children: ReactNode }) {
  return children;
}

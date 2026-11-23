import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Inter } from "next/font/google";
import { Header } from "@/components/layout/header";
import { Footer } from "@/components/layout/footer";
import { SITE_DESCRIPTION, SITE_NAME, SITE_URL } from "@/lib/site";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: `${SITE_NAME} — Prepare Smarter. Practice Better. Become Exam Ready.`,
    template: `%s | ${SITE_NAME}`,
  },
  description: SITE_DESCRIPTION,
  openGraph: {
    type: "website",
    siteName: SITE_NAME,
    title: `${SITE_NAME} — Prepare Smarter. Practice Better. Become Exam Ready.`,
    description: SITE_DESCRIPTION,
  },
  twitter: {
    card: "summary_large_image",
    title: `${SITE_NAME} — Prepare Smarter. Practice Better. Become Exam Ready.`,
    description: SITE_DESCRIPTION,
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  // M10: no <Providers> here any more. The QueryClient + Toast
  // providers live in the dashboard and admin layouts only — no
  // page outside those areas consumes useQuery/useMutation/useToast,
  // so public pages no longer download or hydrate the TanStack
  // Query chunk (see components/providers.tsx).
  return (
    <html lang="en" className={`${inter.variable} h-full`}>
      <body className="flex min-h-full flex-col bg-white font-sans text-slate-900 antialiased">
        <Header />
        <main className="flex-1">{children}</main>
        <Footer />
      </body>
    </html>
  );
}

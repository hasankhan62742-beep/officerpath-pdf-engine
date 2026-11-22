/**
 * OfficerPath AI — site constants.
 *
 * SITE_URL is the canonical public URL used for SEO metadata and the
 * sitemap. It is a placeholder until the owner confirms the production
 * domain (recorded in the M2 report); override with
 * NEXT_PUBLIC_SITE_URL when the domain is known.
 */
export const SITE_NAME = "OfficerPath AI";
export const SITE_TAGLINE = "Prepare Smarter. Practice Better. Become Exam Ready.";
export const SITE_DESCRIPTION =
  "OfficerPath AI turns your own books, PDFs and past papers into structured, traceable MCQs — then helps you practise with timed, exam-style tests and track your progress.";
export const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL ?? "https://officerpath.ai";
export const CONTACT_EMAIL = "hello@abdulqadeerml.com";

export const EXAMS = [
  { short: "PPSC", name: "Punjab Public Service Commission" },
  { short: "FPSC", name: "Federal Public Service Commission" },
  { short: "BPSC", name: "Balochistan Public Service Commission" },
  { short: "SPSC", name: "Sindh Public Service Commission" },
  { short: "KPSC", name: "Khyber Pakhtunkhwa Public Service Commission" },
  { short: "CSS", name: "Central Superior Services" },
  { short: "PMS", name: "Provincial Management Service" },
  { short: "NTS", name: "National Testing Service" },
] as const;

export const SUBJECTS = [
  "General Knowledge",
  "Pakistan Affairs",
  "Current Affairs",
  "Islamic Studies",
  "Everyday Science",
  "English",
  "Mathematics",
  "Computer Science",
  "Urdu",
  "Geography",
  "History",
  "Political Science",
  "General Ability",
] as const;

export const NAV_LINKS = [
  { href: "/", label: "Home" },
  { href: "/about", label: "About" },
  { href: "/features", label: "Features" },
  { href: "/how-it-works", label: "How It Works" },
  { href: "/exam-preparation", label: "Exam Preparation" },
  { href: "/pricing", label: "Pricing" },
  { href: "/contact", label: "Contact" },
] as const;

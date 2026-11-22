import Link from "next/link";
import { Button } from "@/components/ui/button";

/** 404 page. */
export default function NotFound() {
  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center px-4 py-24 text-center sm:px-6">
      <p className="text-6xl font-extrabold text-brand-600">404</p>
      <h1 className="mt-4 text-2xl font-bold text-slate-900">Page not found</h1>
      <p className="mt-2 text-base leading-relaxed text-slate-600">
        The page you are looking for does not exist or has moved. Check the
        address, or return to the home page.
      </p>
      <div className="mt-6 flex flex-col gap-3 sm:flex-row">
        <Button href="/">Go to home page</Button>
        <Button href="/contact" variant="secondary">
          Contact us
        </Button>
      </div>
      <p className="mt-6 text-sm text-slate-500">
        Looking for your dashboard?{" "}
        <Link href="/login" className="font-medium text-brand-700 hover:underline">
          Log in
        </Link>
      </p>
    </div>
  );
}

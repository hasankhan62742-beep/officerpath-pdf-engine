// OfficerPath AI — header session state (Phase 2, M3).
//
// Signed-in: shows the user's email (truncated), a Profile link
// and a real Log out button. Signed-out: Log in / Start Your
// Preparation links. The session comes from the Supabase browser
// client and is kept in sync with onAuthStateChange, so logging in
// or out on another tab updates the header here too.
//
// `variant="desktop"` renders the inline row, `variant="mobile"`
// the stacked column used in the hamburger menu.

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { User } from "@supabase/supabase-js";
import { Button } from "@/components/ui/button";
import { createClient } from "@/lib/supabase/client";

export function AuthSection({ variant }: { variant: "desktop" | "mobile" }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const supabase = createClient();
    supabase.auth.getSession().then(({ data: { session } }) => {
      setUser(session?.user ?? null);
      setLoaded(true);
    });
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      setUser(session?.user ?? null);
    });
    return () => subscription.unsubscribe();
  }, []);

  const logOut = async () => {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/");
    router.refresh();
  };

  if (!loaded) {
    // Session still loading — render nothing rather than flashing
    // the signed-out links to a signed-in user.
    return null;
  }

  if (user) {
    const label = user.email ?? "My account";
    return variant === "desktop" ? (
      <>
        <Link
          href="/dashboard/profile"
          className="max-w-44 truncate rounded-lg px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 hover:text-slate-900"
          title={label}
        >
          {label}
        </Link>
        <Button variant="ghost" size="md" onClick={logOut}>
          Log out
        </Button>
      </>
    ) : (
      <>
        <Link
          href="/dashboard/profile"
          className="flex min-h-11 items-center rounded-lg px-3 text-base font-medium text-slate-700 hover:bg-slate-100"
        >
          {label}
        </Link>
        <Button variant="secondary" className="w-full" onClick={logOut}>
          Log out
        </Button>
      </>
    );
  }

  return variant === "desktop" ? (
    <>
      <Button href="/login" variant="ghost">
        Log in
      </Button>
      <Button href="/register" size="md">
        Start Your Preparation
      </Button>
    </>
  ) : (
    <>
      <Button href="/login" variant="secondary" className="w-full">
        Log in
      </Button>
      <Button href="/register" className="w-full">
        Start Your Preparation
      </Button>
    </>
  );
}

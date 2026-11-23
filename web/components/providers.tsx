"use client";

import { useState, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToastProvider } from "@/components/ui/toast";

/**
 * Client-side providers for the protected areas (M10).
 *
 * QueryClient is created once per browser session (useState initializer).
 * M10 scoping: these providers used to wrap the whole app in the root
 * layout, so every public page downloaded and hydrated the TanStack
 * Query chunk (~16 KB raw) even though no public page uses
 * useQuery/useMutation/useToast. They now live in the dashboard and
 * admin layouts only — the only areas that consume them. Auth
 * (Supabase) is wired in M3: the browser client in
 * lib/supabase/client.ts owns the session; the header reads it via
 * AuthSection, and proxy.ts guards /dashboard/*.
 */
export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>{children}</ToastProvider>
    </QueryClientProvider>
  );
}

"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { createClient } from "@/lib/supabase/client";

const loginSchema = z.object({
  email: z.string().trim().email("Please enter a valid email address."),
  password: z.string().min(1, "Please enter your password."),
});

type LoginValues = z.infer<typeof loginSchema>;

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = searchParams.get("next");
  const linkError = searchParams.get("error");
  const [authError, setAuthError] = useState<string | null>(
    linkError === "invalid_link"
      ? "That confirmation or reset link is invalid or has expired. Request a new one below."
      : linkError === "missing_code"
        ? "The link was missing its confirmation code. Request a new one below."
        : null,
  );

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({ resolver: zodResolver(loginSchema) });

  const onSubmit = async (values: LoginValues) => {
    setAuthError(null);
    const supabase = createClient();
    const { error } = await supabase.auth.signInWithPassword({
      email: values.email,
      password: values.password,
    });
    if (error) {
      // Supabase's own message, shown as-is: "Invalid login
      // credentials", "Email not confirmed", and so on.
      setAuthError(error.message);
      return;
    }
    router.push(next && next.startsWith("/") ? next : "/dashboard/profile");
    router.refresh();
  };

  return (
    <div className="mx-auto flex max-w-md flex-col px-4 py-14 sm:px-6">
      <Card>
        <CardTitle as="h1">Log in to OfficerPath AI</CardTitle>
        <CardDescription>
          Enter your email and password to continue to your dashboard.
        </CardDescription>
        {authError ? (
          <Alert tone="danger" title="Could not log you in" className="mt-5">
            {authError}
            {authError.toLowerCase().includes("not confirmed") ? (
              <>
                {" "}
                Check your inbox for the confirmation email we sent when you
                registered — your account is created but not active until you
                confirm it.
              </>
            ) : null}
          </Alert>
        ) : null}
        <form onSubmit={handleSubmit(onSubmit)} noValidate className="mt-6 space-y-5">
          <Input
            label="Email"
            type="email"
            placeholder="you@example.com"
            autoComplete="email"
            error={errors.email?.message}
            {...register("email")}
          />
          <Input
            label="Password"
            type="password"
            placeholder="Your password"
            autoComplete="current-password"
            error={errors.password?.message}
            {...register("password")}
          />
          <Button type="submit" loading={isSubmitting} size="lg" className="w-full">
            Log in
          </Button>
        </form>
        <p className="mt-5 text-center text-sm text-slate-600">
          <Link href="/forgot-password" className="font-medium text-brand-700 hover:underline">
            Forgot your password?
          </Link>
        </p>
        <p className="mt-3 text-center text-sm text-slate-600">
          Don&apos;t have an account?{" "}
          <Link href="/register" className="font-medium text-brand-700 hover:underline">
            Create one — it&apos;s free
          </Link>
        </p>
      </Card>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}

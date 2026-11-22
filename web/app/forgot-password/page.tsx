"use client";

import { useState } from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { createClient } from "@/lib/supabase/client";

const forgotSchema = z.object({
  email: z.string().trim().email("Please enter a valid email address."),
});

type ForgotValues = z.infer<typeof forgotSchema>;

export default function ForgotPasswordPage() {
  const [sent, setSent] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ForgotValues>({ resolver: zodResolver(forgotSchema) });

  const onSubmit = async (values: ForgotValues) => {
    setAuthError(null);
    const supabase = createClient();
    const { error } = await supabase.auth.resetPasswordForEmail(values.email, {
      // The reset link must return to THIS origin (localhost in dev,
      // the production domain when deployed) so the confirmation
      // callback can exchange the code for a session.
      redirectTo: `${window.location.origin}/auth/callback?type=recovery`,
    });
    if (error) {
      setAuthError(error.message);
      return;
    }
    setSent(true);
  };

  return (
    <div className="mx-auto flex max-w-md flex-col px-4 py-14 sm:px-6">
      <Card>
        <CardTitle as="h1">Reset your password</CardTitle>
        <CardDescription>
          Enter the email you registered with and we will send you a reset
          link.
        </CardDescription>
        {sent ? (
          <Alert tone="success" title="Reset email sent" className="mt-5">
            If an account exists for that email, a password-reset link is on
            its way. The link expires after a short time — use it promptly.
          </Alert>
        ) : null}
        {authError ? (
          <Alert tone="danger" title="Could not send the reset email" className="mt-5">
            {authError}
          </Alert>
        ) : null}
        {!sent ? (
          <form onSubmit={handleSubmit(onSubmit)} noValidate className="mt-6 space-y-5">
            <Input
              label="Email"
              type="email"
              placeholder="you@example.com"
              autoComplete="email"
              error={errors.email?.message}
              {...register("email")}
            />
            <Button type="submit" loading={isSubmitting} size="lg" className="w-full">
              Send reset link
            </Button>
          </form>
        ) : null}
        <p className="mt-5 text-center text-sm text-slate-600">
          <Link href="/login" className="font-medium text-brand-700 hover:underline">
            Back to log in
          </Link>
        </p>
      </Card>
    </div>
  );
}

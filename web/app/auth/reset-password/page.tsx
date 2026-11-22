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

// Reached from the link in a password-reset email (via
// /auth/callback?type=recovery, which creates a recovery session).
// If the session is missing — the link expired or was already used —
// the user is told so honestly and sent back to /forgot-password.

const resetSchema = z
  .object({
    password: z.string().min(8, "Password must be at least 8 characters."),
    confirmPassword: z.string().min(1, "Please confirm your password."),
  })
  .refine((v) => v.password === v.confirmPassword, {
    message: "Passwords do not match.",
    path: ["confirmPassword"],
  });

type ResetValues = z.infer<typeof resetSchema>;

export default function ResetPasswordPage() {
  const [done, setDone] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ResetValues>({ resolver: zodResolver(resetSchema) });

  const onSubmit = async (values: ResetValues) => {
    setAuthError(null);
    const supabase = createClient();
    const { error } = await supabase.auth.updateUser({
      password: values.password,
    });
    if (error) {
      setAuthError(
        `${error.message} Request a new reset link from the forgot-password page.`,
      );
      return;
    }
    setDone(true);
  };

  return (
    <div className="mx-auto flex max-w-md flex-col px-4 py-14 sm:px-6">
      <Card>
        <CardTitle as="h1">Choose a new password</CardTitle>
        <CardDescription>
          Enter a new password for your OfficerPath AI account.
        </CardDescription>
        {done ? (
          <Alert tone="success" title="Password updated" className="mt-5">
            Your password has been changed.{" "}
            <Link href="/login" className="font-medium underline">
              Log in with your new password
            </Link>
            .
          </Alert>
        ) : null}
        {authError ? (
          <Alert tone="danger" title="Could not update your password" className="mt-5">
            {authError}
          </Alert>
        ) : null}
        {!done ? (
          <form onSubmit={handleSubmit(onSubmit)} noValidate className="mt-6 space-y-5">
            <Input
              label="New password"
              type="password"
              placeholder="At least 8 characters"
              autoComplete="new-password"
              error={errors.password?.message}
              {...register("password")}
            />
            <Input
              label="Confirm new password"
              type="password"
              placeholder="Repeat your new password"
              autoComplete="new-password"
              error={errors.confirmPassword?.message}
              {...register("confirmPassword")}
            />
            <Button type="submit" loading={isSubmitting} size="lg" className="w-full">
              Update password
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

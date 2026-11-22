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

const forgotSchema = z.object({
  email: z.string().trim().email("Please enter a valid email address."),
});

type ForgotValues = z.infer<typeof forgotSchema>;

export default function ForgotPasswordPage() {
  const [notConnected, setNotConnected] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ForgotValues>({ resolver: zodResolver(forgotSchema) });

  const onSubmit = () => {
    // Password reset lands in M3 with real Supabase Auth email.
    // Nothing is sent here.
    setNotConnected(true);
  };

  return (
    <div className="mx-auto flex max-w-md flex-col px-4 py-14 sm:px-6">
      <Card>
        <CardTitle as="h1">Reset your password</CardTitle>
        <CardDescription>
          Enter the email you registered with and we will send you a reset
          link — once password reset is connected in Milestone 3.
        </CardDescription>
        {notConnected ? (
          <Alert tone="warning" title="Password reset is not connected yet" className="mt-5">
            No reset email was sent. Password reset arrives with real
            authentication in Milestone 3.
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
          <Button type="submit" loading={isSubmitting} size="lg" className="w-full">
            Send reset link
          </Button>
        </form>
        <p className="mt-5 text-center text-sm text-slate-600">
          <Link href="/login" className="font-medium text-brand-700 hover:underline">
            Back to log in
          </Link>
        </p>
      </Card>
    </div>
  );
}

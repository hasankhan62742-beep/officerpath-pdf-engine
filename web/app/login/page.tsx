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

const loginSchema = z.object({
  email: z.string().trim().email("Please enter a valid email address."),
  password: z.string().min(1, "Please enter your password."),
});

type LoginValues = z.infer<typeof loginSchema>;

export default function LoginPage() {
  const [notConnected, setNotConnected] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({ resolver: zodResolver(loginSchema) });

  const onSubmit = () => {
    // Authentication lands in M3. Nothing is sent, no session is
    // created, and no login is faked — the state below says so plainly.
    setNotConnected(true);
  };

  return (
    <div className="mx-auto flex max-w-md flex-col px-4 py-14 sm:px-6">
      <Card>
        <CardTitle as="h1">Log in to OfficerPath AI</CardTitle>
        <CardDescription>
          Enter your email and password to continue to your dashboard.
        </CardDescription>
        {notConnected ? (
          <Alert tone="warning" title="Authentication is not connected yet" className="mt-5">
            This form is real and validated, but sign-in is not wired up yet
            — no credentials were sent anywhere and no session was created.
            Authentication (real email verification and login) arrives in
            Milestone 3.
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
        <div className="mt-5 flex items-center justify-between text-sm">
          <Link href="/forgot-password" className="font-medium text-brand-700 hover:underline">
            Forgot password?
          </Link>
          <Link href="/register" className="font-medium text-brand-700 hover:underline">
            Create an account
          </Link>
        </div>
      </Card>
    </div>
  );
}

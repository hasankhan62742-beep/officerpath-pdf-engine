"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { EXAMS } from "@/lib/site";
import { createClient } from "@/lib/supabase/client";

const registerSchema = z
  .object({
    fullName: z.string().trim().min(2, "Please enter your full name."),
    email: z.string().trim().email("Please enter a valid email address."),
    password: z.string().min(8, "Password must be at least 8 characters."),
    confirmPassword: z.string().min(1, "Please confirm your password."),
    phone: z.string().trim().optional(),
    preferredExam: z.string().min(1, "Please choose an examination."),
    educationLevel: z.string().min(1, "Please choose your education level."),
  })
  .refine((v) => v.password === v.confirmPassword, {
    message: "Passwords do not match.",
    path: ["confirmPassword"],
  });

type RegisterValues = z.infer<typeof registerSchema>;

export default function RegisterPage() {
  const router = useRouter();
  const [sentEmail, setSentEmail] = useState<string | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<RegisterValues>({ resolver: zodResolver(registerSchema) });

  const onSubmit = async (values: RegisterValues) => {
    setAuthError(null);
    const supabase = createClient();
    const { data, error } = await supabase.auth.signUp({
      email: values.email,
      password: values.password,
      options: {
        // The confirmation link must return to THIS origin
        // (localhost in dev, the production domain when deployed).
        emailRedirectTo: `${window.location.origin}/auth/callback`,
        // Profile fields collected at sign-up. The auth callback
        // creates the engine profile from these on confirmation.
        data: {
          full_name: values.fullName,
          phone: values.phone ?? null,
          preferred_exam: values.preferredExam,
          education_level: values.educationLevel,
        },
      },
    });
    if (error) {
      // Supabase's own message, shown as-is: "User already
      // registered", password rules, and so on.
      setAuthError(error.message);
      return;
    }
    if (data.session) {
      // Email confirmation is OFF on this project — the account is
      // active immediately. (On the live project confirmation is ON,
      // so this branch is not expected; it is kept honest rather
      // than assumed.)
      router.push("/dashboard/profile");
      router.refresh();
      return;
    }
    setSentEmail(values.email);
  };

  return (
    <div className="mx-auto flex max-w-lg flex-col px-4 py-14 sm:px-6">
      <Card>
        <CardTitle as="h1">Create your free account</CardTitle>
        <CardDescription>
          Register to upload your books, extract MCQs and take timed tests.
          Free during this phase — no card required.
        </CardDescription>
        {sentEmail ? (
          <Alert tone="success" title="Check your email" className="mt-5">
            We sent a confirmation link to <strong>{sentEmail}</strong>.
            Click it to activate your account, then log in. The link
            expires after a short time — if you don&apos;t see the email,
            check your spam folder.
          </Alert>
        ) : null}
        {authError ? (
          <Alert tone="danger" title="Could not create your account" className="mt-5">
            {authError}
          </Alert>
        ) : null}
        {!sentEmail ? (
          <form onSubmit={handleSubmit(onSubmit)} noValidate className="mt-6 space-y-5">
            <Input
              label="Full name"
              placeholder="Muhammad Ahmed"
              autoComplete="name"
              error={errors.fullName?.message}
              {...register("fullName")}
            />
            <Input
              label="Email"
              type="email"
              placeholder="you@example.com"
              autoComplete="email"
              error={errors.email?.message}
              {...register("email")}
            />
            <div className="grid gap-5 sm:grid-cols-2">
              <Input
                label="Password"
                type="password"
                placeholder="At least 8 characters"
                autoComplete="new-password"
                error={errors.password?.message}
                {...register("password")}
              />
              <Input
                label="Confirm password"
                type="password"
                placeholder="Repeat your password"
                autoComplete="new-password"
                error={errors.confirmPassword?.message}
                {...register("confirmPassword")}
              />
            </div>
            <Input
              label="Phone number (optional)"
              type="tel"
              placeholder="03XX-XXXXXXX"
              autoComplete="tel"
              hint="Optional — only used if we need to reach you about your account."
              error={errors.phone?.message}
              {...register("phone")}
            />
            <div className="grid gap-5 sm:grid-cols-2">
              <div>
                <label htmlFor="preferredExam" className="mb-1.5 block text-sm font-medium text-slate-900">
                  Preferred examination
                </label>
                <select
                  id="preferredExam"
                  className="min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3.5 text-base text-slate-900 shadow-sm focus:border-brand-600 focus:outline-2 focus:outline-brand-600"
                  {...register("preferredExam")}
                >
                  <option value="">Choose an exam…</option>
                  {EXAMS.map((e) => (
                    <option key={e.short} value={e.short}>
                      {e.short} — {e.name}
                    </option>
                  ))}
                  <option value="Other">Other</option>
                </select>
                {errors.preferredExam ? (
                  <p role="alert" className="mt-1.5 text-sm font-medium text-danger-600">
                    {errors.preferredExam.message}
                  </p>
                ) : null}
              </div>
              <div>
                <label htmlFor="educationLevel" className="mb-1.5 block text-sm font-medium text-slate-900">
                  Education level
                </label>
                <select
                  id="educationLevel"
                  className="min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3.5 text-base text-slate-900 shadow-sm focus:border-brand-600 focus:outline-2 focus:outline-brand-600"
                  {...register("educationLevel")}
                >
                  <option value="">Choose a level…</option>
                  <option value="Intermediate">Intermediate</option>
                  <option value="Bachelor's">Bachelor&apos;s</option>
                  <option value="Master's">Master&apos;s</option>
                  <option value="MPhil">MPhil</option>
                  <option value="PhD">PhD</option>
                  <option value="Other">Other</option>
                </select>
                {errors.educationLevel ? (
                  <p role="alert" className="mt-1.5 text-sm font-medium text-danger-600">
                    {errors.educationLevel.message}
                  </p>
                ) : null}
              </div>
            </div>
            <Button type="submit" loading={isSubmitting} size="lg" className="w-full">
              Create account
            </Button>
          </form>
        ) : null}
        <p className="mt-5 text-center text-sm text-slate-600">
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-brand-700 hover:underline">
            Log in
          </Link>
        </p>
      </Card>
    </div>
  );
}

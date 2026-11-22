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
import { EXAMS } from "@/lib/site";

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
  const [notConnected, setNotConnected] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<RegisterValues>({ resolver: zodResolver(registerSchema) });

  const onSubmit = () => {
    // Authentication lands in M3. Nothing is sent and no account is
    // created — the state below says so plainly.
    setNotConnected(true);
  };

  return (
    <div className="mx-auto flex max-w-lg flex-col px-4 py-14 sm:px-6">
      <Card>
        <CardTitle as="h1">Create your free account</CardTitle>
        <CardDescription>
          Register to upload your books, extract MCQs and take timed tests.
          Free during this phase — no card required.
        </CardDescription>
        {notConnected ? (
          <Alert tone="warning" title="Registration is not connected yet" className="mt-5">
            This form is real and validated, but registration is not wired up
            yet — no details were sent anywhere and no account was created.
            Real registration with email verification arrives in Milestone 3.
          </Alert>
        ) : null}
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

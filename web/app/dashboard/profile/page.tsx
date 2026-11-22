"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { EXAMS } from "@/lib/site";
import { createClient } from "@/lib/supabase/client";
import {
  ApiError,
  createProfile,
  getProfile,
  updateProfile,
  type ProfileInput,
} from "@/lib/api";

// Profile page (M3): the signed-in user's real profile, read from
// and written to the engine database (GET/POST/PATCH /api/v1/me
// with the Supabase session token).
//
//  - Profile exists  -> edit form, PATCH on save.
//  - No profile yet  -> creation form prefilled from the sign-up
//    metadata, POST on save (this is the fallback when the auth
//    callback could not reach the engine).
//  - Engine unreachable -> honest error, no fake values.

const profileSchema = z.object({
  fullName: z.string().trim().min(2, "Please enter your full name."),
  phone: z.string().trim().optional(),
  preferredExam: z.string().min(1, "Please choose an examination."),
  educationLevel: z.string().min(1, "Please choose your education level."),
});

type ProfileValues = z.infer<typeof profileSchema>;

const EDUCATION_LEVELS = ["Intermediate", "Bachelor's", "Master's", "MPhil", "PhD", "Other"];

export default function ProfilePage() {
  const [loading, setLoading] = useState(true);
  const [hasProfile, setHasProfile] = useState(false);
  const [email, setEmail] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<ProfileValues>({ resolver: zodResolver(profileSchema) });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const supabase = createClient();
      const {
        data: { session },
      } = await supabase.auth.getSession();
      if (!session) {
        if (!cancelled) {
          setLoadError("Your session has expired. Please log in again.");
          setLoading(false);
        }
        return;
      }
      if (!cancelled) setEmail(session.user.email ?? null);
      try {
        const profile = await getProfile(session.access_token);
        if (cancelled) return;
        setHasProfile(true);
        reset({
          fullName: profile.full_name,
          phone: profile.phone ?? "",
          preferredExam: profile.preferred_exam ?? "",
          educationLevel: profile.education_level ?? "",
        });
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.code === "profile_not_found") {
          // First visit after confirmation — prefill from the
          // sign-up metadata and let the user create the profile.
          const meta = session.user.user_metadata ?? {};
          reset({
            fullName: typeof meta.full_name === "string" ? meta.full_name : "",
            phone: typeof meta.phone === "string" ? meta.phone : "",
            preferredExam: typeof meta.preferred_exam === "string" ? meta.preferred_exam : "",
            educationLevel:
              typeof meta.education_level === "string" ? meta.education_level : "",
          });
        } else if (err instanceof ApiError) {
          setLoadError(`Could not load your profile: ${err.message}`);
        } else {
          setLoadError(
            "The profile service is not reachable right now. Check that the engine is running and reload this page.",
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [reset]);

  const onSubmit = async (values: ProfileValues) => {
    setSaveError(null);
    setSaved(false);
    const supabase = createClient();
    const {
      data: { session },
    } = await supabase.auth.getSession();
    if (!session) {
      setSaveError("Your session has expired. Please log in again.");
      return;
    }
    const input: ProfileInput = {
      full_name: values.fullName,
      phone: values.phone || null,
      preferred_exam: values.preferredExam,
      education_level: values.educationLevel,
    };
    try {
      const savedProfile = hasProfile
        ? await updateProfile(session.access_token, input)
        : await createProfile(session.access_token, input);
      setHasProfile(true);
      reset({
        fullName: savedProfile.full_name,
        phone: savedProfile.phone ?? "",
        preferredExam: savedProfile.preferred_exam ?? "",
        educationLevel: savedProfile.education_level ?? "",
      });
      setSaved(true);
    } catch (err) {
      if (err instanceof ApiError) {
        setSaveError(`Could not save your profile: ${err.message}`);
      } else {
        setSaveError(
          "The profile service is not reachable right now. Your changes were not saved.",
        );
      }
    }
  };

  if (loading) {
    return (
      <Card>
        <div className="flex items-center gap-3 py-6">
          <Spinner />
          <p className="text-sm text-slate-600">Loading your profile…</p>
        </div>
      </Card>
    );
  }

  if (loadError) {
    return (
      <Card>
        <CardTitle as="h1">Your profile</CardTitle>
        <Alert tone="danger" title="Could not load your profile" className="mt-5">
          {loadError}{" "}
          <Link href="/login" className="font-medium underline">
            Log in again
          </Link>
        </Alert>
      </Card>
    );
  }

  return (
    <Card>
      <CardTitle as="h1">Your profile</CardTitle>
      <CardDescription>
        {hasProfile
          ? "Your profile is saved in your account. Edit it below — changes are saved to the database."
          : "We could not find a profile for your account yet. Complete it below to create one."}
      </CardDescription>
      {email ? (
        <p className="mt-4 text-sm text-slate-600">
          Signed in as <strong className="text-slate-900">{email}</strong>
        </p>
      ) : null}
      {saved ? (
        <Alert tone="success" title="Profile saved" className="mt-5">
          Your profile was saved and will be shown exactly like this when you reload.
        </Alert>
      ) : null}
      {saveError ? (
        <Alert tone="danger" title="Could not save" className="mt-5">
          {saveError}
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
          label="Phone number (optional)"
          type="tel"
          placeholder="03XX-XXXXXXX"
          autoComplete="tel"
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
              {EDUCATION_LEVELS.map((level) => (
                <option key={level} value={level}>
                  {level}
                </option>
              ))}
            </select>
            {errors.educationLevel ? (
              <p role="alert" className="mt-1.5 text-sm font-medium text-danger-600">
                {errors.educationLevel.message}
              </p>
            ) : null}
          </div>
        </div>
        <Button type="submit" loading={isSubmitting} size="lg" className="w-full sm:w-auto">
          {hasProfile ? "Save changes" : "Create my profile"}
        </Button>
      </form>
    </Card>
  );
}

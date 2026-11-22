"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { CONTACT_EMAIL } from "@/lib/site";

const contactSchema = z.object({
  name: z.string().trim().min(2, "Please enter your name."),
  email: z.string().trim().email("Please enter a valid email address."),
  subject: z.string().trim().min(3, "Please enter a subject."),
  message: z.string().trim().min(10, "Please write at least 10 characters."),
});

type ContactValues = z.infer<typeof contactSchema>;

export default function ContactPage() {
  const [submitted, setSubmitted] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ContactValues>({ resolver: zodResolver(contactSchema) });

  const onSubmit = () => {
    // No backend endpoint exists yet (M3/M4 will wire it). The form
    // validates locally and states plainly that nothing was sent.
    setSubmitted(true);
  };

  return (
    <div className="mx-auto max-w-7xl px-4 py-14 sm:px-6 lg:px-8">
      <div className="grid gap-10 lg:grid-cols-5">
        <div className="lg:col-span-2">
          <p className="text-sm font-bold uppercase tracking-widest text-brand-600">Contact</p>
          <h1 className="mt-2 text-3xl font-extrabold tracking-tight text-slate-900 sm:text-4xl">
            Talk to us
          </h1>
          <p className="mt-4 text-base leading-relaxed text-slate-600">
            Questions about the platform, a problem with an upload, or a
            suggestion for a feature — write to us and we will get back to
            you.
          </p>
          <Card className="mt-8">
            <CardTitle>Email</CardTitle>
            <CardDescription>
              <a href={`mailto:${CONTACT_EMAIL}`} className="font-medium text-brand-700 hover:underline">
                {CONTACT_EMAIL}
              </a>
            </CardDescription>
          </Card>
          <Card className="mt-4">
            <CardTitle>Response time</CardTitle>
            <CardDescription>
              We aim to reply within two working days. During this phase the
              platform is under active development, so replies may take a
              little longer.
            </CardDescription>
          </Card>
        </div>

        <div className="lg:col-span-3">
          {submitted ? (
            <Card>
              <CardTitle>Thank you — your message is recorded on this page only</CardTitle>
              <CardDescription>
                The contact form is not connected to a backend yet, so your
                message was <strong>not sent anywhere</strong>. It was
                validated on this page and nothing was stored. The form will
                be connected in a later milestone — until then, please email
                us directly at{" "}
                <a href={`mailto:${CONTACT_EMAIL}`} className="font-medium text-brand-700 hover:underline">
                  {CONTACT_EMAIL}
                </a>
                .
              </CardDescription>
              <div className="mt-5">
                <Button variant="secondary" onClick={() => setSubmitted(false)}>
                  Write another message
                </Button>
              </div>
            </Card>
          ) : (
            <Card>
              <CardTitle>Send a message</CardTitle>
              <CardDescription>
                All fields are required. Your message is not sent anywhere
                yet — see the note below the form.
              </CardDescription>
              <form
                onSubmit={handleSubmit(onSubmit)}
                noValidate
                className="mt-6 space-y-5"
              >
                <div className="grid gap-5 sm:grid-cols-2">
                  <Input
                    label="Full name"
                    placeholder="Your name"
                    autoComplete="name"
                    error={errors.name?.message}
                    {...register("name")}
                  />
                  <Input
                    label="Email"
                    type="email"
                    placeholder="you@example.com"
                    autoComplete="email"
                    error={errors.email?.message}
                    {...register("email")}
                  />
                </div>
                <Input
                  label="Subject"
                  placeholder="What is this about?"
                  error={errors.subject?.message}
                  {...register("subject")}
                />
                <Textarea
                  label="Message"
                  placeholder="Write your message here…"
                  error={errors.message?.message}
                  {...register("message")}
                />
                <Alert tone="info" title="Not connected yet">
                  This form validates your input on this page, but there is no
                  backend endpoint for it yet — nothing is sent or stored when
                  you submit. It will be connected in a later milestone.
                </Alert>
                <Button type="submit" loading={isSubmitting} size="lg">
                  Send message
                </Button>
              </form>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

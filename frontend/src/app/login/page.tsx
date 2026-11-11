"use client";

import { ArrowRight, Eye, EyeOff, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Logo } from "@/components/Logo";
import { OperationalLoop } from "@/components/OperationalLoop";
import { Alert, Button, Field, Input } from "@/components/ui";
import { branding } from "@/config/branding";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { vocab } from "@/lib/terms";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<{ email?: string; password?: string }>({});
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const errs: typeof fieldErrors = {};
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) errs.email = "Enter the email address you use for work.";
    if (!password) errs.password = "Enter your password.";
    setFieldErrors(errs);
    if (errs.email || errs.password) return;
    setBusy(true);
    setError(null);
    try {
      await login(email.trim(), password);
      router.replace("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sign-in failed. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    // Phones: logo, headline, sign-in, then the loop. 640–1023px: one centred column. From 1024px: brand and loop on
    // the left, the sign-in panel on white on the right.
    <main className="flex min-h-screen flex-col gap-8 bg-canvas px-page py-8 md:mx-auto md:max-w-xl md:justify-center md:py-12 lg:grid lg:max-w-none lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] lg:gap-0 lg:p-0">
      <div className="max-lg:contents lg:relative lg:flex lg:flex-col lg:justify-center lg:gap-10 lg:px-16 lg:py-24 xl:px-20">
        <Logo className="order-1 h-9 self-start sm:h-11 lg:absolute lg:top-12 lg:left-16 xl:left-20" priority />
        <div className="order-2 lg:max-w-120">
          <h1 className="text-display-compact font-bold text-ink sm:text-display">
            <span className="block">Smarter consignment.</span>
            <span className="block">Better stock control.</span>
            <span className="block">Faster replenishment.</span>
          </h1>
          <p className="mt-3 text-body-lg text-ink-secondary">
            One view of stock across your warehouse and {vocab.partner} network. Manage consignment, replenishment, transfers and backorders together.
          </p>
        </div>
        <OperationalLoop className="order-4 lg:max-w-120" />
      </div>

      {/* Sign-in: the main thing to do here, so it comes straight after the headline on phones. */}
      <section aria-labelledby="sign-in-heading" className="order-3 lg:flex lg:items-center lg:justify-center lg:border-l lg:border-line lg:bg-surface lg:px-12 lg:py-12">
        <div className="w-full rounded-card border border-line bg-surface p-5 shadow-raised sm:p-8 lg:max-w-md lg:border-0 lg:p-0 lg:shadow-none">
          <h2 id="sign-in-heading" className="text-heading font-semibold text-ink">Sign in</h2>
          <p className="mt-1 text-body text-ink-secondary">Welcome back. Use your {branding.productName} work account.</p>

          <form onSubmit={submit} noValidate className="mt-6 space-y-5">
            <Alert>{error}</Alert>
            <Field label="Email" error={fieldErrors.email}>
              {(id, describedBy) => <Input id={id} type="email" inputMode="email" autoComplete="username" placeholder="name@company.com" className="h-11"
                aria-invalid={!!fieldErrors.email} aria-describedby={describedBy} value={email} onChange={(e) => { setEmail(e.target.value); setError(null); }} />}
            </Field>
            <Field label="Password" error={fieldErrors.password}>
              {(id, describedBy) => (
                <div className="relative">
                  <Input id={id} type={showPassword ? "text" : "password"} autoComplete="current-password" className="h-11 pr-12"
                    aria-invalid={!!fieldErrors.password} aria-describedby={describedBy} value={password} onChange={(e) => { setPassword(e.target.value); setError(null); }} />
                  {/* A toggle: the name stays "Show password" and aria-pressed says whether it is on. 44px tap area on touch. */}
                  <button type="button" onClick={() => setShowPassword((s) => !s)} aria-pressed={showPassword} aria-label="Show password"
                    title={showPassword ? "Hide password" : "Show password"}
                    className="touch-target absolute top-1/2 right-1 inline-flex size-9 -translate-y-1/2 items-center justify-center rounded-control text-ink-secondary hover:bg-subtle hover:text-ink focus-visible:focus-ring">
                    {showPassword ? <EyeOff className="size-4.5" aria-hidden /> : <Eye className="size-4.5" aria-hidden />}
                  </button>
                </div>
              )}
            </Field>
            <Button type="submit" variant="primary" size="lg" className="w-full" disabled={busy}>
              {busy ? <><Loader2 className="animate-spin" aria-hidden />Signing in…</> : <>Sign in<ArrowRight aria-hidden /></>}
            </Button>
            <p className="text-center text-label text-ink-secondary">
              Forgot your password? Ask your {branding.companyName} administrator to reset it.
            </p>
          </form>
        </div>
      </section>
    </main>
  );
}

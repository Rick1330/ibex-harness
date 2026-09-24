"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { IconEye, IconEyeOff } from "@tabler/icons-react"

import {
  AuthBrandLockup,
  AuthCard,
  AuthTitle,
} from "@/components/auth/auth-shell"
import { useAuth } from "@/components/auth/auth-provider"
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  AuthApiError,
  getAuthEnvironment,
  issueOperatorSession,
  setAuthDemoFlags,
} from "@/lib/auth/api"
import { cn } from "@/lib/utils"

const VALID_HINT = "devon@acme.com / correct-horse"

export function LoginForm({ className }: { className?: string }) {
  const router = useRouter()
  const params = useSearchParams()
  const { setSession } = useAuth()
  const [email, setEmail] = React.useState("devon@acme.com")
  const [password, setPassword] = React.useState("")
  const [showPw, setShowPw] = React.useState(false)
  const [busy, setBusy] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [errorKind, setErrorKind] = React.useState<
    "credentials" | "unavailable" | "rate" | "env" | null
  >(null)
  const [cooldownUntil, setCooldownUntil] = React.useState<number | null>(null)
  const [now, setNow] = React.useState(Date.now())

  const securityMsg = params.get("reason") === "security"

  React.useEffect(() => {
    if (!cooldownUntil) return
    const t = window.setInterval(() => setNow(Date.now()), 500)
    return () => window.clearInterval(t)
  }, [cooldownUntil])

  const cooldownLeft =
    cooldownUntil && cooldownUntil > now
      ? Math.ceil((cooldownUntil - now) / 1000)
      : 0

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (cooldownLeft > 0) return
    setBusy(true)
    setError(null)
    setErrorKind(null)
    try {
      const { session, cookies } = await issueOperatorSession(email, password)
      setSession(session, cookies)
      if (session.mfa_required && !session.totp_enrolled) {
        router.replace("/enroll-totp")
      } else {
        router.replace("/dashboard")
      }
    } catch (err) {
      if (err instanceof AuthApiError) {
        if (err.code === "login_rate_limited") {
          setErrorKind("rate")
          setError(err.message)
          setCooldownUntil(Date.now() + 60_000)
        } else if (
          err.code === "auth_unavailable" ||
          err.code === "preview_api_missing" ||
          err.code === "api_unreachable"
        ) {
          setErrorKind(
            err.code === "preview_api_missing" ? "env" : "unavailable",
          )
          setError(
            err.code === "preview_api_missing"
              ? "API not available in preview"
              : err.message,
          )
        } else {
          setErrorKind("credentials")
          setError("Invalid email or password")
        }
      } else {
        setErrorKind("unavailable")
        setError("Sign-in temporarily unavailable — try again shortly.")
      }
    } finally {
      setBusy(false)
    }
  }

  const env = getAuthEnvironment()

  return (
    <AuthCard className={className}>
      <AuthBrandLockup />
      <AuthTitle
        title="Sign in"
        subtitle="Operator access to traces, memory, and governance."
      />

      <form onSubmit={onSubmit}>
        <FieldGroup>
          {securityMsg ? (
            <p className="rounded-xl border border-amber-500/35 bg-amber-500/8 px-3.5 py-2.5 text-[12px] leading-relaxed text-foreground">
              Your session was invalidated for security reasons — please sign in
              again.
            </p>
          ) : null}

          <Field>
            <FieldLabel htmlFor="email">Email</FieldLabel>
            <Input
              id="email"
              type="email"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              disabled={busy || cooldownLeft > 0}
              className="h-10"
            />
          </Field>

          <Field>
            <FieldLabel htmlFor="password">Password</FieldLabel>
            <div className="relative">
              <Input
                id="password"
                type={showPw ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                disabled={busy || cooldownLeft > 0}
                className="h-10 pr-10"
              />
              <button
                type="button"
                className="absolute top-1/2 right-2.5 -translate-y-1/2 text-muted-foreground transition-colors hover:text-foreground"
                aria-label={showPw ? "Hide password" : "Show password"}
                onClick={() => setShowPw((s) => !s)}
              >
                {showPw ? (
                  <IconEyeOff className="size-4" />
                ) : (
                  <IconEye className="size-4" />
                )}
              </button>
            </div>
          </Field>

          {error ? (
            <p
              role="alert"
              className={cn(
                "rounded-xl border px-3.5 py-2.5 text-[12px] leading-relaxed",
                errorKind === "credentials" &&
                  "border-border bg-muted/50 text-foreground",
                (errorKind === "rate" ||
                  errorKind === "unavailable" ||
                  errorKind === "env") &&
                  "border-amber-500/35 bg-amber-500/8 text-foreground",
              )}
            >
              {error}
              {cooldownLeft > 0 ? ` (${cooldownLeft}s)` : null}
            </p>
          ) : null}

          <Field>
            <Button
              type="submit"
              disabled={busy || cooldownLeft > 0}
              className="h-10 w-full text-[13px]"
            >
              {busy ? "Signing in…" : "Sign in"}
            </Button>
            <FieldDescription className="text-center text-[12px]">
              Forgot password? Contact your org admin.
            </FieldDescription>
            <FieldDescription className="text-center text-[12px]">
              New org?{" "}
              <Link
                href="/signup"
                className="font-medium text-foreground underline-offset-4 hover:underline"
              >
                Create an account
              </Link>
            </FieldDescription>
          </Field>
        </FieldGroup>
      </form>

      <div className="mt-6 border-t border-border/70 pt-4">
        <p className="font-mono text-[10px] text-muted-foreground">
          Demo · {VALID_HINT} · env={env}
        </p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          <DemoChip
            label="auth down"
            onClick={() => setAuthDemoFlags({ authDown: true })}
          />
          <DemoChip
            label="auth up"
            onClick={() => setAuthDemoFlags({ authDown: false })}
          />
          <DemoChip
            label="preview missing"
            onClick={() => setAuthDemoFlags({ previewMissing: true })}
          />
        </div>
      </div>
    </AuthCard>
  )
}

function DemoChip({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-md border border-border/80 px-2 py-0.5 text-[10px] text-muted-foreground transition-colors hover:border-foreground/30 hover:text-foreground"
    >
      {label}
    </button>
  )
}

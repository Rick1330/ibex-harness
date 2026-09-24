"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
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
import { AuthApiError, registerOperatorOrg } from "@/lib/auth/api"
import { cn } from "@/lib/utils"

/**
 * Org creation signup — fixture for IssueOperatorSession after register.
 * Not OIDC/SSO. Production orgs are often invite-provisioned; this path
 * creates a demo org bound to the new session.
 */
export function SignupForm({ className }: { className?: string }) {
  const router = useRouter()
  const { setSession } = useAuth()
  const [orgName, setOrgName] = React.useState("")
  const [email, setEmail] = React.useState("")
  const [password, setPassword] = React.useState("")
  const [confirm, setConfirm] = React.useState("")
  const [showPw, setShowPw] = React.useState(false)
  const [busy, setBusy] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (password.length < 8) {
      setError("Password must be at least 8 characters")
      return
    }
    if (password !== confirm) {
      setError("Passwords do not match")
      return
    }
    if (!/^[a-z0-9][a-z0-9-]*$/i.test(orgName.replace(/\s+/g, "-"))) {
      setError("Org name must yield a slug like acme or acme-corp")
      return
    }
    setBusy(true)
    try {
      const { session, cookies } = await registerOperatorOrg({
        orgName: orgName.trim(),
        email: email.trim(),
        password,
      })
      setSession(session, cookies)
      if (session.mfa_required && !session.totp_enrolled) {
        router.replace("/enroll-totp")
      } else {
        router.replace("/dashboard")
      }
    } catch (err) {
      if (err instanceof AuthApiError) {
        setError(
          err.code === "auth_unavailable"
            ? "Sign-up temporarily unavailable — try again shortly."
            : err.message,
        )
      } else {
        setError("Could not create account")
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthCard className={className}>
      <AuthBrandLockup />
      <AuthTitle
        title="Create your org"
        subtitle="Spin up an operator workspace. SSO federation is out of scope for this build."
      />

      <form onSubmit={onSubmit}>
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="org">Organization name</FieldLabel>
            <Input
              id="org"
              value={orgName}
              onChange={(e) => setOrgName(e.target.value)}
              placeholder="Acme Corp"
              required
              disabled={busy}
              className="h-10"
            />
          </Field>
          <Field>
            <FieldLabel htmlFor="email">Work email</FieldLabel>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              disabled={busy}
              className="h-10"
            />
          </Field>
          <Field>
            <FieldLabel htmlFor="password">Password</FieldLabel>
            <div className="relative">
              <Input
                id="password"
                type={showPw ? "text" : "password"}
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                disabled={busy}
                className="h-10 pr-10"
              />
              <button
                type="button"
                className="absolute top-1/2 right-2.5 -translate-y-1/2 text-muted-foreground hover:text-foreground"
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
          <Field>
            <FieldLabel htmlFor="confirm">Confirm password</FieldLabel>
            <Input
              id="confirm"
              type={showPw ? "text" : "password"}
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              disabled={busy}
              className="h-10"
            />
          </Field>

          {error ? (
            <p
              role="alert"
              className={cn(
                "rounded-xl border border-border bg-muted/50 px-3.5 py-2.5 text-[12px] leading-relaxed",
              )}
            >
              {error}
            </p>
          ) : null}

          <Field>
            <Button
              type="submit"
              disabled={busy}
              className="h-10 w-full text-[13px]"
            >
              {busy ? "Creating…" : "Create account"}
            </Button>
            <FieldDescription className="text-center text-[12px]">
              Already have access?{" "}
              <Link
                href="/login"
                className="font-medium text-foreground underline-offset-4 hover:underline"
              >
                Sign in
              </Link>
            </FieldDescription>
          </Field>
        </FieldGroup>
      </form>
    </AuthCard>
  )
}

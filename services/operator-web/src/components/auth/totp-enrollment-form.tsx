"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import QRCode from "qrcode"

import {
  AuthBrandLockup,
  AuthCard,
  AuthTitle,
} from "@/components/auth/auth-shell"
import { useAuth } from "@/components/auth/auth-provider"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  AuthApiError,
  beginTotpEnrollment,
  confirmTotpEnrollment,
} from "@/lib/auth/api"

/**
 * BeginTotpEnrollment → ConfirmTotpEnrollment.
 * No backup-codes screen — no generation endpoint in reviewed TOTP service.
 */
export function TotpEnrollmentForm() {
  const router = useRouter()
  const { session, setSession, cookies, ready } = useAuth()
  const [secret, setSecret] = React.useState<string | null>(null)
  const [qrDataUrl, setQrDataUrl] = React.useState<string | null>(null)
  const [code, setCode] = React.useState("")
  const [error, setError] = React.useState<string | null>(null)
  const [busy, setBusy] = React.useState(false)
  const [lockoutUntil, setLockoutUntil] = React.useState<number | null>(null)
  const [now, setNow] = React.useState(Date.now())

  React.useEffect(() => {
    if (!ready) return
    if (!session) {
      router.replace("/login")
      return
    }
    if (session.totp_enrolled) {
      router.replace("/dashboard/settings")
    }
  }, [ready, session, router])

  React.useEffect(() => {
    if (!lockoutUntil) return
    const t = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(t)
  }, [lockoutUntil])

  React.useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await beginTotpEnrollment()
        if (cancelled) return
        setSecret(res.secret)
        const url = await QRCode.toDataURL(res.otpauth_uri, {
          margin: 1,
          width: 208,
          color: { dark: "#141414", light: "#ffffff" },
        })
        if (!cancelled) setQrDataUrl(url)
      } catch (e) {
        if (e instanceof AuthApiError && e.code === "ErrTOTPAlreadyDone") {
          router.replace("/dashboard/settings")
          return
        }
        setError(
          e instanceof AuthApiError ? e.message : "Could not start enrollment",
        )
      }
    })()
    return () => {
      cancelled = true
    }
  }, [router])

  const lockoutLeft =
    lockoutUntil && lockoutUntil > now
      ? Math.ceil((lockoutUntil - now) / 1000)
      : 0

  const onConfirm = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!/^\d{6}$/.test(code)) {
      setError("Enter exactly 6 digits")
      return
    }
    if (lockoutLeft > 0) return
    setBusy(true)
    setError(null)
    try {
      await confirmTotpEnrollment(code)
      if (session && cookies) {
        setSession({ ...session, totp_enrolled: true }, cookies)
      }
      router.replace("/dashboard")
    } catch (err) {
      if (err instanceof AuthApiError) {
        if (err.code === "ErrTOTPLockedOut") {
          setLockoutUntil(Date.now() + 5 * 60_000)
          setError("Too many attempts. Try again in a few minutes.")
        } else if (err.code === "ErrTOTPAlreadyDone") {
          router.replace("/dashboard/settings")
        } else if (err.code === "ErrTOTPInvalidCode") {
          setError(
            "That code didn't match. Check the time on your device and try again.",
          )
        } else {
          setError(err.message)
        }
      } else {
        setError("Enrollment failed")
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthCard>
      <AuthBrandLockup />
      <AuthTitle
        title="Set up authenticator"
        subtitle="Your org requires MFA. Scan the QR, then enter the 6-digit code from your app."
      />

      {qrDataUrl ? (
        <div className="mb-5 flex flex-col items-center gap-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={qrDataUrl}
            alt="TOTP QR code"
            width={208}
            height={208}
            className="rounded-xl border border-border shadow-sm"
          />
          {secret ? (
            <p className="max-w-full break-all text-center font-mono text-[11px] text-muted-foreground">
              Manual secret · {secret}
            </p>
          ) : null}
        </div>
      ) : (
        <div className="mb-5 flex h-[208px] items-center justify-center rounded-xl border border-dashed border-border text-[12px] text-muted-foreground">
          Preparing enrollment…
        </div>
      )}

      <form onSubmit={onConfirm} className="space-y-3">
        <div>
          <label
            htmlFor="totp"
            className="text-[12px] font-medium text-foreground"
          >
            6-digit code
          </label>
          <Input
            id="totp"
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="\d{6}"
            maxLength={6}
            value={code}
            onChange={(e) =>
              setCode(e.target.value.replace(/\D/g, "").slice(0, 6))
            }
            disabled={busy || lockoutLeft > 0}
            className="mt-1.5 h-11 font-mono text-center text-lg tracking-[0.35em]"
            placeholder="••••••"
          />
        </div>
        {error ? (
          <p
            role="alert"
            className="rounded-xl border border-border bg-muted/50 px-3.5 py-2.5 text-[12px] leading-relaxed"
          >
            {error}
            {lockoutLeft > 0
              ? ` (${Math.floor(lockoutLeft / 60)}m ${lockoutLeft % 60}s)`
              : null}
          </p>
        ) : null}
        <Button
          type="submit"
          className="h-10 w-full"
          disabled={busy || code.length !== 6 || lockoutLeft > 0}
        >
          {busy ? "Confirming…" : "Confirm enrollment"}
        </Button>
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          Demo accept code: <span className="font-mono">123456</span>. Backup
          recovery codes are omitted — no generation endpoint exists in the
          reviewed TOTP service yet.
        </p>
      </form>
    </AuthCard>
  )
}

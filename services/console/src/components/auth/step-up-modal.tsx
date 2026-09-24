"use client"

import * as React from "react"

import { useAuth } from "@/components/auth/auth-provider"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { createStepUpToken } from "@/lib/auth/api"

/**
 * In-context step-up — modal overlay. Token used once then discarded.
 * Denial UX is non-leaking (identical message for all failure modes).
 */
export function StepUpModal() {
  const { stepUpOpen, closeStepUp, setPendingStepUp, resolveStepUp } = useAuth()
  const [code, setCode] = React.useState("")
  const [busy, setBusy] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (!stepUpOpen) {
      setCode("")
      setError(null)
      setBusy(false)
    }
  }, [stepUpOpen])

  if (!stepUpOpen) return null

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!/^\d{6}$/.test(code)) {
      setError("Step-up authentication required")
      return
    }
    setBusy(true)
    setError(null)
    try {
      const issued = await createStepUpToken(code)
      setPendingStepUp(issued)
      resolveStepUp(issued.token)
    } catch {
      setError("Step-up authentication required")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-background/75 p-4 backdrop-blur-sm">
      <div
        role="dialog"
        aria-modal
        aria-labelledby="step-up-title"
        className="auth-card-enter w-full max-w-sm rounded-2xl border border-border/80 bg-card p-6 shadow-[0_24px_80px_-28px_oklch(0_0_0_/_0.45)]"
      >
        <div className="mb-3 flex items-center gap-2.5">
          <span className="flex size-8 items-center justify-center rounded-lg bg-foreground text-[11px] font-semibold tracking-[0.08em] text-background">
            IX
          </span>
          <div>
            <p className="font-serif text-[15px] leading-none tracking-tight">
              IBEX
            </p>
            <p className="mt-0.5 font-mono text-[9px] tracking-[0.12em] text-muted-foreground uppercase">
              Step-up
            </p>
          </div>
        </div>
        <h2
          id="step-up-title"
          className="text-[20px] font-medium tracking-tight text-foreground"
        >
          Confirm it&apos;s you
        </h2>
        <p className="mt-1.5 text-[12px] leading-relaxed text-muted-foreground">
          Enter your authenticator code. This issues a one-shot{" "}
          <span className="font-mono text-foreground">X-IBEX-Step-Up</span>{" "}
          token for this action only.
        </p>
        <form onSubmit={onSubmit} className="mt-5 space-y-3">
          <Input
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            value={code}
            onChange={(e) =>
              setCode(e.target.value.replace(/\D/g, "").slice(0, 6))
            }
            className="h-11 font-mono text-center text-lg tracking-[0.35em]"
            placeholder="••••••"
            autoFocus
            disabled={busy}
          />
          {error ? (
            <p role="alert" className="text-[12px] text-foreground">
              {error}
            </p>
          ) : null}
          <div className="flex gap-2">
            <Button
              type="submit"
              className="h-9 flex-1"
              disabled={busy || code.length !== 6}
            >
              {busy ? "Verifying…" : "Continue"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              className="h-9"
              disabled={busy}
              onClick={closeStepUp}
            >
              Cancel
            </Button>
          </div>
          <p className="text-[10px] text-muted-foreground">
            Demo code: <span className="font-mono">123456</span>
          </p>
        </form>
      </div>
    </div>
  )
}

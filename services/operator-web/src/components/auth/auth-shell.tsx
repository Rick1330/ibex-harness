"use client"

import type { ReactNode } from "react"
import Link from "next/link"

import { cn } from "@/lib/utils"

/**
 * Auth surface chrome — centered, atmospheric, brand-led.
 * Not the dense investigation layout. No marketing logos or SSO fakes.
 */
export function AuthShell({
  children,
  footer,
}: {
  children: ReactNode
  footer?: ReactNode
}) {
  return (
    <div className="auth-shell relative flex min-h-svh w-full flex-col overflow-hidden">
      <div
        className="auth-shell-bg pointer-events-none absolute inset-0"
        aria-hidden
      />
      <div
        className="auth-shell-glow pointer-events-none absolute inset-0"
        aria-hidden
      />
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.4] dark:opacity-[0.28]"
        aria-hidden
        style={{
          backgroundImage:
            "radial-gradient(circle at 1px 1px, color-mix(in oklch, var(--foreground) 11%, transparent) 1px, transparent 0)",
          backgroundSize: "22px 22px",
          maskImage:
            "radial-gradient(ellipse 65% 55% at 50% 38%, black 15%, transparent 72%)",
        }}
      />

      <header className="relative z-10 flex items-center justify-between px-6 py-5 md:px-10">
        <Link
          href="/login"
          className="group flex items-center gap-2.5 text-foreground"
        >
          <span className="auth-mark flex size-8 items-center justify-center rounded-lg bg-foreground text-[11px] font-semibold tracking-[0.08em] text-background transition-transform duration-300 group-hover:scale-[1.04]">
            IX
          </span>
          <span className="font-serif text-[22px] leading-none tracking-tight">
            IBEX
          </span>
        </Link>
        <span className="font-mono text-[10px] tracking-wide text-muted-foreground uppercase">
          operator
        </span>
      </header>

      <main className="relative z-10 flex flex-1 items-center justify-center px-4 py-6 md:px-6 md:py-10">
        <div className="auth-card-enter w-full max-w-[420px]">{children}</div>
      </main>

      {footer ? (
        <footer className="relative z-10 px-6 pb-7 text-center font-mono text-[10px] tracking-wide text-muted-foreground md:px-10">
          {footer}
        </footer>
      ) : null}
    </div>
  )
}

export function AuthCard({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-border/70 bg-card/92 p-7 shadow-[0_28px_90px_-36px_oklch(0_0_0_/_0.42)] backdrop-blur-md dark:bg-card/78 md:p-8",
        className,
      )}
    >
      {children}
    </div>
  )
}

export function AuthBrandLockup({ eyebrow = "IBEX" }: { eyebrow?: string }) {
  return (
    <div className="mb-5 flex items-center gap-3">
      <span className="auth-mark flex size-10 items-center justify-center rounded-xl bg-foreground text-[13px] font-semibold tracking-[0.1em] text-background shadow-[0_8px_24px_-10px_oklch(0_0_0_/_0.55)]">
        IX
      </span>
      <div className="min-w-0">
        <p className="font-serif text-[26px] leading-none tracking-tight text-foreground">
          {eyebrow}
        </p>
        <p className="mt-1 font-mono text-[10px] tracking-[0.14em] text-muted-foreground uppercase">
          Control plane
        </p>
      </div>
    </div>
  )
}

export function AuthTitle({
  title,
  subtitle,
}: {
  title: string
  subtitle?: string
}) {
  return (
    <div className="mb-6 space-y-2">
      <h1 className="text-[22px] leading-tight font-medium tracking-tight text-foreground md:text-[24px]">
        {title}
      </h1>
      {subtitle ? (
        <p className="max-w-[34ch] text-[13px] leading-relaxed text-muted-foreground">
          {subtitle}
        </p>
      ) : null}
    </div>
  )
}

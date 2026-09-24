"use client"

import { panelClass } from "@/components/sessions/dashboard-shell"
import * as React from "react"

import { useOnboarding } from "@/components/onboarding/onboarding-provider"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  createUserInvite,
  onboardingCreateAgent,
  slugifyAgentName,
  validateAgentSlug,
} from "@/lib/onboarding/api"
import {
  ONBOARDING_STEPS,
  type MemberRole,
  type OnboardingStepId,
} from "@/lib/onboarding/types"
import { cn } from "@/lib/utils"
import {
  IconCheck,
  IconChevronDown,
  IconX,
} from "@tabler/icons-react"
import { toast } from "sonner"

export function OnboardingChecklist({ className }: { className?: string }) {
  const {
    showChecklist,
    isStepDone,
    activeStep,
    setActiveStep,
    hideChecklist,
  } = useOnboarding()

  if (!showChecklist) return null

  const doneCount = ONBOARDING_STEPS.filter((s) => isStepDone(s.id)).length
  const pct = Math.round((doneCount / ONBOARDING_STEPS.length) * 100)

  return (
    <section
      className={cn(panelClass, className)}
      aria-labelledby="onboarding-title"
    >
      <header className="flex items-start justify-between gap-3 border-b border-border/60 px-4 py-3">
        <div className="min-w-0">
          <h2
            id="onboarding-title"
            className="text-[14px] font-medium tracking-tight"
          >
            Get IBEX Harness running
          </h2>
          <p className="mt-1 text-[12px] text-muted-foreground">
            {doneCount} of {ONBOARDING_STEPS.length} steps complete
          </p>
          <div
            className="mt-2 h-1.5 w-full max-w-xs overflow-hidden rounded-full bg-muted"
            role="progressbar"
            aria-valuenow={pct}
            aria-valuemin={0}
            aria-valuemax={100}
          >
            <div
              className="h-full rounded-full bg-foreground transition-[width] duration-500"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-7 shrink-0 gap-1 text-[11px] text-muted-foreground"
          onClick={hideChecklist}
          aria-label="Hide setup checklist"
        >
          <IconX className="size-3.5" />
          hide
        </Button>
      </header>

      <ol className="divide-y divide-border/50">
        {ONBOARDING_STEPS.map((step, i) => {
          const done = isStepDone(step.id)
          const open = activeStep === step.id
          return (
            <li key={step.id}>
              <button
                type="button"
                className={cn(
                  "flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/40",
                  open && "bg-muted/30",
                )}
                onClick={() => setActiveStep(open ? null : step.id)}
                aria-expanded={open}
              >
                <span
                  className={cn(
                    "flex size-5 shrink-0 items-center justify-center rounded-full border text-[10px]",
                    done
                      ? "border-foreground bg-foreground text-background"
                      : "border-border text-muted-foreground",
                  )}
                  aria-hidden
                >
                  {done ? <IconCheck className="size-3" /> : i + 1}
                </span>
                <span className="min-w-0 flex-1 text-[13px] font-medium">
                  {step.label}
                  {step.optional ? (
                    <span className="ml-1.5 font-normal text-muted-foreground">
                      · optional
                    </span>
                  ) : null}
                </span>
                <IconChevronDown
                  className={cn(
                    "size-4 shrink-0 text-muted-foreground transition-transform",
                    open && "rotate-180",
                  )}
                />
              </button>
              {open ? (
                <div className="border-t border-border/40 bg-muted/15 px-4 py-4">
                  <StepPanel step={step.id} />
                </div>
              ) : null}
            </li>
          )
        })}
      </ol>
    </section>
  )
}

function StepPanel({ step }: { step: OnboardingStepId }) {
  switch (step) {
    case "create_agent":
      return <StepCreateAgent />
    case "invite_teammate":
      return <StepInvite />
    case "set_budget":
      return <StepBudget />
  }
}

function StepCreateAgent() {
  const {
    orgId,
    progress,
    setProgress,
    isStepDone,
    refreshAgentCount,
    setDemoZeroAgents,
  } = useOnboarding()
  const done = isStepDone("create_agent")
  const [name, setName] = React.useState("")
  const [slug, setSlug] = React.useState("")
  const [slugTouched, setSlugTouched] = React.useState(false)
  const [tags, setTags] = React.useState("")
  const [busy, setBusy] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  if (done) {
    if (progress.agent_id) {
      return (
        <div className="space-y-2 text-[12px]">
          <p className="text-muted-foreground">Agent created — keep going.</p>
          <div className="rounded-md border border-border/70 bg-background px-3 py-2 font-mono text-[11px]">
            <div>
              {progress.agent_name}{" "}
              <span className="text-muted-foreground">
                · {progress.agent_slug}
              </span>
            </div>
            <div className="mt-0.5 text-muted-foreground">
              {progress.agent_id}
            </div>
          </div>
        </div>
      )
    }
    return (
      <p className="text-[12px] text-muted-foreground">
        Org already has agents — step complete. Expand the next step.
      </p>
    )
  }

  const onName = (v: string) => {
    setName(v)
    if (!slugTouched) setSlug(slugifyAgentName(v))
  }

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const slugErr = validateAgentSlug(slug)
    if (slugErr) {
      setError(slugErr)
      return
    }
    setBusy(true)
    setError(null)
    try {
      const agent = await onboardingCreateAgent({
        name,
        slug,
        tags: tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
        orgId,
      })
      setProgress((p) => ({
        ...p,
        agent_id: agent.agent_id,
        agent_slug: agent.slug,
        agent_name: agent.name,
      }))
      setDemoZeroAgents(false)
      await refreshAgentCount()
      toast.success("Agent created")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed")
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={onSubmit} className="max-w-md space-y-3">
      <p className="text-[12px] leading-relaxed text-muted-foreground">
        Calls <span className="font-mono text-foreground">POST /v1/agents</span>{" "}
        (4.A.3). Slug must match{" "}
        <span className="font-mono">agents_slug_format</span>.
      </p>
      <Field label="Name">
        <Input
          value={name}
          onChange={(e) => onName(e.target.value)}
          required
          disabled={busy}
          className="h-9"
          placeholder="Support Agent"
        />
      </Field>
      <Field label="Slug">
        <Input
          value={slug}
          onChange={(e) => {
            setSlugTouched(true)
            setSlug(e.target.value.toLowerCase())
          }}
          required
          disabled={busy}
          className="h-9 font-mono text-[12px]"
          placeholder="support-agent"
        />
      </Field>
      <Field label="Tags (optional, comma-separated)">
        <Input
          value={tags}
          onChange={(e) => setTags(e.target.value)}
          disabled={busy}
          className="h-9"
          placeholder="prod, customer-facing"
        />
      </Field>
      {error ? (
        <p role="alert" className="text-[12px] text-foreground">
          {error}
        </p>
      ) : null}
      <Button type="submit" size="sm" className="h-8" disabled={busy || !name}>
        {busy ? "Creating…" : "Create agent"}
      </Button>
    </form>
  )
}

function StepInvite() {
  const { progress, setProgress, isStepDone } = useOnboarding()
  const done = isStepDone("invite_teammate")
  const [email, setEmail] = React.useState("")
  const [name, setName] = React.useState("")
  const [role, setRole] = React.useState<MemberRole>("member")
  const [busy, setBusy] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  const onInvite = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const inv = await createUserInvite({ email, name, role })
      setProgress((p) => ({
        ...p,
        invites: [...p.invites, inv],
        invite_skipped: false,
      }))
      toast.success("Invite sent — status: invited")
      setEmail("")
      setName("")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invite failed")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="max-w-md space-y-3">
      <p className="text-[12px] leading-relaxed text-muted-foreground">
        Wired to{" "}
        <span className="font-mono text-foreground">create_user_invite</span>.
        Pending users stay <span className="font-mono">status: invited</span>{" "}
        until accept — never shown as active early. Skippable for
        single-operator orgs.
      </p>
      {progress.invites.length > 0 ? (
        <ul className="space-y-1 rounded-md border border-border/70 px-3 py-2 text-[11px]">
          {progress.invites.map((inv) => (
            <li key={inv.user_id} className="flex justify-between gap-2">
              <span>
                {inv.name} · {inv.email} · {inv.role}
              </span>
              <span className="font-mono text-muted-foreground">invited</span>
            </li>
          ))}
        </ul>
      ) : null}
      {!done || progress.invites.length > 0 ? (
        <form onSubmit={onInvite} className="space-y-2">
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Name"
            className="h-9"
            required
            disabled={busy}
          />
          <Input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="work@company.com"
            className="h-9"
            required
            disabled={busy}
          />
          <Select value={role} onValueChange={(v) => setRole(v as MemberRole)}>
            <SelectTrigger className="h-9 w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(["owner", "admin", "member", "viewer"] as MemberRole[]).map(
                (r) => (
                  <SelectItem key={r} value={r}>
                    {r}
                  </SelectItem>
                ),
              )}
            </SelectContent>
          </Select>
          {error ? (
            <p role="alert" className="text-[12px]">
              {error}
            </p>
          ) : null}
          <div className="flex gap-2">
            <Button type="submit" size="sm" className="h-8" disabled={busy}>
              {busy ? "Sending…" : "Send invite"}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-8"
              onClick={() =>
                setProgress((p) => ({ ...p, invite_skipped: true }))
              }
            >
              Skip
            </Button>
          </div>
        </form>
      ) : (
        <p className="text-[12px] text-muted-foreground">Step marked done.</p>
      )}
    </div>
  )
}

function StepBudget() {
  const { setProgress, isStepDone } = useOnboarding()
  const done = isStepDone("set_budget")

  return (
    <div className="max-w-md space-y-3 text-[12px]">
      <p className="leading-relaxed text-muted-foreground">
        Recommended before production traffic. Opens Billing → Budget periods (ibex_billing.budget_periods, enforcement_mode: alert_only / hard_cap). Add a monthly cap so a runaway agent cannot overspend.
      </p>
      {done ? (
        <p className="text-muted-foreground">Budget step complete.</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          <Button asChild size="sm" className="h-8">
            <a
              href="/dashboard/billing#budgets"
              onClick={() =>
                setProgress((p) => ({ ...p, budget_visited: true }))
              }
            >
              Open budget periods
            </a>
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-8"
            onClick={() => setProgress((p) => ({ ...p, budget_skipped: true }))}
          >
            Skip for now
          </Button>
        </div>
      )}
    </div>
  )
}

function Field({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <label className="block space-y-1">
      <span className="text-[11px] font-medium text-muted-foreground">
        {label}
      </span>
      {children}
    </label>
  )
}

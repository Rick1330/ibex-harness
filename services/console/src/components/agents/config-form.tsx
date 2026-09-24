"use client"

import * as React from "react"
import { toast } from "sonner"
import { panelClass } from "@/components/sessions/dashboard-shell"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { AgentApiError, patchAgent } from "@/lib/agents/api"
import type { AgentConfig, AgentDetail, MemoryScope } from "@/lib/agents/types"

const PROVIDERS = ["openai", "anthropic", "google"] as const

export function AgentConfigForm({
  agent,
  onSaved,
}: {
  agent: AgentDetail
  onSaved: (next: AgentDetail) => void
}) {
  const [config, setConfig] = React.useState<AgentConfig>(agent.config)
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    setConfig(agent.config)
  }, [agent.agent_id, agent.config])

  const set = <K extends keyof AgentConfig>(key: K, value: AgentConfig[K]) => {
    setConfig((c) => ({ ...c, [key]: value }))
  }

  const toggleProvider = (p: string) => {
    setConfig((c) => {
      const has = c.llm_providers.includes(p)
      const next = has
        ? c.llm_providers.filter((x) => x !== p)
        : [...c.llm_providers, p]
      return { ...c, llm_providers: next }
    })
  }

  const ctxPct = Math.round((config.context_budget_tokens / 128_000) * 100)

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      const next = await patchAgent(agent.agent_id, { config })
      onSaved(next)
      toast.success("Configuration saved")
    } catch (e) {
      const msg =
        e instanceof AgentApiError ? `${e.code}: ${e.message}` : "Save failed"
      setError(msg)
      toast.error(msg)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card className={panelClass}>
      <CardHeader className="gap-1 border-b px-4 py-3">
        <CardTitle className="text-[13px] font-medium">Configuration</CardTitle>
        <p className="text-[12px] text-muted-foreground">
          Maps to <span className="font-mono">config</span> JSONB on{" "}
          <span className="font-mono">ibex_core.agents</span>. Save issues{" "}
          <span className="font-mono">PATCH /v1/agents/{"{id}"}</span>.
        </p>
      </CardHeader>
      <CardContent className="space-y-6 px-4 py-4 text-[13px]">
        <section className="space-y-3">
          <h3 className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
            Memory
          </h3>
          <ToggleRow
            id="memory_extraction_enabled"
            label="memory_extraction_enabled"
            description="Extract memories from completed turns"
            checked={config.memory_extraction_enabled}
            onChange={(v) => set("memory_extraction_enabled", v)}
          />
          <Field
            label="memory_scope"
            description="Where extracted memories are visible"
          >
            <Select
              value={config.memory_scope}
              onValueChange={(v) => set("memory_scope", v as MemoryScope)}
            >
              <SelectTrigger
                size="sm"
                className="w-full max-w-[160px] sm:w-[160px]"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="agent">agent</SelectItem>
                <SelectItem value="org">org</SelectItem>
                <SelectItem value="session">session</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          <Field
            label="max_memories_per_context"
            description="Cap on memories injected per request"
          >
            <Input
              type="number"
              className="h-8 w-28 font-mono text-[12px]"
              value={config.max_memories_per_context}
              onChange={(e) =>
                set("max_memories_per_context", Number(e.target.value) || 0)
              }
            />
          </Field>
        </section>

        <section className="space-y-3">
          <h3 className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
            Context
          </h3>
          <Field
            label="context_budget_tokens"
            description={`≈ ${ctxPct}% of a 128k model context window`}
          >
            <Input
              type="number"
              className="h-8 w-36 font-mono text-[12px]"
              value={config.context_budget_tokens}
              onChange={(e) =>
                set("context_budget_tokens", Number(e.target.value) || 0)
              }
            />
          </Field>
        </section>

        <section className="space-y-3">
          <h3 className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
            Drift
          </h3>
          <ToggleRow
            id="drift_detection_enabled"
            label="drift_detection_enabled"
            description="Emit drift signals for this agent"
            checked={config.drift_detection_enabled}
            onChange={(v) => set("drift_detection_enabled", v)}
          />
          <Field
            label="drift_sensitivity"
            description={`Threshold ${config.drift_sensitivity.toFixed(2)} — Phase 4.5 producer required for alerts UI`}
          >
            <input
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={config.drift_sensitivity}
              onChange={(e) => set("drift_sensitivity", Number(e.target.value))}
              className="w-48 accent-foreground"
            />
          </Field>
        </section>

        <section className="space-y-3">
          <h3 className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
            Reliability
          </h3>
          <Field
            label="loop_detection_threshold"
            description="Identical tool-call repeats before break"
          >
            <Input
              type="number"
              className="h-8 w-28 font-mono text-[12px]"
              value={config.loop_detection_threshold}
              onChange={(e) =>
                set("loop_detection_threshold", Number(e.target.value) || 0)
              }
            />
          </Field>
          <Field
            label="heartbeat_interval_seconds"
            description="Session liveness probe interval"
          >
            <Input
              type="number"
              className="h-8 w-28 font-mono text-[12px]"
              value={config.heartbeat_interval_seconds}
              onChange={(e) =>
                set("heartbeat_interval_seconds", Number(e.target.value) || 0)
              }
            />
          </Field>
        </section>

        <section className="space-y-3">
          <h3 className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
            Providers
          </h3>
          <Field
            label="llm_providers"
            description="Allowed providers for this agent"
          >
            <div className="flex flex-wrap gap-2">
              {PROVIDERS.map((p) => {
                const on = config.llm_providers.includes(p)
                return (
                  <button
                    key={p}
                    type="button"
                    onClick={() => toggleProvider(p)}
                    className={
                      on
                        ? "rounded-md border border-foreground bg-foreground px-2 py-1 font-mono text-[11px] text-background"
                        : "rounded-md border px-2 py-1 font-mono text-[11px] text-muted-foreground"
                    }
                  >
                    {p}
                  </button>
                )
              })}
            </div>
          </Field>
          <Field
            label="default_provider / default_model"
            description="Soft-validated only — not verified against the provider registry yet (Track C)."
          >
            <div className="flex flex-wrap gap-2">
              <Input
                className="h-8 w-36 font-mono text-[12px]"
                placeholder="provider"
                value={config.default_provider ?? ""}
                onChange={(e) =>
                  set("default_provider", e.target.value || null)
                }
              />
              <Input
                className="h-8 w-44 font-mono text-[12px]"
                placeholder="model"
                value={config.default_model ?? ""}
                onChange={(e) => set("default_model", e.target.value || null)}
              />
            </div>
          </Field>
          <p className="rounded-md border border-amber-600/30 bg-amber-500/5 px-3 py-2 text-[12px] text-amber-900 dark:text-amber-200">
            Registry allowlist validation is deferred. Values are accepted as
            configuration hints, not guaranteed routable endpoints.
          </p>
        </section>

        {error && (
          <p className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 font-mono text-[12px] text-destructive">
            {error}
          </p>
        )}

        <Button size="sm" disabled={saving} onClick={save}>
          {saving ? "Saving…" : "Save configuration"}
        </Button>
      </CardContent>
    </Card>
  )
}

function Field({
  label,
  description,
  children,
}: {
  label: string
  description: string
  children: React.ReactNode
}) {
  return (
    <div className="grid gap-1.5 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
      <div>
        <Label className="font-mono text-[12px]">{label}</Label>
        <p className="text-[12px] text-muted-foreground">{description}</p>
      </div>
      {children}
    </div>
  )
}

function ToggleRow({
  id,
  label,
  description,
  checked,
  onChange,
}: {
  id: string
  label: string
  description: string
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div>
        <Label htmlFor={id} className="font-mono text-[12px]">
          {label}
        </Label>
        <p className="text-[12px] text-muted-foreground">{description}</p>
      </div>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={
          checked
            ? "h-6 w-10 shrink-0 rounded-full bg-foreground"
            : "h-6 w-10 shrink-0 rounded-full bg-muted"
        }
      >
        <span
          className={
            checked
              ? "ml-4 block size-5 rounded-full bg-background transition-all"
              : "ml-0.5 block size-5 rounded-full bg-background transition-all"
          }
        />
      </button>
    </div>
  )
}

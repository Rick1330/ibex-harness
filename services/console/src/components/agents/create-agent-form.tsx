"use client"

import * as React from "react"
import { toast } from "sonner"

import { useOnboardingOptional } from "@/components/onboarding/onboarding-provider"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { createAgent } from "@/lib/agents/api"
import { slugifyAgentName, validateAgentSlug } from "@/lib/onboarding/api"

/** Inline create agent — POST /v1/agents. Used by Agents page + onboarding. */
export function CreateAgentForm({
  orgId,
  onCreated,
  onCancel,
}: {
  orgId: string
  onCreated: (agentId: string) => void
  onCancel?: () => void
}) {
  const onboarding = useOnboardingOptional()
  const [name, setName] = React.useState("")
  const [slug, setSlug] = React.useState("")
  const [slugTouched, setSlugTouched] = React.useState(false)
  const [tags, setTags] = React.useState("")
  const [busy, setBusy] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

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
      const agent = await createAgent({
        name,
        slug,
        tags: tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
        org_id: orgId,
      })
      onboarding?.setProgress((p) => ({
        ...p,
        agent_id: agent.agent_id,
        agent_slug: agent.slug,
        agent_name: agent.name,
      }))
      await onboarding?.refreshAgentCount()
      toast.success("Agent created")
      onCreated(agent.agent_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed")
    } finally {
      setBusy(false)
    }
  }

  return (
    <form
      onSubmit={onSubmit}
      className="mx-auto max-w-md space-y-3 rounded-lg border border-border/70 bg-card p-4 text-left"
    >
      <div>
        <div className="text-[13px] font-medium">Create agent</div>
        <p className="mt-0.5 text-[11px] text-muted-foreground">
          <span className="font-mono">POST /v1/agents</span> · slug{" "}
          <span className="font-mono">^[a-z0-9-]+$</span>
        </p>
      </div>
      <label className="block space-y-1">
        <span className="text-[11px] text-muted-foreground">Name</span>
        <Input
          value={name}
          onChange={(e) => {
            setName(e.target.value)
            if (!slugTouched) setSlug(slugifyAgentName(e.target.value))
          }}
          required
          disabled={busy}
          className="h-9"
        />
      </label>
      <label className="block space-y-1">
        <span className="text-[11px] text-muted-foreground">Slug</span>
        <Input
          value={slug}
          onChange={(e) => {
            setSlugTouched(true)
            setSlug(e.target.value.toLowerCase())
          }}
          required
          disabled={busy}
          className="h-9 font-mono text-[12px]"
        />
      </label>
      <label className="block space-y-1">
        <span className="text-[11px] text-muted-foreground">
          Tags (optional)
        </span>
        <Input
          value={tags}
          onChange={(e) => setTags(e.target.value)}
          disabled={busy}
          className="h-9"
          placeholder="prod, internal"
        />
      </label>
      {error ? (
        <p role="alert" className="text-[12px]">
          {error}
        </p>
      ) : null}
      <div className="flex gap-2">
        <Button type="submit" size="sm" className="h-8" disabled={busy}>
          {busy ? "Creating…" : "Create"}
        </Button>
        {onCancel ? (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-8"
            onClick={onCancel}
            disabled={busy}
          >
            Cancel
          </Button>
        ) : null}
      </div>
    </form>
  )
}

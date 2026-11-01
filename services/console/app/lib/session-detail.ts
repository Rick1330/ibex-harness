import type { PreviewSession, SessionFocus, SessionPrivacy, SessionRound, SessionSpan, SessionToolCall } from "./session-preview"

/**
 * The illustrative fixture set is recorded for one operator day. Keeping the day
 * in one place lets the detail header show a real date without implying that a
 * live timestamp was observed.
 */
export const SESSION_PREVIEW_DAY = "2026-10-29"

export type SessionTotals = {
  tokensIn: number
  tokensOut: number
  costUsd: number
  /** `$0.090` for the strip, rounded to three significant decimals. */
  costShort: string
  /** `$0.09021` for the exact-value tooltip. */
  costExact: string
  tokensLabel: string
  /** True when the rendered thread covers every turn recorded on the session. */
  complete: boolean
}

export type SessionStepRow = {
  id: string
  label: string
  kind: SessionSpan["kind"]
  durationMs: number
  summary: string
  status: "ok" | "error" | "skipped"
  span: SessionSpan | null
  toolCall: SessionToolCall | null
}

export function parseClockMs(clock: string): number {
  const [hours = "0", minutes = "0", seconds = "0"] = clock.split(":")
  return (Number(hours) * 3600 + Number(minutes) * 60 + Number.parseFloat(seconds)) * 1000
}

export function parseDurationMs(value: string): number {
  const hours = value.match(/(\d+)\s*h/)
  const minutes = value.match(/(\d+)\s*m/)
  const seconds = value.match(/([\d.]+)\s*s/)
  if (hours || minutes || seconds) {
    return (
      (Number(hours?.[1] ?? 0) * 3600 +
        Number(minutes?.[1] ?? 0) * 60 +
        Number.parseFloat(seconds?.[1] ?? "0")) *
      1000
    )
  }
  return Number.parseFloat(value) * 1000 || 0
}

export function parseCostUsd(value: string): number {
  return Number.parseFloat(value.replace(/[^0-9.]/g, "")) || 0
}

export function roundOffsetMs(session: PreviewSession, round: SessionRound): number {
  return Math.max(0, parseClockMs(round.startedAt) - parseClockMs(session.first))
}

export function sessionAgentTimeMs(rounds: SessionRound[]): number {
  return rounds.reduce((sum, round) => sum + round.latencyMs, 0)
}

export function sessionWallTimeMs(session: PreviewSession): number {
  const recorded = parseDurationMs(session.duration)
  if (recorded > 0) return recorded
  return Math.max(0, parseClockMs(session.last) - parseClockMs(session.first))
}

export function sessionTotals(session: PreviewSession, rounds: SessionRound[]): SessionTotals {
  const complete = rounds.length === session.turns
  const costUsd = complete
    ? rounds.reduce((sum, round) => sum + parseCostUsd(round.cost), 0)
    : parseCostUsd(session.cost)
  const tokensIn = complete ? rounds.reduce((sum, round) => sum + round.tokensIn, 0) : parseUsage(session.usage).input
  const tokensOut = complete ? rounds.reduce((sum, round) => sum + round.tokensOut, 0) : parseUsage(session.usage).output
  return {
    tokensIn,
    tokensOut,
    costUsd,
    costShort: formatCostShort(costUsd),
    costExact: `$${costUsd.toFixed(5)}`,
    tokensLabel: `${formatCount(tokensIn)} in · ${formatCount(tokensOut)} out`,
    complete,
  }
}

function parseUsage(value: string): { input: number; output: number } {
  const numbers = value.match(/\d[\d,]*/g)?.map((entry) => Number(entry.replaceAll(",", ""))) ?? []
  return { input: numbers[0] ?? 0, output: numbers[1] ?? 0 }
}

export function formatCount(value: number): string {
  return value.toLocaleString("en-US")
}

export function formatCostShort(value: number): string {
  if (value === 0) return "$0.000"
  if (value < 0.001) return `$${value.toFixed(5)}`
  return `$${value.toFixed(3)}`
}

export function formatMs(value: number): string {
  if (value >= 1000) return `${(value / 1000).toFixed(2)} s`
  return `${Math.round(value)} ms`
}

export function formatSeconds(value: number): string {
  return `${(value / 1000).toFixed(2)} s`
}

export function formatOffset(value: number): string {
  return `+${(value / 1000).toFixed(1)}s`
}

export function formatSessionStart(session: PreviewSession): string {
  const date = new Date(`${SESSION_PREVIEW_DAY}T${session.first}.000Z`)
  if (Number.isNaN(date.getTime())) return session.first
  const day = new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(date)
  return `${day}, ${session.first} UTC`
}

export function turnToolMs(round: SessionRound): number {
  return round.spans.filter((item) => item.kind === "tool").reduce((sum, item) => sum + item.durationMs, 0)
}

export function turnFailedTools(round: SessionRound): number {
  return round.toolCalls.filter((tool) => tool.status === "error").length
}

export function sessionDriftCount(rounds: SessionRound[]): number {
  return rounds.filter((round) => round.drift !== null).length
}

export function sessionFailureCount(rounds: SessionRound[]): number {
  return rounds.filter((round) => round.outcome !== "succeeded").length
}

export const CAPTURE_MODE_LABELS: Record<SessionPrivacy["captureMode"], string> = {
  metadata: "Metadata only",
  redacted: "Redacted",
  off: "Off",
}

export const COMPLETENESS_LABELS: Record<SessionPrivacy["completeness"], string> = {
  complete: "Complete",
  partial: "Partial",
  sampled: "Sampled",
  late: "Late",
  redacted: "Redacted",
  expired: "Expired",
  deleted: "Deleted",
  simulated: "Simulated",
}

export function sessionPrivacy(round: SessionRound): SessionPrivacy {
  return (
    round.privacy ?? {
      captureMode: "metadata",
      completeness: "complete",
      redactionClass: "metadata",
      redactionProofVersion: "session-metadata-allowlist/v1",
      droppedFields: [],
      pii: { detected: false, redacted: false, threshold: 0.6, findings: [] },
      note: "No redaction was recorded for this turn. Metadata completeness is complete; content is never part of this contract.",
    }
  )
}

export function outcomeLabel(outcome: SessionRound["outcome"]): string {
  if (outcome === "succeeded") return "Succeeded"
  if (outcome === "denied") return "Denied"
  return "Failed"
}

export function outcomeTone(outcome: SessionRound["outcome"]): "success" | "warning" | "destructive" {
  if (outcome === "succeeded") return "success"
  return outcome === "denied" ? "warning" : "destructive"
}

export function roundFailureMessage(round: SessionRound): string | null {
  if (round.outcome === "succeeded") return null
  if (round.error) return round.error
  const failed = round.spans.find((span) => span.status === "error")
  if (failed) return `${failed.label} failed while handling this turn.`
  return "This turn did not complete. No failure reason was recorded."
}

export function stepRows(round: SessionRound): SessionStepRow[] {
  const bySpan = new Map<string, SessionToolCall>()
  for (const tool of round.toolCalls) {
    if (tool.spanId) bySpan.set(tool.spanId, tool)
  }
  const rows: SessionStepRow[] = round.spans
    .slice()
    .sort((first, second) => first.offsetMs - second.offsetMs || second.durationMs - first.durationMs)
    .map((span) => {
      const toolCall = bySpan.get(span.id) ?? null
      return {
        id: span.id,
        label: span.label,
        kind: span.kind,
        durationMs: span.durationMs,
        summary: toolCall?.summary ?? span.summary,
        status: span.status === "error" ? "error" : (toolCall?.status ?? "ok"),
        span,
        toolCall,
      }
    })

  for (const tool of round.toolCalls) {
    if (tool.spanId) continue
    rows.push({
      id: `call-${round.id}-${tool.name}`,
      label: `tool.${tool.name}`,
      kind: "tool",
      durationMs: tool.durationMs,
      summary: tool.summary,
      status: tool.status,
      span: null,
      toolCall: tool,
    })
  }
  return rows
}

export function spanDepth(spans: SessionSpan[], span: SessionSpan): number {
  let depth = 0
  let current: SessionSpan | undefined = span
  const seen = new Set<string>()
  while (current?.parentId && depth < 8) {
    if (seen.has(current.parentId)) break
    seen.add(current.parentId)
    const parent = spans.find((item) => item.id === current?.parentId)
    if (!parent) break
    depth += 1
    current = parent
  }
  return depth
}

export function spanChildren(spans: SessionSpan[], span: SessionSpan): SessionSpan[] {
  return spans.filter((item) => item.parentId === span.id)
}

/** Marks the longest ancestor chain so the waterfall can keep it at full opacity. */
export function criticalSpanIds(spans: SessionSpan[]): Set<string> {
  const totals = new Map<string, number>()
  for (const item of spans) {
    let total = item.durationMs
    let current: SessionSpan | undefined = item
    const seen = new Set<string>()
    while (current?.parentId && !seen.has(current.parentId)) {
      seen.add(current.parentId)
      const parent = spans.find((entry) => entry.id === current?.parentId)
      if (!parent) break
      total += parent.durationMs
      current = parent
    }
    totals.set(item.id, total)
  }
  const longest = [...totals.entries()].sort((first, second) => second[1] - first[1])[0]?.[0]
  const result = new Set<string>()
  if (!longest) return result
  let current = spans.find((item) => item.id === longest)
  while (current) {
    result.add(current.id)
    const parent = current.parentId ? spans.find((item) => item.id === current?.parentId) : undefined
    current = parent
  }
  return result
}

export function slowestSpan(spans: SessionSpan[]): SessionSpan | null {
  if (spans.length === 0) return null
  return [...spans].sort((first, second) => second.durationMs - first.durationMs)[0] ?? null
}

export function spanShare(span: SessionSpan, totalMs: number): number {
  if (totalMs <= 0) return 0
  return Math.round((span.durationMs / totalMs) * 100)
}

export function spanTotalMs(round: SessionRound): number {
  return round.spans.reduce((sum, span) => sum + span.durationMs, 0)
}

export function traceEndMs(round: SessionRound): number {
  return round.spans.reduce((end, span) => Math.max(end, span.offsetMs + span.durationMs), 0)
}

export function unaccountedMs(round: SessionRound): number {
  return Math.max(0, round.latencyMs - traceEndMs(round))
}

export function driftState(round: SessionRound): "advisory" | "clean" | "not_checked" {
  if (round.drift) return "advisory"
  return round.driftCheck?.state === "clean" ? "clean" : "not_checked"
}

export function decisionLabel(decision: SessionRound["policy"]["decision"]): string {
  if (decision === "allow") return "Allowed"
  if (decision === "deny") return "Blocked"
  return "Needs approval"
}

export function decisionIcon(decision: SessionRound["policy"]["decision"]): "success" | "destructive" | "warning" {
  if (decision === "allow") return "success"
  return decision === "deny" ? "destructive" : "warning"
}

export function traceSummary(round: SessionRound): string {
  return `${spanTotalMs(round)} ms in spans · ${round.spans.length} spans · ${turnToolMs(round)} ms in tools`
}

export function turnInsight(round: SessionRound, focus: SessionFocus): string {
  switch (focus) {
    case "trace": {
      const longest = slowestSpan(round.spans)
      if (!longest) return "No spans were recorded for this turn."
      const total = spanTotalMs(round)
      return `${longest.label} was the longest span: ${longest.durationMs} ms, ${spanShare(longest, total)}% of the turn.`
    }
    case "memories": {
      if (round.memories.length === 0) return "No memories retrieved."
      const used = round.memories.filter((memory) => memory.usedInResponse).length
      return `${round.memories.length} memories retrieved · ${used} included in the reply.`
    }
    case "directive":
      return `${round.directive.name} ${round.directive.version} governed this turn.`
    case "policy":
      if (round.policy.decision === "allow") return `${round.policy.action} was allowed by ${round.policy.id}.`
      if (round.policy.decision === "deny") return `${round.policy.action} was blocked by ${round.policy.id}.`
      return `${round.policy.action} was sent for approval by ${round.policy.id}.`
    case "privacy": {
      const privacy = sessionPrivacy(round)
      if (privacy.pii.detected) {
        const count = privacy.pii.findings.reduce((sum, finding) => sum + finding.occurrences, 0)
        return `${count} PII ${count === 1 ? "entity" : "entities"} detected · capture ${CAPTURE_MODE_LABELS[privacy.captureMode].toLowerCase()} · record ${COMPLETENESS_LABELS[privacy.completeness].toLowerCase()}.`
      }
      return `No PII finding recorded. Capture ${CAPTURE_MODE_LABELS[privacy.captureMode].toLowerCase()} · record ${COMPLETENESS_LABELS[privacy.completeness].toLowerCase()}.`
    }
    default:
      if (round.drift) return `Drift advisory on this turn: ${round.drift.detail}`
      return round.driftCheck?.state === "clean" ? "No drift detected on this turn." : "Drift wasn't checked for this turn."
  }
}

export function statusLabel(status: SessionStepRow["status"]): string {
  if (status === "ok") return "OK"
  if (status === "error") return "Failed"
  return "Skipped"
}

export function jsonLineCount(value: unknown): number {
  return JSON.stringify(value, null, 2)?.split("\n").length ?? 0
}

export function totalToolCalls(rounds: SessionRound[]): number {
  return rounds.reduce((sum, round) => sum + round.toolCalls.length, 0)
}

export function toolUsage(rounds: SessionRound[]): Array<{ name: string; count: number; turns: number[] }> {
  const usage = new Map<string, { name: string; count: number; turns: number[] }>()
  for (const round of rounds) {
    for (const tool of round.toolCalls) {
      const entry = usage.get(tool.name) ?? { name: tool.name, count: 0, turns: [] }
      entry.count += 1
      if (!entry.turns.includes(round.index)) entry.turns.push(round.index)
      usage.set(tool.name, entry)
    }
  }
  return [...usage.values()].sort((first, second) => second.count - first.count || first.name.localeCompare(second.name))
}

export function memoryUsage(rounds: SessionRound[]): Array<{ id: string; label: string; count: number; turns: number[] }> {
  const usage = new Map<string, { id: string; label: string; count: number; turns: number[] }>()
  for (const round of rounds) {
    for (const memory of round.memories) {
      const entry = usage.get(memory.id) ?? { id: memory.id, label: memory.label, count: 0, turns: [] }
      entry.count += 1
      if (!entry.turns.includes(round.index)) entry.turns.push(round.index)
      usage.set(memory.id, entry)
    }
  }
  return [...usage.values()].sort((first, second) => second.count - first.count || first.label.localeCompare(second.label))
}

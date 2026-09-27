import type { ReactNode } from "react"

import { CopyId } from "@/components/explore/copy-id"
import { panelClass } from "@/components/sessions/dashboard-shell"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { OperatorTraceDetail } from "@/lib/api/contracts"

function Section({
  title,
  state,
  children,
}: Readonly<{ title: string; state: "available" | "unavailable" | "partial" | "unknown"; children: ReactNode }>) {
  return (
    <section>
      <div className="mb-3 flex items-center gap-2">
        <h2 className="text-sm font-medium">{title}</h2>
        <span className="rounded-full border px-2 py-0.5 font-mono text-[11px] text-muted-foreground">{state}</span>
      </div>
      {children}
    </section>
  )
}

function Metadata({ label, value }: Readonly<{ label: string; value: ReactNode }>) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-1 break-all text-sm">{value}</dd>
    </div>
  )
}

function IdentityPanel({ trace }: Readonly<{ trace: OperatorTraceDetail }>) {
  return (
    <section>
      <h2 className="mb-3 text-sm font-medium">Identity</h2>
      <dl className="grid gap-4 md:grid-cols-2">
        <Metadata label="Trace" value={<CopyId value={trace.trace_id} label="trace_id" />} />
        <Metadata label="Request" value={<CopyId value={trace.request_id} label="request_id" />} />
        <Metadata
          label="Session"
          value={trace.session_id ? <CopyId value={trace.session_id} label="session_id" /> : "unavailable"}
        />
        <Metadata
          label="Checkpoint"
          value={trace.checkpoint_id ? <CopyId value={trace.checkpoint_id} label="checkpoint_id" /> : "unavailable"}
        />
        <Metadata label="Status" value={trace.status} />
        <Metadata label="Error code" value={trace.error_code ?? "none"} />
      </dl>
    </section>
  )
}

function EvidencePanel({ trace }: Readonly<{ trace: OperatorTraceDetail }>) {
  return (
    <section>
      <h2 className="mb-3 text-sm font-medium">Evidence state</h2>
      <dl className="grid gap-4 md:grid-cols-2">
        <Metadata label="Schema version" value={trace.evidence.schema_version} />
        <Metadata label="Capture mode" value={trace.evidence.capture_mode} />
        <Metadata label="Sample decision" value={trace.evidence.sample_decision} />
        <Metadata label="Completeness" value={trace.evidence.completeness} />
        <Metadata label="Freshness" value={trace.evidence.freshness} />
        <Metadata label="Retention" value={trace.evidence.retention} />
        <Metadata label="Publication" value={trace.evidence.publication_state} />
        <Metadata label="Source watermark" value={trace.evidence.source_watermark} />
        <Metadata
          label="Ingestion lag"
          value={trace.evidence.ingestion_lag_ms == null ? "not measured" : `${trace.evidence.ingestion_lag_ms} ms`}
        />
        <Metadata label="Started" value={new Date(trace.started_at).toISOString()} />
        <Metadata label="Ended" value={trace.ended_at ? new Date(trace.ended_at).toISOString() : "unavailable"} />
        <Metadata
          label="Measured duration"
          value={trace.duration_ms === null ? "unavailable" : `${trace.duration_ms} ms`}
        />
      </dl>
    </section>
  )
}

function SpansPanel({ trace }: Readonly<{ trace: OperatorTraceDetail }>) {
  return (
    <Section title="Spans" state={trace.spans.length ? "available" : "unavailable"}>
      {trace.spans.length === 0 ? (
        <p className="text-sm text-muted-foreground">No span rows for this run.</p>
      ) : (
        <ul className="space-y-2 font-mono text-xs">
          {trace.spans.map((span) => (
            <li key={span.span_id}>
              <CopyId value={span.span_id} label="span_id" /> · {span.operation_kind} · {span.status}
            </li>
          ))}
        </ul>
      )}
    </Section>
  )
}

function AssemblyPanel({ trace }: Readonly<{ trace: OperatorTraceDetail }>) {
  return (
    <Section title="Assembly metrics" state={trace.assembly ? "available" : "unavailable"}>
      {trace.assembly ? (
        <dl className="grid gap-2 md:grid-cols-3 font-mono text-xs">
          <Metadata label="total_ms" value={String(trace.assembly.total_ms)} />
          <Metadata label="ranking_ms" value={String(trace.assembly.ranking_ms)} />
          <Metadata label="packing_ms" value={String(trace.assembly.packing_ms)} />
          <Metadata label="candidates_evaluated" value={String(trace.assembly.candidates_evaluated)} />
        </dl>
      ) : (
        <p className="text-sm text-muted-foreground">Assembly metrics not persisted for this run.</p>
      )}
    </Section>
  )
}

function CandidatesPanel({ trace }: Readonly<{ trace: OperatorTraceDetail }>) {
  return (
    <Section title="Candidates" state={trace.candidates.length ? "available" : "unavailable"}>
      {trace.score_schema_note ? (
        <p className="mb-2 text-sm text-amber-700 dark:text-amber-300">{trace.score_schema_note}</p>
      ) : null}
      {trace.candidates.length === 0 ? (
        <p className="text-sm text-muted-foreground">No candidate rows for this run.</p>
      ) : (
        <ul className="space-y-1 font-mono text-xs">
          {trace.candidates.map((candidate) => (
            <li key={`${candidate.memory_id}-${candidate.retrieval_rank}`}>
              rank {candidate.retrieval_rank}
              {candidate.final_rank != null ? ` → ${candidate.final_rank}` : ""} · {candidate.exclusion} ·{" "}
              {candidate.score_schema}
            </li>
          ))}
        </ul>
      )}
    </Section>
  )
}

function DirectivePanel({ trace }: Readonly<{ trace: OperatorTraceDetail }>) {
  return (
    <Section title="Directive snapshot" state={trace.directive ? "available" : "unavailable"}>
      {trace.directive ? (
        <dl className="grid gap-2 md:grid-cols-2 font-mono text-xs">
          <Metadata label="schema_version" value={trace.directive.schema_version} />
          <Metadata label="content_hash" value={trace.directive.content_hash ?? "unavailable"} />
        </dl>
      ) : (
        <p className="text-sm text-muted-foreground">Directive snapshot not persisted for this run.</p>
      )}
    </Section>
  )
}

function ToolsPanel({ trace }: Readonly<{ trace: OperatorTraceDetail }>) {
  return (
    <Section title="Sanitized tool audits" state={trace.tools.length ? "available" : "unavailable"}>
      {trace.tools.length === 0 ? (
        <p className="text-sm text-muted-foreground">No sanitized tool audits for this run.</p>
      ) : (
        <ul className="space-y-1 font-mono text-xs">
          {trace.tools.map((tool, index) => (
            <li key={`${tool.tool_name}-${index}`}>
              {tool.tool_name} · {tool.status}
              {tool.error_code ? ` · ${tool.error_code}` : ""}
            </li>
          ))}
        </ul>
      )}
    </Section>
  )
}

function UnavailablePanel({ trace }: Readonly<{ trace: OperatorTraceDetail }>) {
  return (
    <div className="rounded-md border border-dashed p-4">
      <h2 className="font-medium">Unavailable / disabled</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Raw content, replay, counterfactuals, and actions remain disabled. Sections without durable joins stay
        explicitly unavailable.
      </p>
      <p className="mt-2 font-mono text-xs text-muted-foreground">{trace.unavailable_sections.join(" · ")}</p>
    </div>
  )
}

export function RunInspector({ trace }: Readonly<{ trace: OperatorTraceDetail }>) {
  return (
    <Card className={`${panelClass} mt-4`}>
      <CardHeader>
        <p className="font-mono text-[12px] uppercase tracking-[0.18em] text-muted-foreground">
          Trace Inspector · frozen metadata snapshot
        </p>
        <CardTitle className="mt-2 break-all font-mono text-xl">
          <CopyId value={trace.run_id} label="run_id" />
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          Source {trace.evidence.source} · publication {trace.evidence.publication_state} · watermark{" "}
          {trace.evidence.source_watermark} · observed {new Date(trace.evidence.observed_at).toISOString()}
        </p>
      </CardHeader>
      <CardContent className="space-y-6">
        <IdentityPanel trace={trace} />
        <EvidencePanel trace={trace} />
        <SpansPanel trace={trace} />
        <AssemblyPanel trace={trace} />
        <CandidatesPanel trace={trace} />
        <DirectivePanel trace={trace} />
        <ToolsPanel trace={trace} />
        <UnavailablePanel trace={trace} />
      </CardContent>
    </Card>
  )
}

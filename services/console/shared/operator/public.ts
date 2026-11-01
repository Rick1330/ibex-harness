import type {
  OperatorAgent,
  OperatorAgentPage,
  OperatorContext,
  OperatorOverview,
  OperatorTrace,
  OperatorTraceDetail,
  OperatorTraceList,
  PlatformHealth,
} from "./contracts"

export type PublicOperatorContext = Omit<OperatorContext, "org_id">
export type PublicOperatorOverview = Omit<OperatorOverview, "org_id">

export type PublicOperatorTrace = OperatorTrace
export type PublicOperatorTraceList = OperatorTraceList
export type PublicOperatorTraceDetail = OperatorTraceDetail
export type PublicPlatformHealth = PlatformHealth
export type PublicOperatorAgent = OperatorAgent
export type PublicOperatorAgentPage = OperatorAgentPage

export type OperatorErrorEnvelope = {
  error: {
    code: string
    message: string
    request_id?: string
  }
}

export function readErrorEnvelope(error: unknown): OperatorErrorEnvelope | null {
  if (!error || typeof error !== "object") return null
  const data = "data" in error ? (error as { data?: unknown }).data : null
  if (!data || typeof data !== "object" || !("error" in data)) return null
  const envelope = (data as { error?: unknown }).error
  if (!envelope || typeof envelope !== "object") return null
  const candidate = envelope as Record<string, unknown>
  if (typeof candidate.code !== "string" || typeof candidate.message !== "string") return null
  return {
    error: {
      code: candidate.code,
      message: candidate.message,
      ...(typeof candidate.request_id === "string" ? { request_id: candidate.request_id } : {}),
    },
  }
}

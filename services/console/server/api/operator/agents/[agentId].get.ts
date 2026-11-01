import { OperatorAgentSchema } from "~~/shared/operator/contracts"
import { noStore, fetchOperatorJson, toHttpError } from "~~/server/utils/operator/http"

const AGENT_ID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export default defineEventHandler(async (event) => {
  noStore(event)
  const agentId = getRouterParam(event, "agentId")
  if (!agentId || !AGENT_ID_RE.test(agentId)) {
    throw createError({
      statusCode: 404,
      statusMessage: "Agent not found",
      data: { error: { code: "NOT_FOUND", message: "Agent not found" } },
    })
  }
  try {
    return await fetchOperatorJson(
      event,
      "agentDetail",
      (value) => OperatorAgentSchema.parse(value),
      { suffix: agentId },
    )
  } catch (error) {
    toHttpError(error)
  }
})

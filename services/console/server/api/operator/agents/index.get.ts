import { OperatorAgentPageSchema } from "~~/shared/operator/contracts"
import {
  LiveAgentQueryError,
  parseLiveAgentQuery,
  serializeLiveAgentQuery,
} from "~~/shared/operator/agent-query"
import { noStore, fetchOperatorJson, toHttpError } from "~~/server/utils/operator/http"

export default defineEventHandler(async (event) => {
  noStore(event)
  try {
    const query = parseLiveAgentQuery(getQuery(event))
    return await fetchOperatorJson(
      event,
      "agents",
      (value) => OperatorAgentPageSchema.parse(value),
      { query: serializeLiveAgentQuery(query) },
    )
  } catch (error) {
    if (error instanceof LiveAgentQueryError) {
      throw createError({
        statusCode: 400,
        statusMessage: error.message,
        data: { error: { code: "INVALID_QUERY", message: error.message } },
      })
    }
    toHttpError(error)
  }
})

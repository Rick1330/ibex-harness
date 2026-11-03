import { OperatorTraceListSchema } from "~~/shared/operator/contracts"
import { noStore, fetchOperatorJson, toHttpError } from "~~/server/utils/operator/http"

export default defineEventHandler(async (event) => {
  noStore(event)
  const traceId = getRouterParam(event, "traceId")
  if (!traceId) {
    throw createError({
      statusCode: 404,
      statusMessage: "Trace not found",
      data: { error: { code: "NOT_FOUND", message: "Trace not found" } },
    })
  }
  try {
    return await fetchOperatorJson(
      event,
      "traceDetail",
      (value) => OperatorTraceListSchema.parse(value),
      { suffix: traceId },
    )
  } catch (error) {
    toHttpError(error)
  }
})

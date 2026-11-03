import { OperatorTraceDetailSchema } from "~~/shared/operator/contracts"
import { noStore, fetchOperatorJson, toHttpError } from "~~/server/utils/operator/http"

export default defineEventHandler(async (event) => {
  noStore(event)
  const runId = getRouterParam(event, "runId")
  if (!runId) {
    throw createError({
      statusCode: 404,
      statusMessage: "Trace run not found",
      data: { error: { code: "NOT_FOUND", message: "Trace run not found" } },
    })
  }
  try {
    return await fetchOperatorJson(
      event,
      "runDetail",
      (value) => OperatorTraceDetailSchema.parse(value),
      { suffix: runId },
    )
  } catch (error) {
    toHttpError(error)
  }
})

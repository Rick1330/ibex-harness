import { OperatorSessionRecordDetailSchema } from "~~/shared/operator/contracts"
import { noStore, fetchOperatorJson, toHttpError } from "~~/server/utils/operator/http"

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export default defineEventHandler(async (event) => {
  noStore(event)
  const sessionId = getRouterParam(event, "sessionId")
  if (!sessionId || !UUID_RE.test(sessionId)) {
    throw createError({
      statusCode: 404,
      statusMessage: "Session not found",
      data: { error: { code: "NOT_FOUND", message: "Session not found" } },
    })
  }
  try {
    return await fetchOperatorJson(
      event,
      "sessionDetail",
      (value) => OperatorSessionRecordDetailSchema.parse(value),
      { suffix: sessionId },
    )
  } catch (error) {
    toHttpError(error)
  }
})

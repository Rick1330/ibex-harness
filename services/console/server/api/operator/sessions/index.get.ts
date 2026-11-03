import { OperatorSessionRecordPageSchema } from "~~/shared/operator/contracts"
import {
  LiveSessionQueryError,
  parseLiveSessionQuery,
  serializeLiveSessionQuery,
} from "~~/shared/operator/session-query"
import { noStore, fetchOperatorJson, toHttpError } from "~~/server/utils/operator/http"

export default defineEventHandler(async (event) => {
  noStore(event)
  try {
    const query = parseLiveSessionQuery(getQuery(event))
    return await fetchOperatorJson(
      event,
      "sessions",
      (value) => OperatorSessionRecordPageSchema.parse(value),
      { query: serializeLiveSessionQuery(query) },
    )
  } catch (error) {
    if (error instanceof LiveSessionQueryError) {
      throw createError({
        statusCode: 400,
        statusMessage: error.message,
        data: { error: { code: "INVALID_QUERY", message: error.message } },
      })
    }
    toHttpError(error)
  }
})

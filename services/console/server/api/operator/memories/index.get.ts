import { OperatorMemoryPageSchema } from "~~/shared/operator/contracts"
import {
  LiveMemoryQueryError,
  parseLiveMemoryQuery,
  serializeLiveMemoryQuery,
} from "~~/shared/operator/memory-query"
import { noStore, fetchOperatorJson, toHttpError } from "~~/server/utils/operator/http"

export default defineEventHandler(async (event) => {
  noStore(event)
  try {
    const query = parseLiveMemoryQuery(getQuery(event))
    return await fetchOperatorJson(
      event,
      "memories",
      (value) => OperatorMemoryPageSchema.parse(value),
      { query: serializeLiveMemoryQuery(query) },
    )
  } catch (error) {
    if (error instanceof LiveMemoryQueryError) {
      throw createError({
        statusCode: 400,
        statusMessage: error.message,
        data: { error: { code: "INVALID_QUERY", message: error.message } },
      })
    }
    toHttpError(error)
  }
})

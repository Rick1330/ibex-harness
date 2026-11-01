import { OperatorTraceListSchema } from "~~/shared/operator/contracts"
import {
  LiveExploreQueryError,
  serializeLiveExploreQuery,
  parseLiveExploreQuery,
} from "~~/shared/operator/explore-query"
import { noStore, fetchOperatorJson, toHttpError } from "~~/server/utils/operator/http"

export default defineEventHandler(async (event) => {
  noStore(event)
  try {
    const query = parseLiveExploreQuery(getQuery(event))
    return await fetchOperatorJson(
      event,
      "traces",
      (value) => OperatorTraceListSchema.parse(value),
      { query: serializeLiveExploreQuery(query) },
    )
  } catch (error) {
    if (error instanceof LiveExploreQueryError) {
      throw createError({
        statusCode: 400,
        statusMessage: error.message,
        data: { error: { code: "INVALID_QUERY", message: error.message } },
      })
    }
    toHttpError(error)
  }
})

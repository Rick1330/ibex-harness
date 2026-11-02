import { OperatorDirectivePageSchema } from "~~/shared/operator/contracts"
import {
  LiveDirectiveQueryError,
  parseLiveDirectiveListQuery,
  serializeLiveDirectiveListQuery,
} from "~~/shared/operator/directive-query"
import { noStore, fetchOperatorJson, toHttpError } from "~~/server/utils/operator/http"

export default defineEventHandler(async (event) => {
  noStore(event)
  try {
    const query = parseLiveDirectiveListQuery(getQuery(event))
    return await fetchOperatorJson(
      event,
      "directives",
      (value) => OperatorDirectivePageSchema.parse(value),
      { query: serializeLiveDirectiveListQuery(query) },
    )
  } catch (error) {
    if (error instanceof LiveDirectiveQueryError) {
      throw createError({
        statusCode: 400,
        statusMessage: error.message,
        data: { error: { code: "INVALID_QUERY", message: error.message } },
      })
    }
    toHttpError(error)
  }
})

import { OperatorDirectiveDetailSchema } from "~~/shared/operator/contracts"
import {
  LiveDirectiveQueryError,
  parseLiveDirectiveDetailQuery,
  serializeLiveDirectiveDetailQuery,
} from "~~/shared/operator/directive-query"
import { noStore, fetchOperatorJson, toHttpError } from "~~/server/utils/operator/http"

export default defineEventHandler(async (event) => {
  noStore(event)
  const directiveId = getRouterParam(event, "directiveId")
  if (!directiveId) {
    throw createError({ statusCode: 400, statusMessage: "directiveId is required" })
  }
  try {
    const query = parseLiveDirectiveDetailQuery(getQuery(event))
    return await fetchOperatorJson(
      event,
      "directiveDetail",
      (value) => OperatorDirectiveDetailSchema.parse(value),
      { suffix: directiveId, query: serializeLiveDirectiveDetailQuery(query) },
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

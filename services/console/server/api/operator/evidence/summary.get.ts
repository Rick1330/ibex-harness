import { OperatorEvidenceSummarySchema } from "~~/shared/operator/contracts"
import {
  LiveEvidenceQueryError,
  parseLiveEvidenceQuery,
  serializeLiveEvidenceQuery,
} from "~~/shared/operator/evidence-query"
import { noStore, fetchOperatorJson, toHttpError } from "~~/server/utils/operator/http"

export default defineEventHandler(async (event) => {
  noStore(event)
  try {
    const query = parseLiveEvidenceQuery(getQuery(event))
    return await fetchOperatorJson(
      event,
      "evidenceSummary",
      (value) => OperatorEvidenceSummarySchema.parse(value),
      { query: serializeLiveEvidenceQuery(query) },
    )
  } catch (error) {
    if (error instanceof LiveEvidenceQueryError) {
      throw createError({
        statusCode: 400,
        statusMessage: error.message,
        data: { error: { code: "INVALID_QUERY", message: error.message } },
      })
    }
    toHttpError(error)
  }
})

import { OperatorContextSchema } from "~~/shared/operator/contracts"
import { noStore, fetchOperatorJson, toHttpError } from "~~/server/utils/operator/http"

export default defineEventHandler(async (event) => {
  noStore(event)
  try {
    const context = await fetchOperatorJson(event, "context", (value) =>
      OperatorContextSchema.parse(value),
    )
    const { org_id: _orgId, ...visible } = context
    return visible
  } catch (error) {
    toHttpError(error)
  }
})

import { OperatorOverviewSchema } from "~~/shared/operator/contracts"
import { noStore, fetchOperatorJson, toHttpError } from "~~/server/utils/operator/http"

export default defineEventHandler(async (event) => {
  noStore(event)
  try {
    const overview = await fetchOperatorJson(event, "overview", (value) =>
      OperatorOverviewSchema.parse(value),
    )
    const { org_id: _orgId, ...visible } = overview
    return visible
  } catch (error) {
    toHttpError(error)
  }
})

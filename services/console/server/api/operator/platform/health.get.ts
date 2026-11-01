import { PlatformHealthSchema } from "~~/shared/operator/contracts"
import { noStore, fetchOperatorJson, toHttpError } from "~~/server/utils/operator/http"

export default defineEventHandler(async (event) => {
  noStore(event)
  try {
    return await fetchOperatorJson(event, "platformHealth", (value) =>
      PlatformHealthSchema.parse(value),
    )
  } catch (error) {
    toHttpError(error)
  }
})

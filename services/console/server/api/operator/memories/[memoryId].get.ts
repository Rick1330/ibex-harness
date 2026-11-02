import { OperatorMemorySchema } from "~~/shared/operator/contracts"
import { noStore, fetchOperatorJson, toHttpError } from "~~/server/utils/operator/http"

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export default defineEventHandler(async (event) => {
  noStore(event)
  const memoryId = getRouterParam(event, "memoryId")
  if (!memoryId || !UUID_RE.test(memoryId)) {
    throw createError({
      statusCode: 404,
      statusMessage: "Memory not found",
      data: { error: { code: "NOT_FOUND", message: "Memory not found" } },
    })
  }
  try {
    return await fetchOperatorJson(
      event,
      "memoryDetail",
      (value) => OperatorMemorySchema.parse(value),
      { suffix: memoryId },
    )
  } catch (error) {
    toHttpError(error)
  }
})

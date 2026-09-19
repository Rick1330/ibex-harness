/**
 * Pure SSE helpers (unit-tested). Used by the operator shell.
 */

export function parseSSEBlock(block) {
  if (!block.trim() || block.startsWith(":")) {
    return null;
  }
  let id = null;
  let data = "";
  for (const line of block.split("\n")) {
    if (line.startsWith("id:")) id = line.slice(3).trim();
    if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  const numericId = id != null && id !== "" && Number.isFinite(Number(id)) ? Number(id) : null;
  return { id: numericId, rawId: id, data };
}

export function shouldAcceptEventId(lastEventId, nextId) {
  if (nextId == null) return true;
  if (lastEventId == null) return true;
  return nextId > lastEventId;
}

export function buildLoginBody(pat) {
  return JSON.stringify({ pat: String(pat).trim() });
}

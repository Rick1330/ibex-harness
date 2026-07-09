/** Safe label for fumadocs PageTree nodes (name may be ReactNode). */
function primitiveLabel(name: unknown): string | null {
  if (typeof name === "number") {
    return String(name);
  }
  if (typeof name === "boolean") {
    return String(name);
  }
  if (typeof name === "bigint") {
    return String(name);
  }
  return null;
}

export function pageTreeLabel(name: unknown): string {
  if (typeof name === "string") {
    return name;
  }
  const primitive = primitiveLabel(name);
  if (primitive !== null) {
    return primitive;
  }
  return "Untitled";
}

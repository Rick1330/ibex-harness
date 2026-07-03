/** Safe label for fumadocs PageTree nodes (name may be ReactNode). */
export function pageTreeLabel(name: unknown): string {
  if (typeof name === "string") {
    return name;
  }
  if (typeof name === "number" || typeof name === "boolean" || typeof name === "bigint") {
    return String(name);
  }
  return "Untitled";
}

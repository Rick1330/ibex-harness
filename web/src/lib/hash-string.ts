/** Small stable hash for diagram cache keys and DOM ids. */
export function hashString(input: string): string {
  let hash = 0;

  for (let index = 0; index < input.length; ) {
    const codePoint = input.codePointAt(index) ?? 0;
    hash = Math.trunc(Math.imul(31, hash) + codePoint);
    index += codePoint > 0xffff ? 2 : 1;
  }

  return Math.trunc(Math.abs(hash)).toString(36);
}

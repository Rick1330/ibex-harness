/** Small stable hash for diagram cache keys and DOM ids. */
export function hashString(input: string): string {
  let hash = 0;

  for (let index = 0; index < input.length; index += 1) {
    hash = (Math.imul(31, hash) + input.charCodeAt(index)) | 0;
  }

  return Math.abs(hash).toString(36);
}

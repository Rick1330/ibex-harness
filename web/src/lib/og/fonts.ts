import { readFile } from "node:fs/promises";
import { join } from "node:path";

export type OgFont = {
  name: "Geist Sans";
  data: ArrayBuffer;
  weight: 400 | 700;
  style: "normal";
};

const fontDir = join(process.cwd(), "public", "fonts");

async function loadFontFile(
  filename: string,
  weight: 400 | 700,
): Promise<OgFont> {
  const buffer = await readFile(join(fontDir, filename));
  return {
    name: "Geist Sans",
    data: buffer.buffer.slice(
      buffer.byteOffset,
      buffer.byteOffset + buffer.byteLength,
    ),
    weight,
    style: "normal",
  };
}

let fontsPromise: Promise<OgFont[]> | undefined;

export function loadOgFonts(): Promise<OgFont[]> {
  if (!fontsPromise) {
    fontsPromise = Promise.all([
      loadFontFile("Geist-Regular.ttf", 400),
      loadFontFile("Geist-Bold.ttf", 700),
    ]);
  }
  return fontsPromise;
}

export function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength - 1).trimEnd()}…`;
}

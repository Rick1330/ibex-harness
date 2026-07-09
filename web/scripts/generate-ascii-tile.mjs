import { execFileSync } from "node:child_process";
import { existsSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const CHARS = String.raw`wxuoi:.=+*%#WM/\<>vc^~ `;
const TILE = 256;
const BG = [233, 232, 228];
const FG = [248, 248, 246];
const SAFE_PATH =
  process.platform === "win32"
    ? String.raw`C:\Windows\System32`
    : "/usr/bin:/bin";

function pickChar(row, col) {
  const hash = Math.trunc((row * 374761393 + col * 668265263) % CHARS.length);
  const index = hash < 0 ? hash + CHARS.length : hash;
  return CHARS.charAt(index);
}

function buildTilePixels() {
  const cell = 8;
  const pixels = Buffer.alloc(TILE * TILE * 3);

  for (let y = 0; y < TILE; y += 1) {
    for (let x = 0; x < TILE; x += 1) {
      const cellRow = Math.floor(y / cell);
      const cellCol = Math.floor(x / cell);
      const glyph = pickChar(cellRow, cellCol);
      const inGlyph =
        glyph !== " " && (x % cell > 1) && (y % cell > 1) && (x % cell < 6) && (y % cell < 6);
      const offset = (y * TILE + x) * 3;
      const color = inGlyph ? FG : BG;
      pixels[offset] = color[0];
      pixels[offset + 1] = color[1];
      pixels[offset + 2] = color[2];
    }
  }
  return pixels;
}

function resolveFfmpegPath() {
  const override = process.env.IBEX_FFMPEG_PATH;
  if (typeof override === "string" && override.length > 0) {
    return override;
  }
  const candidates =
    process.platform === "win32"
      ? [
          String.raw`C:\ffmpeg\bin\ffmpeg.exe`,
          String.raw`C:\Program Files\ffmpeg\bin\ffmpeg.exe`,
        ]
      : ["/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg"];
  const found = candidates.find((candidate) => existsSync(candidate));
  if (!found) {
    throw new Error(
      "ffmpeg not found — set IBEX_FFMPEG_PATH or commit ascii-tile.webp manually",
    );
  }
  return found;
}

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.resolve(scriptDir, "../public/brand");
const ppmPath = path.join(outDir, "ascii-tile.ppm");
const webpPath = path.join(outDir, "ascii-tile.webp");

const pixels = buildTilePixels();
const header = `P6\n${TILE} ${TILE}\n255\n`;
writeFileSync(ppmPath, Buffer.concat([Buffer.from(header), pixels]));

try {
  execFileSync(
    resolveFfmpegPath(),
    ["-y", "-i", ppmPath, "-quality", "85", webpPath],
    {
      stdio: "inherit",
      env: { ...process.env, PATH: SAFE_PATH },
    },
  );
} catch {
  console.error("[ascii-tile] ffmpeg failed — install ffmpeg or commit ascii-tile.webp manually");
  process.exit(1);
}

console.log("[ascii-tile] wrote ascii-tile.webp");

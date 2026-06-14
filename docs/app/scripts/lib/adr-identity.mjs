import { extractH1Title } from "./text-utils.mjs";

function parseAdrFromHeading(h1) {
  if (!h1?.startsWith("ADR-")) return undefined;

  const colonIndex = h1.indexOf(":");
  if (colonIndex === -1) return undefined;

  return {
    adrId: h1.slice(4, colonIndex).trim(),
    title: h1.slice(colonIndex + 1).trim(),
  };
}

function parseAdrFromFilename(filename) {
  let digits = "";
  for (let index = 0; index < filename.length; index += 1) {
    const char = filename[index];
    if (char >= "0" && char <= "9") {
      digits += char;
      if (digits.length === 4) break;
    }
  }

  if (digits.length !== 4) return undefined;
  return { adrId: digits, title: filename };
}

export function parseAdrIdentity(content, filename) {
  const fromHeading = parseAdrFromHeading(extractH1Title(content));
  if (fromHeading) {
    return { adrId: fromHeading.adrId, title: `ADR-${fromHeading.adrId}: ${fromHeading.title}` };
  }

  const fromFilename = parseAdrFromFilename(filename);
  if (fromFilename) {
    return { adrId: fromFilename.adrId, title: `ADR-${fromFilename.adrId}: ${fromFilename.title}` };
  }

  return { adrId: "0000", title: filename };
}

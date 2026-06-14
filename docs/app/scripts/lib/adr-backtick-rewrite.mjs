/** ADR backtick rewrite helpers (Sonar S5852 / CodeScene). */

function readAdrId(text, startIndex) {
  const close = text.indexOf("`", startIndex);
  if (close === -1) return undefined;
  return { adrId: text.slice(startIndex, startIndex + 4), end: close + 1 };
}

function rewriteWriteAdrPrefix(text, index, writePrefix) {
  const parsed = readAdrId(text, index + writePrefix.length);
  if (!parsed) return undefined;

  return {
    text: `Write ADR-${parsed.adrId} (engineering \`docs/adr/\` — promote to \`/docs/adr/\` when accepted)`,
    end: parsed.end,
  };
}

function rewriteInlineAdrPrefix(text, index, inlinePrefix) {
  const parsed = readAdrId(text, index + inlinePrefix.length);
  if (!parsed) return undefined;

  return {
    text: `\`ADR-${parsed.adrId}\``,
    end: parsed.end,
  };
}

export function simplifyAdrBackticks(text) {
  const inlinePrefix = "`docs/adr/ADR-";
  const writePrefix = "Write `docs/adr/ADR-";
  let result = "";
  let index = 0;

  while (index < text.length) {
    const writeMatch = text.startsWith(writePrefix, index)
      ? rewriteWriteAdrPrefix(text, index, writePrefix)
      : undefined;
    if (writeMatch) {
      result += writeMatch.text;
      index = writeMatch.end;
      continue;
    }

    const inlineMatch = text.startsWith(inlinePrefix, index)
      ? rewriteInlineAdrPrefix(text, index, inlinePrefix)
      : undefined;
    if (inlineMatch) {
      result += inlineMatch.text;
      index = inlineMatch.end;
      continue;
    }

    result += text[index];
    index += 1;
  }

  return result;
}

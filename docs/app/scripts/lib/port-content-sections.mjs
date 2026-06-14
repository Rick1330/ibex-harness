function normalizeHeadingTitle(line) {
  const heading = line.match(/^#{1,3}\s+(.+)/);
  if (!heading) return undefined;
  return heading[1].replace(/[^\w\s-]/g, "").trim();
}

function matchesWantedSection(title, sectionTitles) {
  const lower = title.toLowerCase();
  return sectionTitles.some((wanted) => lower.includes(wanted.toLowerCase()));
}

function isMajorSectionBreak(line) {
  return line.startsWith("## ");
}

function flushChunk(chunks, current) {
  if (current.length === 0) return;
  chunks.push(current.join("\n"));
}

export function extractSections(markdown, sectionTitles) {
  if (!sectionTitles?.length) return markdown;

  const lines = markdown.split("\n");
  const chunks = [];
  let capturing = false;
  let current = [];

  for (const line of lines) {
    const title = normalizeHeadingTitle(line);
    if (title && matchesWantedSection(title, sectionTitles)) {
      flushChunk(chunks, current);
      current = [line];
      capturing = true;
      continue;
    }

    if (capturing && isMajorSectionBreak(line)) {
      flushChunk(chunks, current);
      current = [];
      capturing = false;
    }

    if (capturing) current.push(line);
  }

  flushChunk(chunks, current);
  return chunks.join("\n\n") || markdown.slice(0, 8000);
}

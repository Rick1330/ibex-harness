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

function flushChunk(state) {
  if (state.current.length === 0) return;
  state.chunks.push(state.current.join("\n"));
}

function handleHeadingLine(line, state) {
  const title = normalizeHeadingTitle(line);
  if (title && matchesWantedSection(title, state.sectionTitles)) {
    flushChunk(state);
    state.current = [line];
    state.capturing = true;
    return;
  }

  if (state.capturing && isMajorSectionBreak(line)) {
    flushChunk(state);
    state.current = [];
    state.capturing = false;
  }
}

function createExtractState(sectionTitles) {
  return {
    sectionTitles,
    chunks: [],
    capturing: false,
    current: [],
  };
}

export function extractSections(markdown, sectionTitles) {
  if (!sectionTitles?.length) return markdown;

  const state = createExtractState(sectionTitles);

  for (const line of markdown.split("\n")) {
    handleHeadingLine(line, state);
    if (state.capturing) state.current.push(line);
  }

  flushChunk(state);
  return state.chunks.join("\n\n") || markdown.slice(0, 8000);
}

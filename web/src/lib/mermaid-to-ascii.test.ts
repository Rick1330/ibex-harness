import { describe, expect, it } from "vitest";

import { mermaidToAscii, stripAnsiSequences } from "./mermaid-to-ascii";

const INTRO_ARCHITECTURE_CHART = `flowchart LR
  Client["Agent / SDK"] -->|HTTPS :8080| Proxy["Proxy"]
  Proxy -->|gRPC :9091| Auth["Auth"]
  Auth --> PG["Postgres"]
  Proxy --> Redis["Redis"]
  Proxy -.->|Phase 2| LLM["LLM provider"]`;

const ANSI_RE = /\x1B\[[0-9;]*m/;

describe("stripAnsiSequences", () => {
  it("removes ANSI color sequences", () => {
    const colored = "\x1B[38;2;161;161;170m+---+\x1B[0m";
    expect(stripAnsiSequences(colored)).toBe("+---+");
  });
});

describe("mermaidToAscii", () => {
  it("returns plain ASCII without ANSI escapes for introduction architecture chart", () => {
    const { ascii, source } = mermaidToAscii(INTRO_ARCHITECTURE_CHART);

    expect(source).toContain("flowchart LR");
    expect(ascii).toBeTruthy();
    expect(ascii).not.toMatch(ANSI_RE);
    expect(ascii).toContain("Proxy");
    expect(ascii).toContain("Postgres");
  });

  it("returns null ascii for empty input", () => {
    expect(mermaidToAscii("   ").ascii).toBeNull();
  });
});

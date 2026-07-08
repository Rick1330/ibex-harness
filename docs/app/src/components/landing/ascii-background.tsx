"use client";

import { useEffect, useState } from "react";

const CHARS = String.raw`wxuoi:.=+*%#WM/\<>vc^~ `;

function pickChar(row: number, col: number): string {
  const hash = Math.trunc((row * 374761393 + col * 668265263) % CHARS.length);
  const index = hash < 0 ? hash + CHARS.length : hash;
  return CHARS.charAt(index);
}

function buildField(cols: number, rows: number): string {
  let out = "";
  for (let r = 0; r < rows; r += 1) {
    let line = "";
    for (let c = 0; c < cols; c += 1) {
      line += pickChar(r, c);
    }
    out += `${line}\n`;
  }
  return out;
}

export function AsciiBackground() {
  const [field, setField] = useState("");

  useEffect(() => {
    const charWidth = 7.6;
    const lineHeight = 13;
    let raf = 0;

    const generate = () => {
      const cols = Math.ceil(globalThis.innerWidth / charWidth) + 2;
      const rows = Math.ceil(globalThis.innerHeight / lineHeight) + 2;
      setField(buildField(cols, rows));
    };

    generate();
    const onResize = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(generate);
    };
    globalThis.addEventListener("resize", onResize);
    return () => {
      globalThis.removeEventListener("resize", onResize);
      cancelAnimationFrame(raf);
    };
  }, []);

  return (
    <pre
      aria-hidden
      className="ascii-bg pointer-events-none fixed inset-0 -z-10 m-0 select-none overflow-hidden text-muted-foreground"
    >
      {field}
    </pre>
  );
}

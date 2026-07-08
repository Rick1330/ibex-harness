"use client";

import { useEffect, useRef, useState } from "react";

const CHARS = "wxuoi:.=+*%#WM/\\<>vc^~ ";

function buildField(cols: number, rows: number): string {
  let out = "";
  for (let r = 0; r < rows; r += 1) {
    let line = "";
    for (let c = 0; c < cols; c += 1) {
      line += CHARS[(Math.random() * CHARS.length) | 0];
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
      const cols = Math.ceil(window.innerWidth / charWidth) + 2;
      const rows = Math.ceil(window.innerHeight / lineHeight) + 2;
      setField(buildField(cols, rows));
    };

    generate();
    const onResize = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(generate);
    };
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
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

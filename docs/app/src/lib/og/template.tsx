import { ImageResponse } from "next/og";

import { loadOgFonts, truncateText } from "@/lib/og/fonts";

export const ogSize = {
  width: 1200,
  height: 630,
} as const;

export const ogContentType = "image/png";

type OgImageContentProps = {
  title: string;
  description: string;
};

function HornMark() {
  return (
    <svg
      fill="none"
      height="28"
      viewBox="0 0 24 24"
      width="28"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        d="M5 19L11 5"
        stroke="#fafafa"
        strokeLinecap="round"
        strokeWidth="1.5"
      />
      <path
        d="M19 19L13 5"
        stroke="#a1a1aa"
        strokeLinecap="round"
        strokeWidth="1.5"
      />
      <path
        d="M11 5L13 5"
        stroke="#fafafa"
        strokeLinecap="round"
        strokeWidth="1.5"
      />
    </svg>
  );
}

/** Topographic accent lines echoing ibexharness.com OG art (lightweight SVG). */
function TopographicAccent() {
  const stroke = "rgba(179, 109, 68, 0.35)";
  return (
    <svg
      fill="none"
      height="630"
      style={{ position: "absolute", right: 0, top: 0 }}
      viewBox="0 0 520 630"
      width="520"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        d="M40 80 C 140 40, 240 120, 360 60 S 520 140, 520 140"
        stroke={stroke}
        strokeWidth="1"
      />
      <path
        d="M0 180 C 120 140, 220 220, 340 160 S 520 240, 520 240"
        stroke={stroke}
        strokeWidth="1"
      />
      <path
        d="M60 300 C 160 260, 260 340, 380 280 S 520 360, 520 360"
        stroke={stroke}
        strokeWidth="1"
      />
      <path
        d="M20 420 C 140 380, 240 460, 360 400 S 520 480, 520 480"
        stroke={stroke}
        strokeWidth="1"
      />
      <path
        d="M80 540 C 180 500, 280 580, 400 520 S 520 600, 520 600"
        stroke={stroke}
        strokeWidth="1"
      />
    </svg>
  );
}

export async function createOgImageResponse({
  title,
  description,
}: OgImageContentProps) {
  const displayTitle = truncateText(title, 72);
  const displayDescription = truncateText(description, 140);

  const fonts = await loadOgFonts();

  return new ImageResponse(
    (
      <div
        style={{
          backgroundColor: "#09090b",
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          position: "relative",
          fontFamily: "Geist Sans",
        }}
      >
        <TopographicAccent />

        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            padding: "56px 64px 0",
            position: "relative",
          }}
        >
          <HornMark />
          <div
            style={{
              display: "flex",
              fontSize: 20,
              fontWeight: 700,
              letterSpacing: "0.05em",
              textTransform: "uppercase",
            }}
          >
            <span style={{ color: "#fafafa" }}>IBEX</span>
            <span style={{ color: "#a1a1aa" }}> HARNESS</span>
          </div>
        </div>

        <div
          style={{
            display: "flex",
            flexDirection: "column",
            flex: 1,
            justifyContent: "flex-end",
            padding: "0 64px 56px",
            position: "relative",
            gap: 24,
          }}
        >
          <div
            style={{
              color: "#fafafa",
              fontSize: 56,
              fontWeight: 700,
              lineHeight: 1.1,
              letterSpacing: "-0.02em",
              maxWidth: 980,
            }}
          >
            {displayTitle}
          </div>
          <div
            style={{
              backgroundColor: "#222226",
              height: 1,
              width: "100%",
            }}
          />
          <div
            style={{
              color: "#a1a1aa",
              fontSize: 24,
              fontWeight: 400,
              lineHeight: 1.35,
              maxWidth: 920,
            }}
          >
            {displayDescription}
          </div>
        </div>
      </div>
    ),
    {
      ...ogSize,
      fonts,
    },
  );
}
